import sys
import os

# Ensure the root directory is on the path so we can import backend.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from backend.agents.history_agent import fetch_patient_history
from backend.agents.note_writer import generate_soap_note

def main():
    print("=== Testing Subphase 2.1 ===")
    
    # 1. Test History Agent
    patient_code = "P-98214"
    print(f"\n1. Fetching history for patient: {patient_code}")
    history = fetch_patient_history(patient_code)
    
    if history:
        print("Success! History fetched:")
        print(json.dumps(history, indent=2))
    else:
        print("Patient history not found or error occurred.")
        
    # 2. Test Note Writer Agent
    print("\n2. Generating SOAP note from test transcript...")
    test_transcript = "Patient complains of a severe headache and fever for the past 3 days. Diagnosed with a suspected viral infection. Advised rest, hydration, and prescribed Tylenol 500mg every 6 hours PRN."
    print(f"Transcript: {test_transcript}")
    
    try:
        soap_note = generate_soap_note(test_transcript)
        print("Success! Generated SOAP Note:")
        print(soap_note.model_dump_json(indent=2))
    except Exception as exc:
        print(f"Failed to generate SOAP note: {exc}")

if __name__ == "__main__":
    main()
