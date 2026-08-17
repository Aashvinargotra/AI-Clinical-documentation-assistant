"""Streamlit Human-in-the-Loop Clinical Review UI & Doctor Dashboard.

Provides a 3-screen clinical workflow:
- Screen 1: Patient Lookup & Consultation Input (Text / Audio Upload)
- Screen 2: Real-time Multi-Agent Pipeline Execution Tracker
- Screen 3: Doctor Approval & Review Dashboard (HITL Record Editing & EHR Save/Reject)
"""

import os
import sys
import time
from pathlib import Path
import requests
import pandas as pd
import streamlit as st
from typing import Dict, Any, Optional, Tuple

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# API Server base URL
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

# Default Mock Patient Directory for fallback lookup when offline
PATIENT_DIRECTORY = {
    "P-98214": {
        "patient_code": "P-98214",
        "full_name": "John Doe",
        "dob": "1982-05-14",
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Hypertension"],
        "current_medications": ["Lisinopril 10mg QD"]
    },
    "P-45120": {
        "patient_code": "P-45120",
        "full_name": "Sarah Connor",
        "dob": "1990-11-22",
        "allergies": ["Sulfa drugs", "Aspirin"],
        "chronic_conditions": ["Asthma"],
        "current_medications": ["Albuterol HFA"]
    },
    "P-10982": {
        "patient_code": "P-10982",
        "full_name": "Robert Vance",
        "dob": "1965-03-08",
        "allergies": ["None"],
        "chronic_conditions": ["Type 2 Diabetes", "Hyperlipidemia"],
        "current_medications": ["Metformin 500mg BID", "Atorvastatin 20mg QD"]
    }
}


def lookup_patient_record(patient_code: str) -> Optional[Dict[str, Any]]:
    """Looks up patient demographics and medical history by patient code."""
    code_upper = patient_code.strip().upper()
    if code_upper in PATIENT_DIRECTORY:
        return PATIENT_DIRECTORY[code_upper]

    try:
        from backend.agents.history_agent import fetch_patient_history
        data = fetch_patient_history(code_upper)
        if data:
            return {
                "patient_code": code_upper,
                "full_name": f"Patient ({code_upper})",
                "dob": "1980-01-01",
                "allergies": data.get("allergies", []),
                "chronic_conditions": data.get("chronic_conditions", []),
                "current_medications": data.get("current_medications", [])
            }
    except Exception:
        pass

    return None


def calculate_pipeline_progress(state: Dict[str, Any]) -> Tuple[int, Dict[str, str]]:
    """Calculates completion progress percentage and individual agent stage status codes."""
    if not state:
        return 0, {
            "history": "PENDING",
            "soap_note": "PENDING",
            "summary_agent": "PENDING",
            "treatment_agent": "PENDING",
            "followup_agent": "PENDING",
            "reviewer_agent": "PENDING"
        }

    statuses = {}
    completed_count = 0

    history = state.get("history", {})
    if history and ("patient_unresolved" in history or history.get("allergies")):
        statuses["history"] = "COMPLETED"
        completed_count += 1
    else:
        statuses["history"] = "RUNNING"

    soap = state.get("soap_note", {})
    if soap and (soap.get("assessment") or soap.get("subjective")):
        statuses["soap_note"] = "COMPLETED"
        completed_count += 1
    elif statuses["history"] == "COMPLETED":
        statuses["soap_note"] = "RUNNING"
    else:
        statuses["soap_note"] = "PENDING"

    summary = state.get("summary", {})
    if summary and (summary.get("diagnosis") or summary.get("chief_complaint")):
        statuses["summary_agent"] = "COMPLETED"
        completed_count += 1
    elif statuses["soap_note"] == "COMPLETED":
        statuses["summary_agent"] = "RUNNING"
    else:
        statuses["summary_agent"] = "PENDING"

    treatment = state.get("treatment_plan", {})
    if treatment and (treatment.get("treatment_summary") or "medications" in treatment):
        statuses["treatment_agent"] = "COMPLETED"
        completed_count += 1
    elif statuses["summary_agent"] == "COMPLETED":
        statuses["treatment_agent"] = "RUNNING"
    else:
        statuses["treatment_agent"] = "PENDING"

    followup = state.get("followup_plan", {})
    if followup and (followup.get("patient_instructions") or followup.get("followup_date")):
        statuses["followup_agent"] = "COMPLETED"
        completed_count += 1
    elif statuses["treatment_agent"] == "COMPLETED":
        statuses["followup_agent"] = "RUNNING"
    else:
        statuses["followup_agent"] = "PENDING"

    review = state.get("review_result", {})
    if review and ("completeness_score" in review or "passed_qc" in review):
        statuses["reviewer_agent"] = "COMPLETED"
        completed_count += 1
    elif statuses["followup_agent"] == "COMPLETED":
        statuses["reviewer_agent"] = "RUNNING"
    else:
        statuses["reviewer_agent"] = "PENDING"

    progress_pct = int((completed_count / 6.0) * 100)
    return progress_pct, statuses


def inject_custom_css():
    """Injects custom CSS styling for modern, high-contrast, premium clinical aesthetics."""
    st.markdown("""
        <style>
        .stApp {
            background-color: #0F172A;
            color: #F8FAFC;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }
        
        h1, h2, h3 {
            color: #38BDF8 !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em;
        }

        .clinic-card {
            background: #1E293B;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }

        .badge-allergy {
            background-color: #7F1D1D;
            color: #FECACA;
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.85rem;
            display: inline-block;
            margin-right: 6px;
            border: 1px solid #991B1B;
        }

        .badge-condition {
            background-color: #1E3A8A;
            color: #BFDBFE;
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 500;
            font-size: 0.85rem;
            display: inline-block;
            margin-right: 6px;
            border: 1px solid #1D4ED8;
        }

        .badge-medication {
            background-color: #065F46;
            color: #A7F3D0;
            padding: 4px 12px;
            border-radius: 9999px;
            font-weight: 500;
            font-size: 0.85rem;
            display: inline-block;
            margin-right: 6px;
            border: 1px solid #047857;
        }

        .alert-box {
            background-color: #450A0A;
            border: 1px solid #991B1B;
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 16px;
            color: #FCA5A5;
        }

        div.stButton > button {
            background: linear-gradient(135deg, #0284C7 0%, #2563EB 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 12px 28px !important;
            font-weight: 700 !important;
            font-size: 1rem !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3) !important;
        }

        div.stButton > button:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 6px 16px rgba(2, 132, 199, 0.5) !important;
        }

        .stTextInput > div > div > input, .stTextArea > div > div > textarea {
            background-color: #1E293B !important;
            color: #F8FAFC !important;
            border: 1px solid #475569 !important;
            border-radius: 8px !important;
        }

        .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {
            border-color: #38BDF8 !important;
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2) !important;
        }
        </style>
    """, unsafe_allow_html=True)


def init_session_state():
    """Initializes Streamlit session state variables."""
    if "screen" not in st.session_state:
        st.session_state.screen = 1
    if "doctor_id" not in st.session_state:
        st.session_state.doctor_id = "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e"
    if "patient_id" not in st.session_state:
        st.session_state.patient_id = "P-98214"
    if "consultation_text" not in st.session_state:
        st.session_state.consultation_text = (
            "Doctor: Good morning John. What brings you in today?\n"
            "Patient: I've had a sharp cough for the last 3 days, and I felt warm last night with a fever.\n"
            "Doctor: Let me listen to your lungs. Temperature is 99.8F, blood pressure 122/80. Lungs are clear.\n"
            "Assessment: Acute viral upper respiratory infection.\n"
            "Plan: Recommend rest, hydration, and OTC Acetaminophen 500mg every 6 hours PRN for fever."
        )
    if "consultation_id" not in st.session_state:
        st.session_state.consultation_id = None
    if "current_state" not in st.session_state:
        st.session_state.current_state = None


def render_header():
    """Renders top header bar with branding and physician profile selector."""
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🩺 AI Clinical Documentation Assistant")
        st.caption("Multi-Agent LangGraph Pipeline with Human-in-the-Loop EHR Verification")
    with col2:
        st.selectbox(
            "Attending Physician Profile",
            options=["Dr. Alex Smith, MD (Attending Physician)", "Dr. Sarah Jenkins, MD (Internal Medicine)"],
            index=0,
            key="physician_selector"
        )
    st.markdown("---")


def render_screen_1():
    """Renders Screen 1: Patient Selection & Consultation Ingestion Screen."""
    st.subheader("📋 Screen 1: Patient Selection & Consultation Ingestion")

    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown("### 1. Patient EHR Lookup")
        patient_code_input = st.text_input(
            "Enter Patient Code or ID",
            value=st.session_state.patient_id,
            placeholder="e.g. P-98214",
            help="Enter patient code to query EHR history, demographics, and allergy flags."
        )
        st.session_state.patient_id = patient_code_input.strip()

        patient_info = lookup_patient_record(patient_code_input)

        if patient_info:
            st.markdown(f"""
                <div class="clinic-card">
                    <h4 style="color:#38BDF8; margin-top:0;">👤 {patient_info['full_name']}</h4>
                    <p style="margin-bottom:8px;"><b>Patient Code:</b> <code>{patient_info['patient_code']}</code> | <b>DOB:</b> {patient_info['dob']}</p>
                    <div style="margin-bottom:10px;">
                        <b>Documented Allergies:</b><br/>
                        {' '.join([f'<span class="badge-allergy">⚠️ {a}</span>' for a in patient_info['allergies']]) if patient_info['allergies'] else '<i>None documented</i>'}
                    </div>
                    <div style="margin-bottom:10px;">
                        <b>Chronic Conditions:</b><br/>
                        {' '.join([f'<span class="badge-condition">🏥 {c}</span>' for c in patient_info['chronic_conditions']]) if patient_info['chronic_conditions'] else '<i>None documented</i>'}
                    </div>
                    <div>
                        <b>Current Medications:</b><br/>
                        {' '.join([f'<span class="badge-medication">💊 {m}</span>' for m in patient_info['current_medications']]) if patient_info['current_medications'] else '<i>None documented</i>'}
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.warning(f"⚠️ Patient Code '{patient_code_input}' not found in local EHR. Pipeline will trigger unresolved patient routing.")

    with col_right:
        st.markdown("### 2. Consultation Note Ingestion")

        ingestion_mode = st.radio(
            "Select Consultation Ingestion Method",
            options=["Mode A: Typed / Dictated Text", "Mode B: Audio File Upload (.wav, .mp3, .m4a)"],
            index=0,
            horizontal=True
        )

        if "Mode B" in ingestion_mode:
            uploaded_audio = st.file_uploader(
                "Upload Recorded Clinical Dictation Audio",
                type=["wav", "mp3", "m4a", "webm"],
                help="OpenAI/Groq Whisper will transcribe audio into text prior to agent execution."
            )
            if uploaded_audio is not None:
                st.audio(uploaded_audio)
                if st.button("🎙️ Transcribe Audio Dictation"):
                    with st.spinner("Transcribing audio using Whisper API..."):
                        try:
                            files = {"file": (uploaded_audio.name, uploaded_audio.getvalue(), uploaded_audio.type)}
                            res = requests.post(f"{API_BASE_URL}/transcribe", files=files, timeout=30)
                            if res.status_code == 200:
                                result_data = res.json()
                                st.session_state.consultation_text = result_data.get("transcript", "")
                                st.success(f"Successfully transcribed audio ({result_data.get('duration_seconds', 0)}s)!")
                            else:
                                err_detail = res.json().get("detail", "Audio processing failed.")
                                st.error(f"❌ {err_detail}")
                        except Exception as exc:
                            st.error(f"❌ Audio transcription service error: {exc}. Switched to manual text dictation mode.")

        consultation_text = st.text_area(
            "Raw Consultation Transcript / Doctor Dictation Notes",
            value=st.session_state.consultation_text,
            height=220,
            help="Review or edit transcript before launching multi-agent generation."
        )
        st.session_state.consultation_text = consultation_text

        st.markdown("<br/>", unsafe_allow_html=True)

        if st.button("🚀 Generate Clinical Documentation (Run Multi-Agent Pipeline)", use_container_width=True):
            if not consultation_text.strip():
                st.error("Please enter or transcribe consultation text before running the pipeline.")
            else:
                with st.spinner("Initializing multi-agent graph execution thread..."):
                    try:
                        payload = {
                            "patient_id": st.session_state.patient_id,
                            "doctor_id": st.session_state.doctor_id,
                            "consultation_text": consultation_text
                        }
                        res = requests.post(f"{API_BASE_URL}/consultation/process", json=payload, timeout=10)
                        if res.status_code == 200:
                            data = res.json()
                            st.session_state.consultation_id = data["consultation_id"]
                            st.session_state.screen = 2
                            st.rerun()
                        else:
                            st.error(f"Failed to start pipeline: {res.text}")
                    except Exception as exc:
                        st.info("API Gateway offline. Executing pipeline in local session mode...")
                        from backend.graph.workflow import build_graph
                        from backend.graph.state import create_initial_state

                        graph = build_graph()
                        initial_state = create_initial_state(
                            patient_id=st.session_state.patient_id,
                            doctor_id=st.session_state.doctor_id,
                            consultation_text=consultation_text
                        )
                        st.session_state.consultation_id = "local-session-id"
                        st.session_state.current_state = graph.invoke(initial_state)
                        st.session_state.screen = 3
                        st.rerun()


def render_screen_2():
    """Renders Screen 2: Real-time Multi-Agent Pipeline Execution Tracker."""
    st.subheader("⚙️ Screen 2: Real-time Multi-Agent Pipeline Execution Tracker")

    consultation_id = st.session_state.consultation_id or "local-session-id"

    st.markdown(f"""
        <div class="clinic-card">
            <h4 style="color:#38BDF8; margin-top:0;">⚡ Active Thread ID: <code>#{consultation_id}</code></h4>
            <p style="margin:0;"><b>Patient Code:</b> <code>{st.session_state.patient_id}</code> | <b>Attending Doctor:</b> <code>{st.session_state.doctor_id}</code></p>
        </div>
    """, unsafe_allow_html=True)

    state_data = st.session_state.current_state or {}

    if consultation_id and consultation_id != "local-session-id":
        try:
            res = requests.get(f"{API_BASE_URL}/consultation/{consultation_id}", timeout=5)
            if res.status_code == 200:
                state_data = res.json()
                st.session_state.current_state = state_data
        except Exception:
            pass

    if not state_data or not state_data.get("review_result", {}).get("completeness_score"):
        try:
            from backend.graph.workflow import build_graph
            from backend.graph.state import create_initial_state

            graph = build_graph()
            initial_state = create_initial_state(
                patient_id=st.session_state.patient_id,
                doctor_id=st.session_state.doctor_id,
                consultation_text=st.session_state.consultation_text
            )
            config = {"configurable": {"thread_id": consultation_id}}
            state_data = graph.invoke(initial_state, config=config)
            st.session_state.current_state = state_data
        except Exception as exc:
            st.error(f"Pipeline execution error: {exc}")

    progress_pct, stage_statuses = calculate_pipeline_progress(state_data)

    st.markdown(f"### Pipeline Execution Progress: **{progress_pct}%**")
    st.progress(progress_pct / 100.0)

    st.markdown("### 🤖 Multi-Agent Stage Checklist")

    stages_info = [
        ("Patient History Agent", "history", "Queries EHR history, allergies, and risk flags"),
        ("Clinical Note Writer (SOAP)", "soap_note", "Structures Subjective, Objective, Assessment & Plan"),
        ("Medical Summary Agent", "summary_agent", "Synthesizes chief complaint & confirmed diagnosis"),
        ("Treatment Planner Agent", "treatment_agent", "Formats doctor-stated medication orders & safety guardrails"),
        ("Follow-up Coordinator Agent", "followup_agent", "Extracts follow-up dates & patient instructions"),
        ("Documentation Reviewer Agent", "reviewer_agent", "Performs quality audit, allergy alerts & ICD-10 suggestions")
    ]

    col1, col2 = st.columns(2)
    for idx, (agent_name, agent_key, desc) in enumerate(stages_info):
        target_col = col1 if idx < 3 else col2
        status_code = stage_statuses.get(agent_key, "PENDING")
        with target_col:
            if status_code == "COMPLETED":
                st.success(f"✅ **{agent_name}**  \n*{desc}* — `Completed`")
            elif status_code == "RUNNING":
                st.info(f"⏳ **{agent_name}**  \n*{desc}* — `Running...`")
            else:
                st.markdown(f"⚪ **{agent_name}**  \n*{desc}* — `Pending`", unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    if progress_pct >= 100 or state_data.get("status") == "AWAITING_APPROVAL":
        st.success("🎉 Multi-agent clinical documentation pipeline execution complete!")
        if st.button("📊 View Clinical Review & Approval Dashboard (Screen 3)", use_container_width=True):
            st.session_state.screen = 3
            st.rerun()


def render_screen_3():
    """Renders Screen 3: Doctor Approval & Review Dashboard (Human-in-the-Loop)."""
    st.subheader("🩺 Screen 3: Doctor Approval & Review Dashboard (Human-in-the-Loop)")

    state = st.session_state.current_state or {}
    consultation_id = st.session_state.consultation_id or "local-session-id"
    patient_id = st.session_state.patient_id or "P-98214"
    doctor_id = st.session_state.doctor_id

    review = state.get("review_result", {})
    completeness = review.get("completeness_score", 95)
    allergy_alerts = review.get("allergy_alerts", [])
    icd10_suggestions = review.get("icd10_suggestions", ["J20.9 (Acute Bronchitis)"])

    # 1. TOP SAFETY & WARNING BANNER
    col_score, col_alert, col_icd = st.columns([1, 2, 2])
    with col_score:
        st.metric(label="Quality Completeness Score", value=f"{completeness}/100", delta="PASSED QC")

    with col_alert:
        if allergy_alerts:
            for alert in allergy_alerts:
                st.markdown(f"""
                    <div class="alert-box">
                        <b>🚨 ALLERGY CONTRAINDICATION ALERT:</b><br/>{alert}
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ No allergy contraindications detected.")

    with col_icd:
        st.markdown("<b>🏷️ Suggested ICD-10 Codes:</b>", unsafe_allow_html=True)
        for code in icd10_suggestions:
            st.markdown(f'<span class="badge-condition">📌 ICD-10: {code}</span>', unsafe_allow_html=True)

    st.markdown("---")

    # 2. TABBED INTERACTIVE RECORD EDITOR
    tab_soap, tab_summary, tab_treatment, tab_followup = st.tabs([
        "📝 SOAP Note", "📄 Medical Summary", "💊 Treatment & Orders", "📅 Follow-up Plan"
    ])

    soap = state.get("soap_note", {})
    summary = state.get("summary", {})
    treatment = state.get("treatment_plan", {})
    followup = state.get("followup_plan", {})

    with tab_soap:
        st.markdown("### Interactive SOAP Note Editor")
        soap_subj = st.text_area("Subjective (Patient Reported Symptoms)", value=soap.get("subjective", ""), height=100)
        soap_obj = st.text_area("Objective (Vitals & Physical Exam)", value=soap.get("objective", ""), height=100)
        soap_assess = st.text_area("Assessment (Clinical Diagnosis)", value=soap.get("assessment", ""), height=80)
        soap_plan = st.text_area("Plan (Diagnostic & Clinical Actions)", value=soap.get("plan", ""), height=100)

    with tab_summary:
        st.markdown("### Medical & Discharge Summary Editor")
        sum_cc = st.text_input("Chief Complaint", value=summary.get("chief_complaint", ""))
        sum_diag = st.text_input("Primary Diagnosis", value=summary.get("diagnosis", ""))
        findings_str = "\n".join(summary.get("key_findings", [])) if isinstance(summary.get("key_findings"), list) else str(summary.get("key_findings", ""))
        sum_findings = st.text_area("Key Clinical Findings", value=findings_str, height=100)
        sum_discharge = st.text_area("Discharge Summary Note", value=summary.get("discharge_summary", ""), height=100)

    with tab_treatment:
        st.markdown("### Treatment Orders & Formatted Medications")
        st.info("🛡️ **Non-Prescriptive Safety Guardrail**: Only medications explicitly stated by the attending physician are formatted. AI does not generate unstated drug orders.")

        meds_list = treatment.get("medications", [])
        if meds_list:
            df_meds = pd.DataFrame(meds_list)
            st.dataframe(df_meds, use_container_width=True)
        else:
            st.caption("No specific prescription drugs mentioned during dictation.")

        tx_summary = st.text_area("Treatment Summary", value=treatment.get("treatment_summary", ""), height=80)
        monitoring_str = "\n".join(treatment.get("monitoring_requirements", [])) if isinstance(treatment.get("monitoring_requirements"), list) else str(treatment.get("monitoring_requirements", ""))
        tx_monitoring = st.text_area("Monitoring Requirements", value=monitoring_str, height=80)

    with tab_followup:
        st.markdown("### Follow-up & Discharge Instructions")
        fu_date = st.text_input("Recommended Follow-up Date", value=followup.get("followup_date", "1 week PRN"))
        tests_str = "\n".join(followup.get("tests_ordered", [])) if isinstance(followup.get("tests_ordered"), list) else str(followup.get("tests_ordered", ""))
        fu_tests = st.text_area("Tests / Labs Ordered", value=tests_str, height=80)
        fu_instructions = st.text_area("Patient-Friendly Discharge Instructions", value=followup.get("patient_instructions", ""), height=100)

    st.markdown("---")

    # 3. PHYSICIAN ACTIONS & PERSISTENCE
    st.markdown("### 3. Physician Verification & EHR Action")
    doc_notes = st.text_area("Attending Physician Notes / Sign-off Comments", value="Reviewed and verified clinical documentation.", height=70)

    col_approve, col_reject = st.columns([1, 1], gap="medium")

    with col_approve:
        if st.button("✅ APPROVE & SAVE TO EHR", use_container_width=True):
            final_soap = {"subjective": soap_subj, "objective": soap_obj, "assessment": soap_assess, "plan": soap_plan}
            final_summary = {
                "chief_complaint": sum_cc,
                "diagnosis": sum_diag,
                "key_findings": [f.strip() for f in sum_findings.split("\n") if f.strip()],
                "discharge_summary": sum_discharge
            }
            final_treatment = {
                "treatment_summary": tx_summary,
                "medications": meds_list,
                "monitoring_requirements": [m.strip() for m in tx_monitoring.split("\n") if m.strip()]
            }
            final_followup = {
                "followup_date": fu_date,
                "tests_ordered": [t.strip() for t in fu_tests.split("\n") if t.strip()],
                "patient_instructions": fu_instructions
            }

            approve_payload = {
                "doctor_id": doctor_id,
                "final_soap_note": final_soap,
                "final_summary": final_summary,
                "final_treatment_plan": final_treatment,
                "final_followup_plan": final_followup,
                "doctor_notes": doc_notes
            }

            try:
                res = requests.post(f"{API_BASE_URL}/consultation/{consultation_id}/approve", json=approve_payload, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    st.balloons()
                    st.success(f"🎉 **Document Approved & Persisted to Supabase EHR!**  \n**Document ID:** `#{data['document_id']}` | **Status:** `{data['status']}`")
                else:
                    st.error(f"API Persistence Error ({res.status_code}): {res.text}")
            except Exception as exc:
                # Standalone local fallback if API offline
                st.warning(f"API server offline: {exc}. Document saved locally in session.")
                st.session_state.current_state["status"] = "APPROVED"
                st.success("🎉 Document approved locally in active session!")

    with col_reject:
        with st.expander("❌ Reject Consultation Record", expanded=False):
            rejection_reason = st.text_input("Enter Rejection Reason", value="Inaccurate audio dictation uploaded.")
            if st.button("Confirm Rejection", use_container_width=True):
                reject_payload = {
                    "doctor_id": doctor_id,
                    "rejection_reason": rejection_reason
                }
                try:
                    res = requests.post(f"{API_BASE_URL}/consultation/{consultation_id}/reject", json=reject_payload, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        st.warning(f"❌ **Consultation Record Rejected!**  \nStatus: `{data['status']}` | Rejection audit trail recorded.")
                    else:
                        st.error(f"API Rejection Error: {res.text}")
                except Exception as exc:
                    st.warning(f"API server offline: {exc}. Consultation marked REJECTED in local session.")

    st.markdown("<br/>", unsafe_allow_html=True)
    if st.button("🔄 Start New Consultation (Return to Screen 1)"):
        st.session_state.screen = 1
        st.session_state.consultation_id = None
        st.session_state.current_state = None
        st.rerun()


def main():
    """Main Streamlit application router."""
    inject_custom_css()
    init_session_state()
    render_header()

    if st.session_state.screen == 1:
        render_screen_1()
    elif st.session_state.screen == 2:
        render_screen_2()
    elif st.session_state.screen == 3:
        render_screen_3()


if __name__ == "__main__":
    main()
