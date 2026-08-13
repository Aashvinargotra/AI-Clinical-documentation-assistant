import logging
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from backend.tools.llm_provider import llm_rotator
from backend.schemas.models import SOAPNote
from backend.graph.state import MedicalState

logger = logging.getLogger("note_writer")


def generate_soap_note(transcript: str) -> SOAPNote:
    """Generates a structured SOAP note from a raw medical transcript."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert clinical documentation assistant. Given a raw transcript of a doctor-patient consultation, generate a formal SOAP note following strict clinical guidelines. Respond in valid JSON format."),
        ("user", "Transcript:\n{transcript}\n\nGenerate the structured SOAP note in JSON format.")
    ])
    
    result = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={"transcript": transcript},
        schema_model=SOAPNote
    )
    return result


def clinical_note_writer_node(state: MedicalState) -> Dict[str, Any]:
    """LangGraph node execution function for Note Writer Agent."""
    logger.info("Executing Note Writer Agent node...")
    consultation_text = state.get("consultation_text", "")
    soap_obj = generate_soap_note(consultation_text)
    return {"soap_note": soap_obj.model_dump()}

