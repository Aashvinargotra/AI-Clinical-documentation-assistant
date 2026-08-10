from langchain_core.prompts import ChatPromptTemplate
from backend.tools.llm_provider import llm_rotator
from backend.schemas.models import SOAPNote

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
