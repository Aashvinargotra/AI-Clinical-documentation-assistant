# Product & User Experience Specification (`specs/product.md`)

## 1. Product Vision & Value Proposition

The **AI Clinical Documentation Assistant** is an intelligent administrative drafting system designed to eliminate physician documentation burnout. By automatically converting doctor-patient consultation dialogue into structured clinical notes, summaries, treatment plans, and follow-up checklists, the assistant drastically reduces administrative burden while keeping the attending physician firmly in control through an intuitive **Human-in-the-Loop (HITL)** approval workflow.

### Core Product Principles
- **Physician Authority First:** AI drafts, structures, and flags warnings—it **never** prescribes, diagnoses independently, or auto-commits records to the database.
- **Instant Productivity:** Translates 15-minute consultations into polished SOAP notes and discharge records in seconds (AI pipeline latency ~15–30s).
- **Zero Friction UI:** Clean, responsive, tabbed clinical dashboard designed for rapid inline editing and single-click approval.

---

## 2. User Personas

### Primary Persona: Dr. Alex Smith, MD (Attending Physician)
- **Goal:** Provide attentive care during consultations without spending hours after clinics typing EHR notes.
- **Pain Point:** Manual documentation takes 2–3 hours per day, contributing to clinical fatigue and delayed patient discharge summaries.
- **Needs:** Rapid generation of structured SOAP notes, automated allergy conflict flags, editable summary tabs, and a fast 1-click approval workflow.

### Secondary Persona: Nurse Sarah Jenkins, RN (Clinical Coordinator)
- **Goal:** Ensure patients receive clear, actionable follow-up instructions, lab order checklists, and discharge guidelines.
- **Pain Point:** Disorganized or vague physician plan notes lead to follow-up confusion and patient readmissions.
- **Needs:** Formatted follow-up checklists, patient-friendly instruction summaries, and clear monitoring requirements.

> **MVP Scope Note:** Dedicated multi-tenant role-based access control (RBAC) and automated PDF export features are post-MVP enhancements. In the MVP workflow, Nurse Jenkins receives follow-up checklists, lab order summaries, and patient instructions through the clinic's existing workflow (e.g., the attending physician relays or shares the approved record directly from their EHR view).

---

## 3. End-to-End User Experience Journey

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: CONSULTATION INGESTION & PATIENT LOOKUP                        │
│ Doctor selects patient (P-98214) & inputs dialogue (Text or Audio)      │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: LIVE MULTI-AGENT PIPELINE TRACKING                             │
│ Real-time execution indicators showing agent progress (Fan-Out -> Sequential) │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: INTERACTIVE DOCTOR APPROVAL DASHBOARD (HITL)                   │
│ Tabbed editing of SOAP, Summary, Treatment & Follow-up + Reviewer Sidebar│
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                        ┌───────────┴───────────┐
                        ▼                       ▼
            [ APPROVE & SAVE ]          [ REJECT CONSULTATION ]
                        │                       │
                        ▼                       ▼
            Saved to Supabase EHR       Marked Rejected + Audit Logged
```

---

## 4. Screen-by-Screen User Workflow

### Screen 1: Patient Lookup & Consultation Input

**User Actions:**
1. **Patient Selection:** The doctor enters the `Patient Code` (e.g., `P-98214`). The system displays patient demographic details, active chronic conditions, and severe allergy flags (e.g., `Penicillin Anaphylaxis`).
2. **Consultation Ingestion Method:**
   - **Mode A (Typed / Dictated Text):** The doctor pastes or types raw consultation notes directly into the text editor.
   - **Mode B (Audio Dictation Upload):** The doctor uploads a recorded audio file (`.wav`, `.mp3`, `.m4a`, `.webm`). OpenAI Whisper automatically transcribes the audio file into text prior to agent pipeline execution. Audio format validation is handled by `tools/whisper.py`.
3. **Trigger Pipeline:** Click **`[ Generate Clinical Documentation ]`**.

---

### Screen 2: Real-time Multi-Agent Progress Tracking

**User Actions & Feedback:**
- The UI displays a live progress bar and status checklist as the 6 agents process the consultation:

```
+-----------------------------------------------------------------------+
|  PROCESSING CONSULTATION  [Consultation ID: #c7b2e8a1]                |
+-----------------------------------------------------------------------+
|  Pipeline Progress: [===============================>        ] 75%    |
|                                                                       |
|  [v] Patient History Agent        -- Completed (Fetched 3 past records)
|  [v] Clinical Note Writer (SOAP)  -- Completed (SOAP note structured) |
|  [v] Medical Summary Agent        -- Completed (Summary synthesized) |
|  [>] Treatment Planner            -- Running...                       |
|  [ ] Follow-up Coordinator        -- Pending                          |
|  [ ] Documentation Reviewer       -- Pending                          |
+-----------------------------------------------------------------------+
```

---

### Screen 3: Doctor Approval & Review Dashboard (Human-in-the-Loop)

**Key Layout Features:**

#### 1. Reviewer Warning & Safety Sidebar (Top Banner / Sidebar)
- **Allergy Conflict Alert:** Prominently highlights historical allergy conflicts if detected.
- **Completeness Score:** Visual progress ring (e.g., `95% Complete`).
- **ICD-10 Suggestions:** Suggested diagnostic codes (e.g., `ICD-10: J20.9 Acute Bronchitis`).

#### 2. Tabbed Interactive Clinical Record Editor
- **Tab 1: SOAP Note**
  - Editable text fields for `Subjective`, `Objective`, `Assessment`, `Plan`.
- **Tab 2: Medical & Discharge Summary**
  - Editable fields for `Chief Complaint`, `Primary Diagnosis`, `Key Findings`, `Discharge Summary`.
- **Tab 3: Treatment & Medication Orders**
  - Formatted medication table (`Name`, `Dosage`, `Frequency`, `Duration`) and `Monitoring Requirements`.
  - **Non-Prescriptive Banner:** Reminds physician that only doctor-stated medications are formatted.
- **Tab 4: Follow-up & Patient Instructions**
  - `Recommended Follow-up Date`, `Tests/Labs Ordered`, and `Patient-Friendly Instructions`.

#### 3. Primary Action Buttons
- **`[ APPROVE & SAVE TO EHR ]`** (Primary Green Button): Persists the reviewed and edited clinical document to Supabase and writes an audit log.
- **`[ REJECT CONSULTATION ]`** (Secondary Red Button): Prompts for a brief rejection reason, updates consultation status to `REJECTED` in the database, and records rejection metadata in `audit_logs` for HIPAA compliance tracking (no document is written to `clinical_documents`).
- **`[ EDIT ALL FIELDS ]`** (Secondary Gray Button): Enables bulk editing mode.

---

## 5. Error Handling & Fallback User Experiences

### 1. Unresolved Patient Record Alert (`INTERRUPT_UNRESOLVED_PATIENT`)
- **User Experience:** If an entered `Patient Code` / `Patient ID` fails to resolve to a row in `patients`, the pipeline pauses and displays an inline alert:
  > ⚠️ **Patient Record Not Found:** No matching patient row found for `"P-99999"`. Please select an existing patient from the directory or create a new profile.

### 2. Speech-to-Text Audio Upload Failure
- **User Experience:** If audio transcription fails or Whisper API returns an error, the system displays:
  > ❌ **Audio Processing Error:** Unable to transcribe audio file. Switched to manual text dictation mode.
  - Automatically activates the text dictation input box without losing patient context.

### 3. Database Downtime During Approval (`503 Service Unavailable`)
- **User Experience:** If Supabase drops during submission, Streamlit displays:
  > ⚠️ **Database Temporarily Unreachable:** Your edited clinical documentation is preserved in your active session. Please wait a moment and click **"Approve & Save"** again.

---

## 6. Product Success Metrics & Acceptance Criteria

| Metric | Benchmark Goal | Metric Definition & Scoping | User Impact |
|---|---|---|---|
| **AI Pipeline Latency** | ~15–30 seconds | Agent execution time (Fan-Out + 4 sequential chains) | Rapid draft availability |
| **Total Doctor Workflow Time** | < 2 minutes total | Hypothesized goal for Generation + Review + Edit + Approval | 70–80% time reduction vs manual typing |
| **Physician Approval Gate Enforcement** | 100% compliance | Hard safety requirement | Zero unapproved records persisted to database |
| **Unsolicited Prescriptions** | 0% (Strictly zero) | Hard safety requirement | Full adherence to non-prescriptive safety mandate |
| **Allergy Conflict Flagging** | 100% sensitivity | Safety reviewer requirement | Immediate visual alert for penicillin/medication conflicts |

> *Note: Time reduction percentages (70–80%) are hypothesized performance benchmarks to be empirically measured during synthetic evaluation testing.*
