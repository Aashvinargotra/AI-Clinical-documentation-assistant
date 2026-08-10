"""Subphase 2.3 Verification Test Script.

Tests Follow-up Coordinator Agent and Documentation Reviewer Agent:
1. Follow-up plan generation.
2. Documentation Quality Reviewer audit (passed_qc, completeness score, warnings, ICD-10 suggestions).
"""

import sys
import os
import json

# Ensure root directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.followup_agent import generate_followup_plan
from backend.agents.reviewer import review_clinical_documentation
from backend.graph.state import create_initial_state


def test_subphase_2_3():
    print("==========================================================")
    print("         TESTING SUBPHASE 2.3: FOLLOW-UP & REVIEWER AGENTS")
    print("==========================================================")

    # -------------------------------------------------------------
    # 1. Test Follow-up Coordinator Agent
    # -------------------------------------------------------------
    print("\n1. Testing Follow-up Coordinator Agent...")
    sample_treatment = {
        "treatment_summary": "Hydration, rest, Acetaminophen 500mg Q6H PRN for fever.",
        "medications": [
            {"name": "Acetaminophen", "dosage": "500mg", "frequency": "Q6H PRN", "duration": "5 days"}
        ],
        "monitoring_requirements": ["Monitor body temperature twice daily"]
    }
    sample_summary = {
        "chief_complaint": "Cough and fever for 3 days",
        "diagnosis": "Viral Upper Respiratory Infection",
        "key_findings": ["Temp 99.8F", "Lungs clear bilaterally"],
        "discharge_summary": "Cleared for home care."
    }

    try:
        followup = generate_followup_plan(sample_treatment, sample_summary)
        print("[SUCCESS] Follow-up Plan Generated Successfully:")
        print(followup.model_dump_json(indent=2))
    except Exception as exc:
        print(f"[FAIL] Follow-up Coordinator Agent Failed: {exc}")

    # -------------------------------------------------------------
    # 2. Test Documentation Reviewer Agent Quality Audit
    # -------------------------------------------------------------
    print("\n2. Testing Documentation Reviewer Quality Audit & ICD-10 Suggestions...")
    state = create_initial_state(
        patient_id="P-98214",
        doctor_id="b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
        consultation_text="Patient complains of 3-day history of sharp cough and low-grade fever. Diagnosed with acute bronchitis."
    )
    state["history"] = {
        "allergies": ["Penicillin severe anaphylaxis"],
        "chronic_conditions": ["Hypertension"],
        "current_medications": ["Lisinopril 10mg QD"]
    }
    state["soap_note"] = {
        "subjective": "3-day sharp cough and fever.",
        "objective": "Temp 99.8F, BP 122/80. Lungs clear.",
        "assessment": "Acute bronchitis.",
        "plan": "Rest, hydration, OTC Acetaminophen."
    }
    state["summary"] = sample_summary
    state["treatment_plan"] = sample_treatment
    state["followup_plan"] = followup.model_dump() if 'followup' in locals() else {}

    try:
        review = review_clinical_documentation(state)
        print("[SUCCESS] Reviewer Audit Result Generated:")
        print(review.model_dump_json(indent=2))

        print(f"Passed QC: {review.passed_qc}")
        print(f"Completeness Score: {review.completeness_score}")
        print(f"Warnings / ICD-10 Suggestions: {review.warnings}")

        if review.passed_qc is True:
            print("[SUCCESS] REVIEWER AUDIT PASSED: Quality score >= 0.8!")
        else:
            print("[WARNING] Reviewer Audit flagged quality issues.")
    except Exception as exc:
        print(f"[FAIL] Documentation Reviewer Failed: {exc}")

    print("\n==========================================================")
    print("         SUBPHASE 2.3 VERIFICATION COMPLETE               ")
    print("==========================================================")


if __name__ == "__main__":
    test_subphase_2_3()
