"""Unit Test Suite for Specialized Clinical AI Agents & Safety Guardrails.

Tests agent contracts, non-prescriptive safety guardrails, allergy contraindications,
follow-up coordination, and documentation reviewer quality audits.
"""

import pytest
from backend.agents.summary_agent import generate_medical_summary
from backend.agents.treatment_agent import generate_treatment_plan
from backend.agents.followup_agent import generate_followup_plan
from backend.agents.reviewer import review_clinical_documentation
from backend.schemas.models import MedicalSummary, TreatmentPlan, FollowupPlan, ReviewResult
from backend.graph.state import create_initial_state


def test_medical_summary_generation():
    """Test Medical Summary Agent output synthesis."""
    soap_note = {
        "subjective": "Patient reports fever for 2 days.",
        "objective": "Temp 100.2 F.",
        "assessment": "Viral infection.",
        "plan": "Rest and fluids."
    }
    history = {"allergies": [], "chronic_conditions": []}

    summary = generate_medical_summary(soap_note, history)
    assert isinstance(summary, MedicalSummary)
    assert len(summary.chief_complaint) > 0
    assert len(summary.diagnosis) > 0


def test_treatment_plan_non_prescriptive_guardrail():
    """Test Treatment Planner introduces ZERO medications when none are mentioned in plan."""
    no_med_plan = "Advised rest, hydration, and steam inhalation. Follow up if symptoms worsen."
    treatment = generate_treatment_plan(no_med_plan, allergies=["Penicillin"])
    
    assert isinstance(treatment, TreatmentPlan)
    # Non-prescriptive guardrail mandate: zero unmentioned medications introduced
    assert len(treatment.medications) == 0


def test_treatment_plan_allergy_contraindication_flag():
    """Test Treatment Planner generates a warning flag when prescribed drug conflicts with allergy."""
    penicillin_plan = "Prescribe Penicillin VK 500mg QID for 10 days."
    history_allergies = ["Penicillin severe anaphylaxis"]

    treatment = generate_treatment_plan(penicillin_plan, allergies=history_allergies)
    assert isinstance(treatment, TreatmentPlan)
    # Verify contraindication warning is present in treatment summary
    assert "CONTRAINDICATION" in treatment.treatment_summary or "allergy" in treatment.treatment_summary.lower()


def test_followup_plan_generation():
    """Test Follow-up Coordinator Agent output generation."""
    treatment = {"treatment_summary": "Rest and OTC paracetamol."}
    summary = {"chief_complaint": "Fever", "diagnosis": "Viral URI"}

    followup = generate_followup_plan(treatment, summary)
    assert isinstance(followup, FollowupPlan)
    assert len(followup.patient_instructions) > 0


def test_reviewer_quality_audit():
    """Test Documentation Reviewer completeness scoring and allergy alerts."""
    state = create_initial_state(
        patient_id="P-98214",
        doctor_id="b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
        consultation_text="Patient presents with cough and fever. Diagnosed with acute bronchitis."
    )
    state["history"] = {"allergies": ["Penicillin severe anaphylaxis"]}
    state["soap_note"] = {
        "subjective": "Cough and fever.",
        "objective": "Temp 99.8F, BP 120/80. Lungs clear.",
        "assessment": "Acute bronchitis.",
        "plan": "Rest and hydration."
    }
    state["summary"] = {"chief_complaint": "Cough", "diagnosis": "Bronchitis", "key_findings": [], "discharge_summary": "Home care."}
    state["treatment_plan"] = {"treatment_summary": "Symptomatic care.", "medications": [], "monitoring_requirements": []}
    state["followup_plan"] = {"followup_date": "1 week", "tests_ordered": [], "patient_instructions": "Rest and drink fluids."}

    review = review_clinical_documentation(state)
    assert isinstance(review, ReviewResult)
    assert isinstance(review.passed_qc, bool)
    assert review.completeness_score >= 0.0
    # Verify allergy alert in warnings
    assert any("allergy" in w.lower() or "penicillin" in w.lower() for w in review.warnings)
