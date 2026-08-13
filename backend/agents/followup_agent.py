"""Follow-up Coordinator Agent Node.

Formats recommended follow-up dates, diagnostic lab/imaging orders, and
patient-friendly home care instructions based on treatment plan and medical summary.
"""

import logging
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate

from backend.schemas.models import FollowupPlan
from backend.graph.state import MedicalState
from backend.tools.llm_provider import llm_rotator

logger = logging.getLogger("followup_agent")

FOLLOWUP_SYSTEM_PROMPT = """You are an expert Clinical Follow-up Coordinator.
Your task is to generate clear, structured follow-up instructions for patient discharge.

Rules:
1. Extract or recommend a specific follow-up timeframe or date (YYYY-MM-DD or timeframe like '1 week').
2. List any diagnostic tests, imaging, or lab work ordered by the doctor.
3. Write clear, patient-friendly home care instructions including warning signs for when to contact the clinic.
4. Respond in valid JSON format matching the schema.
"""


def generate_followup_plan(treatment_plan: Dict[str, Any], summary: Dict[str, Any]) -> FollowupPlan:
    """Generates a structured FollowupPlan object from treatment plan and medical summary."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", FOLLOWUP_SYSTEM_PROMPT),
        ("human", "Treatment Plan:\n{treatment_plan}\n\nMedical Summary:\n{summary}\n\nGenerate the structured follow-up plan in JSON format.")
    ])
    
    result: FollowupPlan = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={
            "treatment_plan": str(treatment_plan),
            "summary": str(summary)
        },
        schema_model=FollowupPlan
    )
    return result


def followup_coordinator_node(state: MedicalState) -> Dict[str, Any]:
    """LangGraph node execution function for Follow-up Coordinator Agent."""
    logger.info("Executing Follow-up Coordinator Agent node...")
    history = state.get("history", {})
    if history and history.get("patient_unresolved"):
        logger.warning("Follow-up Coordinator Agent skipped: patient_unresolved is True.")
        return {}
    treatment_plan = state.get("treatment_plan", {})
    summary = state.get("summary", {})
    
    followup_obj = generate_followup_plan(treatment_plan, summary)
    return {"followup_plan": followup_obj.model_dump()}
