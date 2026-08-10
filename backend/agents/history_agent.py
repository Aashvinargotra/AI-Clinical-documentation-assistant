import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("history_agent")

def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY.")
    return create_client(url, key)

def fetch_patient_history(patient_code: str) -> dict:
    """Queries Supabase for past EHR, chronic conditions, and allergies."""
    try:
        supabase = get_supabase_client()
        res = supabase.table("patients").select("*").eq("patient_code", patient_code).execute()
        if res.data:
            patient_record = res.data[0]
            return {
                "history": patient_record.get("history", {}),
                "allergies": patient_record.get("allergies", []),
                "chronic_conditions": patient_record.get("chronic_conditions", []),
                "current_medications": patient_record.get("current_medications", [])
            }
        else:
            logger.warning(f"Patient {patient_code} not found in database.")
            return None
    except Exception as exc:
        logger.error(f"Error fetching patient history: {exc}")
        return None
