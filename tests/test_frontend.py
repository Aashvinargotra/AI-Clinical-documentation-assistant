"""Unit Test Suite for Streamlit UI Helpers & Patient Lookup Functions.

Tests patient lookup for P-98214, demographic cards, allergy badges, pipeline progress calculation,
stage checklist status codes, and approval/rejection payload formatting.
"""

import pytest
from frontend.streamlit_app import lookup_patient_record, calculate_pipeline_progress, PATIENT_DIRECTORY
from backend.schemas.models import ApproveConsultationRequest, RejectConsultationRequest


def test_patient_lookup_existing():
    """Test looking up existing patient code P-98214."""
    patient = lookup_patient_record("P-98214")
    assert patient is not None
    assert patient["patient_code"] == "P-98214"
    assert patient["full_name"] == "John Doe"
    assert patient["dob"] == "1982-05-14"
    assert "Penicillin" in patient["allergies"]
    assert "Hypertension" in patient["chronic_conditions"]


def test_patient_lookup_case_insensitive():
    """Test patient lookup is case-insensitive (e.g. p-98214)."""
    patient = lookup_patient_record("p-98214")
    assert patient is not None
    assert patient["full_name"] == "John Doe"


def test_patient_directory_contents():
    """Verify PATIENT_DIRECTORY dictionary contains valid patient records."""
    assert "P-98214" in PATIENT_DIRECTORY
    assert "P-45120" in PATIENT_DIRECTORY
    assert "P-10982" in PATIENT_DIRECTORY
    assert PATIENT_DIRECTORY["P-98214"]["allergies"] == ["Penicillin"]


def test_pipeline_progress_calculation():
    """Test calculate_pipeline_progress progress percentage and agent status stages."""
    pct, statuses = calculate_pipeline_progress({})
    assert pct == 0
    assert statuses["history"] == "PENDING"

    partial_state = {
        "history": {"allergies": ["Penicillin"]},
        "soap_note": {"subjective": "Subj", "assessment": "Bronchitis"}
    }
    pct_partial, statuses_partial = calculate_pipeline_progress(partial_state)
    assert pct_partial == 33
    assert statuses_partial["history"] == "COMPLETED"
    assert statuses_partial["soap_note"] == "COMPLETED"
    assert statuses_partial["summary_agent"] == "RUNNING"

    complete_state = {
        "history": {"allergies": ["Penicillin"]},
        "soap_note": {"assessment": "Bronchitis"},
        "summary": {"diagnosis": "Acute Bronchitis"},
        "treatment_plan": {"treatment_summary": "Rest"},
        "followup_plan": {"patient_instructions": "Rest and fluids"},
        "review_result": {"completeness_score": 95}
    }
    pct_full, statuses_full = calculate_pipeline_progress(complete_state)
    assert pct_full == 100
    assert all(status == "COMPLETED" for status in statuses_full.values())


def test_screen3_approval_payload_formatting():
    """Verify Screen 3 approval and rejection payload Pydantic models validation."""
    approve_data = {
        "doctor_id": "doc-test-123",
        "final_soap_note": {"subjective": "Subj", "objective": "Obj", "assessment": "Bronchitis", "plan": "Rest"},
        "final_summary": {"chief_complaint": "Cough", "diagnosis": "Bronchitis", "key_findings": [], "discharge_summary": "Home"},
        "final_treatment_plan": {"treatment_summary": "Rest", "medications": [], "monitoring_requirements": []},
        "final_followup_plan": {"followup_date": "1 week", "tests_ordered": [], "patient_instructions": "Rest"},
        "doctor_notes": "Reviewed and approved."
    }

    req = ApproveConsultationRequest(**approve_data)
    assert req.doctor_id == "doc-test-123"
    assert req.final_soap_note["assessment"] == "Bronchitis"

    reject_data = {
        "doctor_id": "doc-test-123",
        "rejection_reason": "Inaccurate audio transcript uploaded."
    }

    rej_req = RejectConsultationRequest(**reject_data)
    assert rej_req.doctor_id == "doc-test-123"
    assert rej_req.rejection_reason == "Inaccurate audio transcript uploaded."
