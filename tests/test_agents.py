"""Unit Test Suite for Specialized Clinical AI Agents & Safety Guardrails.

Tests agent contracts, non-prescriptive safety guardrails, and allergy contraindications.
"""

import pytest
from backend.agents.summary_agent import generate_medical_summary
from backend.agents.treatment_agent import generate_treatment_plan
from backend.schemas.models import MedicalSummary, TreatmentPlan


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
