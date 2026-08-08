"""MedicalState TypedDict Definition.

This file is the EXCLUSIVE home for the MedicalState TypedDict representation used
by the LangGraph multi-agent state machine. It contains input parameters, historical EHR context,
generated agent outputs, human review state, and workflow execution metadata.
"""

from typing import TypedDict, List, Dict, Any, Optional
from backend.schemas.models import ConsultationStatus


class PatientHistoryData(TypedDict, total=False):
    allergies: List[str]
    chronic_conditions: List[str]
    current_medications: List[str]
    risk_flags: List[str]
    patient_unresolved: Optional[bool]


class SOAPNoteData(TypedDict, total=False):
    subjective: str
    objective: str
    assessment: str
    plan: str


class SummaryData(TypedDict, total=False):
    chief_complaint: str
    diagnosis: str
    key_findings: List[str]
    discharge_summary: str


class MedicationOrderData(TypedDict, total=False):
    name: str
    dosage: str
    frequency: str
    duration: str


class TreatmentPlanData(TypedDict, total=False):
    treatment_summary: str
    medications: List[MedicationOrderData]
    monitoring_requirements: List[str]


class FollowupPlanData(TypedDict, total=False):
    followup_date: str
    tests_ordered: List[str]
    patient_instructions: str


class ReviewResultData(TypedDict, total=False):
    passed_qc: bool
    completeness_score: float
    issues: List[str]
    warnings: List[str]


class MedicalState(TypedDict, total=False):
    """Shared state graph object passed across all 6 LangGraph agent nodes."""
    
    # Input parameters
    patient_id: str
    doctor_id: str
    consultation_text: str
    audio_url: Optional[str]
    
    # Agent outputs
    history: PatientHistoryData
    soap_note: SOAPNoteData
    summary: SummaryData
    treatment_plan: TreatmentPlanData
    followup_plan: FollowupPlanData
    review_result: ReviewResultData
    
    # Workflow & Human-in-the-Loop state
    status: str  # ConsultationStatus enum value
    doctor_edits: Optional[Dict[str, Any]]
    doctor_notes: Optional[str]
    error_logs: List[str]


def create_initial_state(
    patient_id: str,
    doctor_id: str,
    consultation_text: str,
    audio_url: Optional[str] = None
) -> MedicalState:
    """Helper function to create a clean, default MedicalState dictionary."""
    return {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "consultation_text": consultation_text,
        "audio_url": audio_url,
        "history": {
            "allergies": [],
            "chronic_conditions": [],
            "current_medications": [],
            "risk_flags": []
        },
        "soap_note": {
            "subjective": "",
            "objective": "",
            "assessment": "",
            "plan": ""
        },
        "summary": {
            "chief_complaint": "",
            "diagnosis": "",
            "key_findings": [],
            "discharge_summary": ""
        },
        "treatment_plan": {
            "treatment_summary": "",
            "medications": [],
            "monitoring_requirements": []
        },
        "followup_plan": {
            "followup_date": "",
            "tests_ordered": [],
            "patient_instructions": ""
        },
        "review_result": {
            "passed_qc": False,
            "completeness_score": 0.0,
            "issues": [],
            "warnings": []
        },
        "status": ConsultationStatus.PROCESSING.value,
        "doctor_edits": {},
        "doctor_notes": None,
        "error_logs": []
    }
