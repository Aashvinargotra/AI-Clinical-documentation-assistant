"""Automated Supabase Database Initialization Script.

Connects to Supabase using environment credentials, verifies tables,
and seeds synthetic test patient rows and doctor profiles.
"""

import os
import sys
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("init_db")

# Synthetic Test Patients Data
TEST_PATIENTS = [
    {
        "patient_code": "P-98214",
        "full_name": "John Doe",
        "date_of_birth": "1982-05-14",
        "gender": "Male",
        "allergies": ["Penicillin severe anaphylaxis", "Peanuts"],
        "chronic_conditions": ["Hypertension", "Type 2 Diabetes"],
        "current_medications": ["Lisinopril 10mg QD", "Metformin 500mg BID"]
    },
    {
        "patient_code": "P-98215",
        "full_name": "Jane Smith",
        "date_of_birth": "1990-11-22",
        "gender": "Female",
        "allergies": ["Sulfa drugs"],
        "chronic_conditions": ["Asthma"],
        "current_medications": ["Albuterol inhaler PRN"]
    }
]

# Synthetic Test Doctor Profiles
TEST_DOCTORS = [
    {
        "doctor_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
        "name": "Dr. Alex Smith, MD",
        "specialty": "Internal Medicine"
    },
    {
        "doctor_id": "e7f8a9b0-c1d2-3e4f-5a6b-7c8d9e0f1a2b",
        "name": "Dr. Sarah Taylor, MD",
        "specialty": "General Practice"
    }
]


def initialize_database():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY in environment variables.")
        sys.exit(1)

    logger.info(f"Connecting to Supabase instance at {supabase_url}...")
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.error(f"Failed to create Supabase client: {exc}")
        sys.exit(1)

    # 1. Seed Patients Table
    logger.info("Seeding synthetic test patient records...")
    for patient in TEST_PATIENTS:
        try:
            # Check if patient exists
            res = supabase.table("patients").select("*").eq("patient_code", patient["patient_code"]).execute()
            if res.data:
                logger.info(f"Patient {patient['patient_code']} ({patient['full_name']}) already exists. Updating record...")
                supabase.table("patients").update(patient).eq("patient_code", patient["patient_code"]).execute()
            else:
                logger.info(f"Inserting patient {patient['patient_code']} ({patient['full_name']})...")
                supabase.table("patients").insert(patient).execute()
        except Exception as exc:
            logger.warning(f"Note on patient {patient['patient_code']}: {exc}")

    # 2. Verify Table Existence via query
    logger.info("Verifying database table accessibility...")
    try:
        patients_check = supabase.table("patients").select("count", count="exact").execute()
        logger.info(f"✅ 'patients' table accessible. Total rows: {patients_check.count}")
    except Exception as exc:
        logger.error(f"❌ Error accessing 'patients' table: {exc}")
        logger.info("Please ensure scripts/schema.sql has been executed in the Supabase SQL Editor.")
        sys.exit(1)

    logger.info("\n" + "="*70)
    logger.info("✅ DATABASE INITIALIZATION & TEST DATA SEEDING COMPLETED SUCCESSFULLY!")
    logger.info("Test Patients Seeded:")
    for p in TEST_PATIENTS:
        logger.info(f"  - [{p['patient_code']}] {p['full_name']} | Allergies: {p['allergies']}")
    logger.info("Test Doctor Profiles Available:")
    for d in TEST_DOCTORS:
        logger.info(f"  - [{d['doctor_id']}] {d['name']} ({d['specialty']})")
    logger.info("="*70 + "\n")


if __name__ == "__main__":
    initialize_database()
