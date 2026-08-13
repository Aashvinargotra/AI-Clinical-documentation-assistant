"""Medical Summary Agent Node.

Synthesizes chief complaint, confirmed diagnosis, key findings, and discharge summary
from the SOAP Note and historical EHR patient data.
"""

import logging
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate

from backend.schemas.models import MedicalSummary
from backend.graph.state import MedicalState
from backend.tools.llm_provider import llm_rotator

logger = logging.getLogger("summary_agent")

SUMMARY_SYSTEM_PROMPT = """You are an expert Medical Summary Agent.
Your task is to synthesize a structured medical summary combining the clinical SOAP note with patient history.

Rules:
1. Extract the primary chief complaint and confirmed/suspected diagnosis from the SOAP assessment.
2. Summarize key physical exam findings, lab results, and vitals as concise bullet points.
3. Formulate a clear, professional discharge summary for medical record documentation.
4. Respond in valid JSON format matching the schema.
"""


def generate_medical_summary(soap_note: Dict[str, Any], history: Dict[str, Any]) -> MedicalSummary:
    """Generates a structured MedicalSummary object from SOAP note and history."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUMMARY_SYSTEM_PROMPT),
        ("human", "SOAP Note:\n{soap_note}\n\nPatient History:\n{history}\n\nGenerate the structured medical summary in JSON format.")
    ])
    
    result: MedicalSummary = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={
            "soap_note": str(soap_note),
            "history": str(history)
        },
        schema_model=MedicalSummary
    )
    return result


def medical_summary_node(state: MedicalState) -> Dict[str, Any]:
    """LangGraph node execution function for Medical Summary Agent."""
    logger.info("Executing Medical Summary Agent node...")
    history = state.get("history", {})
    if history and history.get("patient_unresolved"):
        logger.warning("Medical Summary Agent skipped: patient_unresolved is True.")
        return {}
    soap_note = state.get("soap_note", {})
    
    summary_obj = generate_medical_summary(soap_note, history)
    return {"summary": summary_obj.model_dump()}
