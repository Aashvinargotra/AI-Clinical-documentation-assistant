"""Treatment Planner Agent Node with Non-Prescriptive Safety Guardrail.

Formats doctor-prescribed medications, dosages, frequencies, and monitoring orders.
STRICT NON-PRESCRIPTIVE GUARDRAIL: Only formats medications explicitly stated by the physician.
Never introduces unmentioned medications. Flags allergy contraindications against patient history.
"""

import logging
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate

from backend.schemas.models import TreatmentPlan
from backend.graph.state import MedicalState
from backend.tools.llm_provider import llm_rotator

logger = logging.getLogger("treatment_agent")

TREATMENT_SYSTEM_PROMPT = """You are a Clinical Treatment Formatting Assistant.

CRITICAL SAFETY MANDATE (STRICT NON-PRESCRIPTIVE GUARDRAIL):
1. You must ONLY format medications, dosages, frequencies, and durations EXPLICITLY stated by the attending physician in the SOAP plan or transcript.
2. You are STRICTLY FORBIDDEN from independently prescribing new medications, suggesting dosage changes, or adding drugs not explicitly mentioned by the doctor.
3. If the SOAP plan mentions NO medications, the 'medications' array MUST be empty ([]).
4. Cross-check formatted medications against patient historical allergies ({allergies}). If a potential allergy conflict or contraindication exists, include a prominent warning flag in 'treatment_summary'.
5. Respond in valid JSON format matching the schema.
"""


def generate_treatment_plan(soap_plan: str, allergies: List[str]) -> TreatmentPlan:
    """Generates a TreatmentPlan model while enforcing non-prescriptive safety guardrails."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", TREATMENT_SYSTEM_PROMPT),
        ("human", "SOAP Plan:\n{soap_plan}\n\nPatient Known Allergies:\n{allergies}\n\nFormat the treatment plan in valid JSON format.")
    ])
    
    result: TreatmentPlan = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={
            "soap_plan": soap_plan,
            "allergies": str(allergies)
        },
        schema_model=TreatmentPlan
    )
    
    # Programmatic Guardrail Post-Check: Flag allergy contraindication if LLM missed it
    if allergies and result.medications:
        for med in result.medications:
            med_name_lower = med.name.lower()
            for allergy in allergies:
                allergy_lower = allergy.lower()
                if med_name_lower in allergy_lower or any(word in allergy_lower for word in med_name_lower.split()):
                    warning_msg = f"⚠️ CONTRAINDICATION ALERT: Prescribed medication '{med.name}' conflicts with patient allergy '{allergy}'!"
                    if warning_msg not in result.treatment_summary:
                        result.treatment_summary = f"{warning_msg}\n{result.treatment_summary}"
                        logger.warning(warning_msg)
                        
    return result


def treatment_planner_node(state: MedicalState) -> Dict[str, Any]:
    """LangGraph node execution function for Treatment Planner Agent."""
    logger.info("Executing Treatment Planner Agent node...")
    history = state.get("history", {})
    if history and history.get("patient_unresolved"):
        logger.warning("Treatment Planner Agent skipped: patient_unresolved is True.")
        return {}
    soap_note = state.get("soap_note", {})
    
    soap_plan = soap_note.get("plan", "")
    allergies = history.get("allergies", [])
    
    treatment_obj = generate_treatment_plan(soap_plan, allergies)
    return {"treatment_plan": treatment_obj.model_dump()}
