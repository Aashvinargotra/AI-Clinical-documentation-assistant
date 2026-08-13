"""Supabase EHR Database Persistence & Audit Logging Module.

Handles database queries, row-level security (RLS) operations, document persistence,
rejection audit logging, and exponential retry wrappers for DB outage resilience.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from supabase import create_client, Client

load_dotenv()
logger = logging.getLogger("supabase_db")


def get_supabase_client() -> Client:
    """Instantiates Supabase client using environment credentials."""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key or url.startswith("your-") or key.startswith("your-"):
        raise RuntimeError("Missing or invalid SUPABASE_URL or SUPABASE_KEY in environment.")
    return create_client(url, key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4), reraise=True)
def save_approved_document(
    consultation_id: str,
    patient_id: str,
    doctor_id: str,
    soap_note: Dict[str, Any],
    summary: Dict[str, Any],
    treatment_plan: Dict[str, Any],
    followup_plan: Dict[str, Any],
    doctor_edits: Optional[Dict[str, Any]] = None,
    doctor_notes: Optional[str] = None
) -> Dict[str, Any]:
    """Persists approved clinical document to clinical_documents and logs audit entry.
    
    Wrapped with 3 exponential retries for database outage resilience.
    """
    doc_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        supabase = get_supabase_client()

        # 1. Insert row into clinical_documents table
        doc_row = {
            "id": doc_id,
            "consultation_id": consultation_id,
            "patient_id": patient_id,
            "soap_note": soap_note,
            "summary": summary,
            "treatment_plan": treatment_plan,
            "followup_plan": followup_plan,
            "doctor_edits": doctor_edits or {},
            "doctor_notes": doctor_notes
        }
        supabase.table("clinical_documents").insert(doc_row).execute()

        # 2. Insert row into audit_logs table
        audit_row = {
            "id": str(uuid.uuid4()),
            "doctor_id": doctor_id,
            "action": "DOCUMENT_APPROVED",
            "consultation_id": consultation_id,
            "metadata": {
                "doctor_notes": doctor_notes,
                "edited_fields": list((doctor_edits or {}).keys())
            }
        }
        supabase.table("audit_logs").insert(audit_row).execute()

        # 3. Update status in consultations table if present
        try:
            supabase.table("consultations").update({
                "status": "APPROVED",
                "approved_at": timestamp
            }).eq("id", consultation_id).execute()
        except Exception:
            pass

        logger.info(f"Successfully persisted approved document {doc_id} for consultation {consultation_id}.")
        return {
            "success": True,
            "document_id": doc_id,
            "status": "APPROVED",
            "timestamp": timestamp
        }

    except Exception as exc:
        logger.error(f"Error persisting approved document to Supabase: {exc}")
        raise exc


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4), reraise=True)
def save_rejected_consultation(
    consultation_id: str,
    doctor_id: str,
    rejection_reason: str
) -> Dict[str, Any]:
    """Updates consultation status to REJECTED and logs rejection reason in audit_logs.
    
    Does NOT write any row to clinical_documents.
    Wrapped with 3 exponential retries for database outage resilience.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        supabase = get_supabase_client()

        # 1. Update consultations table status to REJECTED
        try:
            supabase.table("consultations").update({"status": "REJECTED"}).eq("id", consultation_id).execute()
        except Exception:
            pass

        # 2. Insert rejection row into audit_logs table
        audit_row = {
            "id": str(uuid.uuid4()),
            "doctor_id": doctor_id,
            "action": "DOCUMENT_REJECTED",
            "consultation_id": consultation_id,
            "metadata": {
                "rejection_reason": rejection_reason
            }
        }
        supabase.table("audit_logs").insert(audit_row).execute()

        logger.info(f"Successfully logged rejection audit trail for consultation {consultation_id}.")
        return {
            "success": True,
            "status": "REJECTED",
            "timestamp": timestamp
        }

    except Exception as exc:
        logger.error(f"Error logging rejected consultation to Supabase: {exc}")
        raise exc
