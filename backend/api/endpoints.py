"""FastAPI REST API Endpoints Router.

Defines API routes for audio transcription (/api/v1/transcribe), consultation processing,
status polling, and doctor approval/rejection.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, status, BackgroundTasks
from pydantic import BaseModel

from backend.tools.whisper import transcribe_audio_file
from backend.graph.state import create_initial_state, MedicalState
from backend.graph.workflow import build_graph
from backend.memory.supabase import save_approved_document, save_rejected_consultation
from backend.schemas.models import (
    ProcessConsultationRequest,
    ProcessConsultationResponse,
    ApproveConsultationRequest,
    ApproveConsultationResponse,
    RejectConsultationRequest,
    RejectConsultationResponse,
    ConsultationStatus
)

logger = logging.getLogger("api_endpoints")

api_router = APIRouter(prefix="/api/v1")

# Global in-memory active consultation session store
ACTIVE_CONSULTATIONS: Dict[str, Dict[str, Any]] = {}


class TranscribeResponse(BaseModel):
    transcript: str
    duration_seconds: float


def run_pipeline_task(consultation_id: str, state: MedicalState):
    """Background task function executing the multi-agent LangGraph workflow engine."""
    try:
        logger.info(f"Starting background LangGraph execution for consultation_id: {consultation_id}")
        graph = build_graph()
        config = {"configurable": {"thread_id": consultation_id}}
        final_state = graph.invoke(state, config=config)

        # Determine final status after graph execution
        history = final_state.get("history", {})
        if history.get("patient_unresolved"):
            final_state["status"] = ConsultationStatus.PROCESSING.value
            logger.warning(f"Consultation {consultation_id}: Unresolved patient record detected.")
        else:
            final_state["status"] = ConsultationStatus.AWAITING_APPROVAL.value
            logger.info(f"Consultation {consultation_id} pipeline completed. Status: AWAITING_APPROVAL")

        ACTIVE_CONSULTATIONS[consultation_id] = final_state
    except Exception as exc:
        logger.error(f"Error executing graph pipeline for consultation {consultation_id}: {exc}")
        state["status"] = ConsultationStatus.FAILED.value
        logs = list(state.get("error_logs") or [])
        logs.append(f"PIPELINE_ERROR: {exc}")
        state["error_logs"] = logs
        ACTIVE_CONSULTATIONS[consultation_id] = state


@api_router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe clinical dictation audio file",
    description="Uploads an audio file (.wav, .mp3, .m4a, .webm) and returns plain text clinical transcript."
)
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
    """FastAPI endpoint to process uploaded dictation audio files using OpenAI/Groq Whisper."""
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file uploaded."
        )

    try:
        file_bytes = await file.read()
        result = transcribe_audio_file(file_bytes, file.filename)
        return TranscribeResponse(
            transcript=result["transcript"],
            duration_seconds=result["duration_seconds"]
        )
    except ValueError as val_err:
        logger.warning(f"Audio file validation error: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as exc:
        logger.error(f"Audio transcription endpoint error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to transcribe audio file. Switched to manual text dictation mode. Details: {exc}"
        )


@api_router.post(
    "/consultation/process",
    response_model=ProcessConsultationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger multi-agent clinical documentation pipeline",
    description="Initializes state and starts background LangGraph multi-agent execution thread."
)
async def process_consultation_endpoint(
    payload: ProcessConsultationRequest,
    background_tasks: BackgroundTasks
):
    """FastAPI endpoint to start consultation pipeline execution."""
    consultation_id = str(uuid.uuid4())
    initial_state = create_initial_state(
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        consultation_text=payload.consultation_text,
        audio_url=payload.audio_url
    )
    ACTIVE_CONSULTATIONS[consultation_id] = initial_state

    # Queue multi-agent graph execution in background task
    background_tasks.add_task(run_pipeline_task, consultation_id, initial_state)

    return ProcessConsultationResponse(
        consultation_id=consultation_id,
        status=ConsultationStatus.PROCESSING
    )


@api_router.get(
    "/consultation/{consultation_id}",
    status_code=status.HTTP_200_OK,
    summary="Fetch consultation state & pipeline status",
    description="Retrieves current execution state and status for a consultation thread."
)
async def get_consultation_status_endpoint(consultation_id: str):
    """FastAPI endpoint to poll consultation state and progress."""
    if consultation_id not in ACTIVE_CONSULTATIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation record '{consultation_id}' not found."
        )
    return ACTIVE_CONSULTATIONS[consultation_id]


@api_router.post(
    "/consultation/{consultation_id}/approve",
    response_model=ApproveConsultationResponse,
    status_code=status.HTTP_200_OK,
    summary="Physician approval & database persistence",
    description="Persists final approved clinical document to Supabase database and audit logs."
)
async def approve_consultation_endpoint(
    consultation_id: str,
    payload: ApproveConsultationRequest
):
    """FastAPI endpoint to handle physician approval, inline edit retention, and EHR persistence."""
    if consultation_id not in ACTIVE_CONSULTATIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation record '{consultation_id}' not found."
        )

    state = ACTIVE_CONSULTATIONS[consultation_id]

    # RLS Cross-Doctor Isolation Gate
    if state.get("doctor_id") != payload.doctor_id:
        logger.warning(f"RLS Violation: Doctor '{payload.doctor_id}' attempted to access consultation '{consultation_id}' owned by '{state.get('doctor_id')}'.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation record '{consultation_id}' not found."
        )

    patient_id = state.get("patient_id", "")
    doctor_edits = {
        "soap_note": payload.final_soap_note,
        "summary": payload.final_summary,
        "treatment_plan": payload.final_treatment_plan,
        "followup_plan": payload.final_followup_plan
    }

    try:
        db_res = save_approved_document(
            consultation_id=consultation_id,
            patient_id=patient_id,
            doctor_id=payload.doctor_id,
            soap_note=payload.final_soap_note,
            summary=payload.final_summary,
            treatment_plan=payload.final_treatment_plan,
            followup_plan=payload.final_followup_plan,
            doctor_edits=doctor_edits,
            doctor_notes=payload.doctor_notes
        )
        state["status"] = ConsultationStatus.APPROVED.value
        state["soap_note"] = payload.final_soap_note
        state["summary"] = payload.final_summary
        state["treatment_plan"] = payload.final_treatment_plan
        state["followup_plan"] = payload.final_followup_plan
        state["doctor_notes"] = payload.doctor_notes
        ACTIVE_CONSULTATIONS[consultation_id] = state

        return ApproveConsultationResponse(
            success=True,
            document_id=db_res["document_id"],
            status=ConsultationStatus.APPROVED,
            timestamp=db_res["timestamp"]
        )
    except Exception as exc:
        logger.error(f"Failed to persist approved document: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database outage error: {exc}. Edits preserved in active session."
        )


@api_router.post(
    "/consultation/{consultation_id}/reject",
    response_model=RejectConsultationResponse,
    status_code=status.HTTP_200_OK,
    summary="Physician rejection & audit trail",
    description="Marks consultation as REJECTED and logs rejection reason in audit trail without creating clinical document."
)
async def reject_consultation_endpoint(
    consultation_id: str,
    payload: RejectConsultationRequest
):
    """FastAPI endpoint to handle physician rejection and audit log persistence."""
    if consultation_id not in ACTIVE_CONSULTATIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation record '{consultation_id}' not found."
        )

    state = ACTIVE_CONSULTATIONS[consultation_id]

    # RLS Cross-Doctor Isolation Gate
    if state.get("doctor_id") != payload.doctor_id:
        logger.warning(f"RLS Violation: Doctor '{payload.doctor_id}' attempted to access consultation '{consultation_id}' owned by '{state.get('doctor_id')}'.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation record '{consultation_id}' not found."
        )

    try:
        db_res = save_rejected_consultation(
            consultation_id=consultation_id,
            doctor_id=payload.doctor_id,
            rejection_reason=payload.rejection_reason
        )
        state["status"] = ConsultationStatus.REJECTED.value
        ACTIVE_CONSULTATIONS[consultation_id] = state

        return RejectConsultationResponse(
            success=True,
            status=ConsultationStatus.REJECTED,
            timestamp=db_res["timestamp"]
        )
    except Exception as exc:
        logger.error(f"Failed to log rejected consultation: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database outage error: {exc}. Rejection state preserved in session."
        )
