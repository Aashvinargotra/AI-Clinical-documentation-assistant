"""Unit & Integration Test Suite for FastAPI REST API Endpoints.

Tests audio transcription (/api/v1/transcribe), Whisper error fallback, consultation processing
(/api/v1/consultation/process), status polling (/api/v1/consultation/{id}), doctor approval (/approve),
doctor rejection (/reject), cross-doctor RLS isolation gate, and DB outage 503 error handling.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Test /health API health check route."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"


@patch("backend.api.endpoints.transcribe_audio_file")
def test_transcribe_audio_endpoint(mock_transcribe):
    """Test POST /api/v1/transcribe audio file upload endpoint."""
    mock_transcribe.return_value = {
        "transcript": "Doctor: Good morning John. How is your knee feeling today?",
        "duration_seconds": 15.0
    }

    fake_audio_content = b"RIFF....WAVEfmt ....data...."
    files = {"file": ("test_dictation.wav", fake_audio_content, "audio/wav")}

    response = client.post("/api/v1/transcribe", files=files)

    assert response.status_code == 200
    data = response.json()
    assert "transcript" in data
    assert "Doctor: Good morning John" in data["transcript"]
    assert data["duration_seconds"] == 15.0


def test_whisper_error_fallback():
    """Test Whisper Failure Fallback when uploading a corrupted or invalid audio file."""
    corrupted_content = b"CORRUPTED_NOT_AUDIO_DATA_12345"
    files = {"file": ("corrupted.xyz", corrupted_content, "application/octet-stream")}

    response = client.post("/api/v1/transcribe", files=files)

    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert len(detail) > 0


@patch("backend.api.endpoints.run_pipeline_task")
def test_process_consultation_endpoint(mock_run_pipeline):
    """Test POST /api/v1/consultation/process endpoint initializing consultation state."""
    payload = {
        "patient_id": "P-98214",
        "doctor_id": "doc-test-123",
        "consultation_text": "Patient presents with sharp cough and fever for 2 days."
    }

    response = client.post("/api/v1/consultation/process", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "consultation_id" in data
    assert len(data["consultation_id"]) > 10
    assert data["status"] == "PROCESSING"


@patch("backend.api.endpoints.run_pipeline_task")
def test_get_consultation_status_endpoint(mock_run_pipeline):
    """Test GET /api/v1/consultation/{consultation_id} status polling endpoint."""
    payload = {
        "patient_id": "P-98214",
        "doctor_id": "doc-test-456",
        "consultation_text": "Patient complains of headache and fatigue."
    }

    post_res = client.post("/api/v1/consultation/process", json=payload)
    consultation_id = post_res.json()["consultation_id"]

    get_res = client.get(f"/api/v1/consultation/{consultation_id}")

    assert get_res.status_code == 200
    state = get_res.json()
    assert state["patient_id"] == "P-98214"
    assert state["doctor_id"] == "doc-test-456"
    assert state["status"] in ["PROCESSING", "AWAITING_APPROVAL"]
    assert "soap_note" in state
    assert "history" in state


def test_consultation_not_found_404():
    """Test GET /api/v1/consultation/{id} returns HTTP 404 for invalid consultation UUID."""
    response = client.get("/api/v1/consultation/non-existent-uuid-999")
    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


@patch("backend.api.endpoints.run_pipeline_task")
@patch("backend.api.endpoints.save_approved_document")
def test_approval_persistence(mock_save_approved, mock_run_pipeline):
    """Test POST /api/v1/consultation/{id}/approve persisting clinical document to EHR."""
    mock_save_approved.return_value = {
        "success": True,
        "document_id": "doc-approved-uuid-101",
        "status": "APPROVED",
        "timestamp": "2026-08-13T22:00:00Z"
    }

    # 1. Initialize consultation
    proc_res = client.post("/api/v1/consultation/process", json={
        "patient_id": "P-98214",
        "doctor_id": "doc-doctor-A",
        "consultation_text": "Patient has bronchitis."
    })
    cid = proc_res.json()["consultation_id"]

    # 2. Approve consultation
    approve_payload = {
        "doctor_id": "doc-doctor-A",
        "final_soap_note": {"subjective": "Subj", "objective": "Obj", "assessment": "Bronchitis", "plan": "Rest"},
        "final_summary": {"chief_complaint": "Cough", "diagnosis": "Bronchitis", "key_findings": [], "discharge_summary": "Home"},
        "final_treatment_plan": {"treatment_summary": "Rest", "medications": [], "monitoring_requirements": []},
        "final_followup_plan": {"followup_date": "1 week", "tests_ordered": [], "patient_instructions": "Drink fluids"},
        "doctor_notes": "Reviewed and approved by physician."
    }

    app_res = client.post(f"/api/v1/consultation/{cid}/approve", json=approve_payload)

    assert app_res.status_code == 200
    data = app_res.json()
    assert data["success"] is True
    assert data["status"] == "APPROVED"
    assert data["document_id"] == "doc-approved-uuid-101"
    mock_save_approved.assert_called_once()


@patch("backend.api.endpoints.run_pipeline_task")
@patch("backend.api.endpoints.save_rejected_consultation")
def test_rejection_audit_trail(mock_save_rejected, mock_run_pipeline):
    """Test POST /api/v1/consultation/{id}/reject logging rejection audit entry without clinical document."""
    mock_save_rejected.return_value = {
        "success": True,
        "status": "REJECTED",
        "timestamp": "2026-08-13T22:00:00Z"
    }

    # 1. Initialize consultation
    proc_res = client.post("/api/v1/consultation/process", json={
        "patient_id": "P-98214",
        "doctor_id": "doc-doctor-A",
        "consultation_text": "Patient has mild cold."
    })
    cid = proc_res.json()["consultation_id"]

    # 2. Reject consultation
    reject_payload = {
        "doctor_id": "doc-doctor-A",
        "rejection_reason": "Inaccurate audio transcript uploaded."
    }

    rej_res = client.post(f"/api/v1/consultation/{cid}/reject", json=reject_payload)

    assert rej_res.status_code == 200
    data = rej_res.json()
    assert data["success"] is True
    assert data["status"] == "REJECTED"
    mock_save_rejected.assert_called_once()


@patch("backend.api.endpoints.run_pipeline_task")
def test_rls_cross_doctor_isolation(mock_run_pipeline):
    """Test Cross-Doctor RLS Isolation Gate (Doctor A receives 404 when attempting to access Doctor B's ID)."""
    # Initialize consultation owned by Doctor A
    proc_res = client.post("/api/v1/consultation/process", json={
        "patient_id": "P-98214",
        "doctor_id": "doc-Doctor-A",
        "consultation_text": "Doctor A consultation text."
    })
    cid = proc_res.json()["consultation_id"]

    # Unauthorized Doctor B attempts to approve Doctor A's consultation
    unauthorized_payload = {
        "doctor_id": "doc-Doctor-B",  # Unauthorized physician
        "final_soap_note": {},
        "final_summary": {},
        "final_treatment_plan": {},
        "final_followup_plan": {}
    }

    response = client.post(f"/api/v1/consultation/{cid}/approve", json=unauthorized_payload)

    # Must return HTTP 404 Not Found to enforce RLS isolation gate
    assert response.status_code == 404


@patch("backend.api.endpoints.run_pipeline_task")
@patch("backend.api.endpoints.save_approved_document")
def test_db_outage_503(mock_save_approved, mock_run_pipeline):
    """Test Supabase DB Outage retry failure returning HTTP 503 Service Unavailable."""
    mock_save_approved.side_effect = Exception("Supabase connection timeout / DB outage")

    proc_res = client.post("/api/v1/consultation/process", json={
        "patient_id": "P-98214",
        "doctor_id": "doc-doctor-A",
        "consultation_text": "Consultation text during DB outage."
    })
    cid = proc_res.json()["consultation_id"]

    approve_payload = {
        "doctor_id": "doc-doctor-A",
        "final_soap_note": {},
        "final_summary": {},
        "final_treatment_plan": {},
        "final_followup_plan": {}
    }

    response = client.post(f"/api/v1/consultation/{cid}/approve", json=approve_payload)

    # Must return HTTP 503 Service Unavailable
    assert response.status_code == 503
    assert "database outage error" in response.json().get("detail", "").lower()
