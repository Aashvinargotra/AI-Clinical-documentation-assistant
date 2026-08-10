"""Documentation Reviewer Agent Node.

Performs automated clinical documentation quality audit, completeness scoring,
safety cross-checks, missing field detection, and ICD-10 diagnostic coding suggestions.
"""

import logging
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate

from backend.schemas.models import ReviewResult
from backend.graph.state import MedicalState
from backend.tools.llm_provider import llm_rotator

logger = logging.getLogger("reviewer_agent")

REVIEWER_SYSTEM_PROMPT = """You are an expert Clinical Documentation Quality & Safety Auditor.
Your task is to review the complete generated medical record and evaluate its clinical completeness, accuracy, and safety.

Audit Tasks:
1. Evaluate completeness score (0.0 to 1.0). Set passed_qc = true if score >= 0.8 and no critical errors exist.
2. Flag any missing SOAP fields, unaddressed patient risk flags, or unmentioned clinical findings in 'issues'.
3. Include allergy warnings, clinical alerts, and relevant ICD-10 diagnostic coding suggestions in 'warnings' (e.g., 'ICD-10 suggestion: J20.9 (Acute Bronchitis)').
4. Respond in valid JSON format matching the schema.
"""


def review_clinical_documentation(state: MedicalState) -> ReviewResult:
    """Performs documentation review, quality audit, and ICD-10 suggestions."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", REVIEWER_SYSTEM_PROMPT),
        ("human", "Complete Medical Record State:\n{medical_state}\n\nPerform documentation review and return audit result in JSON format.")
    ])
    
    # Extract serializable representation of state
    state_str = str({
        "consultation_text": state.get("consultation_text", ""),
        "history": state.get("history", {}),
        "soap_note": state.get("soap_note", {}),
        "summary": state.get("summary", {}),
        "treatment_plan": state.get("treatment_plan", {}),
        "followup_plan": state.get("followup_plan", {})
    })

    result: ReviewResult = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={"medical_state": state_str},
        schema_model=ReviewResult
    )
    
    # Programmatic Post-Check: Ensure allergy alerts from history are present in warnings
    allergies = state.get("history", {}).get("allergies", [])
    if allergies:
        for allergy in allergies:
            allergy_alert = f"[ALERT] Allergy Alert in History: Patient has documented allergy to '{allergy}'."
            if not any(allergy.lower() in w.lower() for w in result.warnings):
                result.warnings.append(allergy_alert)

    return result


def documentation_reviewer_node(state: MedicalState) -> Dict[str, Any]:
    """LangGraph node execution function for Documentation Reviewer Agent."""
    logger.info("Executing Documentation Reviewer Agent node...")
    review_obj = review_clinical_documentation(state)
    return {"review_result": review_obj.model_dump()}
