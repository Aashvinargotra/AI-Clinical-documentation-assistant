"""Unit Test Suite for Pydantic Models & MedicalState TypedDict.

Tests schema serialization, field constraints, status enums, and initial state creation.
"""

import pytest
from backend.schemas.models import (
    ConsultationStatus,
    SOAPNote,
    MedicalSummary,
    MedicationOrder,
    TreatmentPlan,
    FollowupPlan,
    ReviewResult,
    ProcessConsultationRequest,
    ApproveConsultationRequest,
    RejectConsultationRequest
)
from backend.graph.state import MedicalState, create_initial_state


def test_consultation_status_enum():
    """Test ConsultationStatus canonical enum values."""
    assert ConsultationStatus.DRAFT.value == "DRAFT"
    assert ConsultationStatus.PROCESSING.value == "PROCESSING"
    assert ConsultationStatus.AWAITING_APPROVAL.value == "AWAITING_APPROVAL"
    assert ConsultationStatus.APPROVED.value == "APPROVED"
    assert ConsultationStatus.REJECTED.value == "REJECTED"
    assert ConsultationStatus.FAILED.value == "FAILED"


def test_soap_note_schema():
    """Test SOAPNote Pydantic model validation and serialization."""
    data = {
        "subjective": "Patient reports cough for 3 days.",
        "objective": "Temp 99.8F, HR 72, BP 120/80.",
        "assessment": "Acute viral URI.",
        "plan": "Rest, hydration, OTC acetaminophen."
    }
    soap = SOAPNote(**data)
    assert soap.subjective == data["subjective"]
    assert soap.objective == data["objective"]
    assert soap.assessment == data["assessment"]
    assert soap.plan == data["plan"]
    assert soap.model_dump() == data


def test_medical_summary_schema():
    """Test MedicalSummary Pydantic model validation."""
    summary = MedicalSummary(
        chief_complaint="Cough and fever",
        diagnosis="Viral Upper Respiratory Infection",
        key_findings=["No lung wheezing", "Afebrile at exam"],
        discharge_summary="Cleared for outpatient home care."
    )
    assert summary.diagnosis == "Viral Upper Respiratory Infection"
    assert len(summary.key_findings) == 2


def test_treatment_plan_schema():
    """Test TreatmentPlan Pydantic model with MedicationOrder list."""
    med = MedicationOrder(
        name="Acetaminophen",
        dosage="500mg",
        frequency="Q6H PRN",
        duration="5 days"
    )
    treatment = TreatmentPlan(
        treatment_summary="Symptomatic relief.",
        medications=[med],
        monitoring_requirements=["Monitor temperature twice daily"]
    )
    assert len(treatment.medications) == 1
    assert treatment.medications[0].name == "Acetaminophen"


def test_review_result_schema():
    """Test ReviewResult model including passed_qc flag and warnings."""
    result = ReviewResult(
        passed_qc=True,
        completeness_score=0.95,
        issues=[],
        warnings=["ICD-10 suggestion: J20.9 (Acute Bronchitis)"]
    )
    assert result.passed_qc is True
    assert "ICD-10 suggestion" in result.warnings[0]


def test_api_request_models():
    """Test API endpoint request Pydantic models."""
    process_req = ProcessConsultationRequest(
        patient_id="P-98214",
        doctor_id="b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
        consultation_text="Patient presents with fever..."
    )
    assert process_req.patient_id == "P-98214"
    assert process_req.audio_url is None

    reject_req = RejectConsultationRequest(
        doctor_id="b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
        rejection_reason="Inaccurate dictation transcript."
    )
    assert reject_req.rejection_reason == "Inaccurate dictation transcript."


def test_medical_state_typed_dict_creation():
    """Test MedicalState TypedDict helper function."""
    state: MedicalState = create_initial_state(
        patient_id="P-98214",
        doctor_id="b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
        consultation_text="Patient reports cough..."
    )
    assert state["patient_id"] == "P-98214"
    assert state["doctor_id"] == "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e"
    assert state["status"] == ConsultationStatus.PROCESSING.value
    assert isinstance(state["history"], dict)
    assert isinstance(state["soap_note"], dict)
    assert state["review_result"]["passed_qc"] is False
