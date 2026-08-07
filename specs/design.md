# System Design & Architecture Specification (`specs/design.md`)

## 1. System Overview & Philosophy

The **AI Clinical Documentation Assistant** is a multi-agent system designed to convert raw doctor–patient consultation transcripts or dictated audio into structured, high-quality clinical documentation.

### Core Design Philosophy
- **Human-in-the-Loop (HITL) Safety Mandatory:** The system acts strictly as an administrative drafting assistant. AI agents **summarize, format, and flag warnings**—they never prescribe medications, alter medical decisions, or independently persist records without explicit physician review and approval.
- **Structured JSON Handoffs:** Agents communicate via strictly validated JSON schemas rather than unstructured natural language, ensuring predictable rendering and programmatic validation.
- **Parallel Fan-Out Execution:** Non-dependent tasks (fetching patient history vs. parsing consultation transcript) run concurrently to minimize latency.

---

## 2. System Architecture & Flow

### High-Level Architecture Diagram

```
                             ┌─────────────────────────────────┐
                             │    Doctor (User Interface)      │
                             └────────────────┬────────────────┘
                                              │
                                    Text / Audio Input
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │       FastAPI Gateway           │
                             └────────────────┬────────────────┘
                                              │
                                   Whisper API (if audio)
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │     LangGraph Orchestrator      │
                             └────────────────┬────────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     ▼                                                 ▼
        ┌─────────────────────────┐                       ┌─────────────────────────┐
        │  Patient History Agent  │                       │  Clinical Note Writer   │
        │   (Fetches past EHR)    │                       │  (Generates SOAP Note)  │
        └────────────┬────────────┘                       └────────────┬────────────┘
                     │                                                 │
                     └────────────────────────┬────────────────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Medical Summary Agent  │
                                 │  (Consultation/Discharge│
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │    Treatment Planner    │
                                 │   (Formats Meds/Orders) │
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Follow-up Coordinator  │
                                 │  (Checklists/Reminders) │
                                 └────────────┬────────────┘
                                              ▼
                                 ┌─────────────────────────┐
                                 │ Documentation Reviewer  │
                                 │ (Quality/Safety Audit)  │
                                 └────────────┬────────────┘
                                              ▼
                             ┌─────────────────────────────────┐
                             │    Doctor Approval UI           │
                             │  (Inspect, Edit, Approve)       │
                             └────────────────┬────────────────┘
                                              │
                                           Approve
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │  Supabase PostgreSQL Storage    │
                             └─────────────────────────────────┘
```

---

## 3. Data Schema & Models

### 3.1 Entity Relationship Diagram (ERD) Conceptual Schema

```
+-------------------+       1:N       +-------------------+
|     PATIENTS      | <-------------> |   CONSULTATIONS   |
+-------------------+                 +-------------------+
| id (UUID)         |                 | id (UUID)         |
| patient_code      |                 | patient_id (FK)   |
| full_name         |                 | doctor_id (UUID)  |
| dob, gender       |                 | raw_transcript    |
| allergies (JSONB) |                 | status (ENUM)     |
| history (JSONB)   |                 +---------+---------+
+-------------------+                           │ 1:1
                                                ▼
                                      +-------------------+
                                      | CLINICAL_DOCUMENTS|
                                      +-------------------+
                                      | id (UUID)         |
                                      | consultation_id   |
                                      | soap_note (JSONB) |
                                      | summary (JSONB)   |
                                      | treatment (JSONB) |
                                      | followup (JSONB)  |
                                      | reviewer_flags    |
                                      | doctor_edits      |
                                      +-------------------+
```

---

### 3.2 Canonical Status Enum & Database Tables

#### Canonical Status Enum (`ConsultationStatus`)
```python
from enum import Enum

class ConsultationStatus(str, Enum):
    DRAFT = "DRAFT"                 # Consultation created / raw transcript uploaded
    PROCESSING = "PROCESSING"       # Multi-agent LangGraph pipeline executing
    AWAITING_APPROVAL = "AWAITING_APPROVAL" # Agent execution complete; awaiting doctor action
    APPROVED = "APPROVED"           # Doctor clicked "Approve & Save" (persisted to clinical_documents)
    REJECTED = "REJECTED"           # Doctor clicked "Reject & Discard"
    FAILED = "FAILED"               # Unrecoverable error in agent pipeline or transcription
```

#### SQL DDL Schema (PostgreSQL / Supabase)

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Patients Table (Shared across hospital system)
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_code VARCHAR(50) UNIQUE NOT NULL, -- e.g. "P-98214"
    full_name VARCHAR(255) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(20),
    allergies JSONB DEFAULT '[]'::jsonb,
    chronic_conditions JSONB DEFAULT '[]'::jsonb,
    current_medications JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Consultations Table
CREATE TABLE consultations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL,
    raw_transcript TEXT NOT NULL,
    audio_url TEXT,
    status VARCHAR(30) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PROCESSING', 'AWAITING_APPROVAL', 'APPROVED', 'REJECTED', 'FAILED')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    approved_at TIMESTAMP WITH TIME ZONE
);

-- 3. Clinical Documents Table (Approved Records)
CREATE TABLE clinical_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consultation_id UUID REFERENCES consultations(id) ON DELETE CASCADE UNIQUE,
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    soap_note JSONB NOT NULL,
    summary JSONB NOT NULL,
    treatment_plan JSONB NOT NULL,
    followup_plan JSONB NOT NULL,
    reviewer_flags JSONB DEFAULT '[]'::jsonb,
    doctor_edits JSONB DEFAULT '{}'::jsonb,
    doctor_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Audit Logs Table (Metadata-Only Privacy Logging)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL, -- e.g. 'CONSULTATION_SUBMITTED', 'DOCTOR_EDIT', 'DOCUMENT_APPROVED', 'DOCUMENT_REJECTED'
    consultation_id UUID REFERENCES consultations(id),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb -- Example: {"edited_fields": ["soap.plan"], "latency_ms": 1150, "rejection_reason": "Inaccurate transcript"}
);
```

> **Row-Level Security (RLS) & ID Resolution Note:**  
> `patient_id` in API requests accept either `patient_code` (e.g. `"P-98214"`) for user convenience or raw UUIDs. The backend resolves `patient_code` to `patients.id`.  
> Patients table is shared across the hospital directory. Row-Level Security (RLS) strictly restricts a doctor's access to `consultations`, `clinical_documents`, and draft notes authored by their authenticated `doctor_id`.

---

## 4. Contracts & Interface Specifications

### 4.1 LangGraph State Contract (`MedicalState`)

```json
{
  "patient_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "doctor_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
  "consultation_text": "Patient comes in complaining of a 3-day history of sharp cough and low-grade fever...",
  "audio_url": null,
  
  "history": {
    "allergies": ["Penicillin"],
    "chronic_conditions": ["Hypertension"],
    "current_medications": ["Lisinopril 10mg QD"],
    "risk_flags": ["Penicillin allergy severe anaphylaxis"]
  },
  
  "soap_note": {
    "subjective": "3-day history of sharp cough with low-grade fever...",
    "objective": "Temp 99.8F, BP 122/80, HR 76. Lungs clear to auscultation bilaterally.",
    "assessment": "Acute viral upper respiratory infection.",
    "plan": "Hydration, rest, OTC Acetaminophen 500mg Q6H PRN."
  },
  
  "summary": {
    "chief_complaint": "Cough and mild fever",
    "diagnosis": "Viral Upper Respiratory Infection",
    "key_findings": ["No lower respiratory tract involvement", "Afebrile at examination"],
    "discharge_summary": "Cleared for home care with symptomatic treatment."
  },
  
  "treatment_plan": {
    "treatment_summary": "Symptomatic support and monitoring.",
    "medications": [
      {
        "name": "Acetaminophen",
        "dosage": "500mg",
        "frequency": "Every 6 hours PRN for fever",
        "duration": "5 days"
      }
    ],
    "monitoring_requirements": ["Monitor temperature twice daily"]
  },
  
  "followup_plan": {
    "followup_date": "2026-08-14",
    "tests_ordered": [],
    "patient_instructions": "Drink plenty of fluids, rest, and contact clinic if fever exceeds 101F."
  },
  
  "review_result": {
    "passed_qc": true,
    "completeness_score": 0.95,
    "issues": [],
    "warnings": [
      "Check if blood pressure re-check is required.",
      "ICD-10 suggestion: J20.9 (Acute Bronchitis)"
    ]
  },
  
  "status": "AWAITING_APPROVAL"
}
```

---

### 4.2 Agent Contracts

Each of the 6 agents adheres to strict input/output contracts:

| Agent Name | Input Fields | Output JSON Keys | Core Validation / Guardrail |
|---|---|---|---|
| **Patient History Agent** | `patient_id` | `allergies`, `chronic_conditions`, `current_medications`, `risk_flags` | Highlight severe allergies in `risk_flags`. Never fabricate unlisted history. |
| **Clinical Note Writer** | `consultation_text` | `soap: { subjective, objective, assessment, plan }` | Ensure vital signs & physical exam details are extracted only if present in text. |
| **Medical Summary Agent** | `soap_note`, `history` | `chief_complaint`, `diagnosis`, `key_findings`, `discharge_summary` | Synthesize SOAP assessment with history. No contradictory diagnoses. |
| **Treatment Planner** | `soap_note.plan`, `history` | `treatment_summary`, `medications`, `monitoring_requirements` | **Strict Non-Prescriptive Guardrail:** Format only doctor-stated meds. Flag allergy conflicts. |
| **Follow-up Coordinator** | `treatment_plan`, `summary` | `followup_date`, `tests_ordered`, `patient_instructions` | Generate clear, patient-friendly language for instructions. |
| **Documentation Reviewer**| Entire `MedicalState` | `passed_qc`, `completeness_score`, `issues`, `warnings` | Flag missing SOAP sections, unaddressed risk flags, or unfilled fields. Include ICD-10 suggestions inside `warnings`. |

---

### 4.3 REST API Endpoints (FastAPI)

#### 1. Transcribe Audio
- **Endpoint:** `POST /api/v1/transcribe`
- **Request:** `multipart/form-data` with `file: UploadFile`
- **Response:**
```json
{
  "transcript": "Doctor: Good morning... Patient: I have been having a headache...",
  "duration_seconds": 142.5
}
```

#### 2. Process Consultation (Start Agent Pipeline)
- **Endpoint:** `POST /api/v1/consultation/process`
- **Request Body:**
```json
{
  "patient_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "doctor_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
  "consultation_text": "Patient reports severe cough..."
}
```
- **Response:**
```json
{
  "consultation_id": "c7b2e8a1-4f90-41a2-8e3b-9a8f21e0b1a2",
  "status": "PROCESSING"
}
```

#### 3. Fetch Pipeline Status & State
- **Endpoint:** `GET /api/v1/consultation/{consultation_id}`
- **Response:** Returns complete `MedicalState` object along with current execution stage.

#### 4. Doctor Approval & Database Persistence
- **Endpoint:** `POST /api/v1/consultation/{consultation_id}/approve`
- **Request Body:**
```json
{
  "doctor_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
  "final_soap_note": { "subjective": "...", "objective": "...", "assessment": "...", "plan": "..." },
  "final_summary": { "chief_complaint": "...", "diagnosis": "...", "key_findings": [], "discharge_summary": "..." },
  "final_treatment_plan": { "treatment_summary": "...", "medications": [], "monitoring_requirements": [] },
  "final_followup_plan": { "followup_date": "2026-08-14", "tests_ordered": [], "patient_instructions": "..." },
  "doctor_notes": "Reviewed and approved with minor edit to dosage timing."
}
```
- **Response:**
```json
{
  "success": true,
  "document_id": "d91a7f3c-5e21-4a8b-90c1-2f8e7d4a1b0c",
  "status": "APPROVED",
  "timestamp": "2026-08-07T23:10:00Z"
}
```

#### 5. Doctor Rejection
- **Endpoint:** `POST /api/v1/consultation/{consultation_id}/reject`
- **Request Body:**
```json
{
  "doctor_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
  "rejection_reason": "Inaccurate transcript uploaded."
}
```
- **Response:**
```json
{
  "success": true,
  "status": "REJECTED",
  "timestamp": "2026-08-07T23:10:05Z"
}
```
*(Note: Rejection updates `consultations.status = 'REJECTED'` and writes an audit log entry with `action = 'CONSULTATION_REJECTED'` and `metadata = {"rejection_reason": "Inaccurate transcript uploaded"}`.)*

---

### 4.4 Graph Error Handling & Fallback Protocols

#### 1. Missing Patient ID Handling
- If `patient_id` is missing or invalid upon initiation, the graph router catches the error and halts execution at node `INTERRUPT_MISSING_PATIENT_ID`.
- **System Action:** Status remains `PROCESSING` (breakpoint paused); Streamlit UI prompts the physician to select or create a valid patient record before proceeding.

#### 2. LLM Rate Limit / Timeout Handling
- LLM calls (OpenAI API) execute via LangChain retry handler with exponential backoff (`max_retries=2`).
- **Failure Transition:** If retries exhaust without success, the orchestrator sets `status = "FAILED"` and logs the exception. The UI displays an error notification giving the physician the option to retry execution or proceed with manual text editing.

#### 3. Whisper Audio Transcription Failure
- If audio upload decoding fails or the Whisper API returns an HTTP error, the gateway catches the exception, updates `consultations.status = "FAILED"`, and returns a clear API error response.
- **Fallback Action:** Streamlit UI catches the `FAILED` state and automatically falls back to displaying the text dictation editor so the doctor can type or paste the transcript directly.

#### 4. Backend Process Restart Mid-Pipeline
- LangGraph MVP uses in-process backend memory (`MemorySaver`) bound to `thread_id`.
- If the backend FastAPI process restarts while an agent pipeline is running, the in-memory execution state is reset.
- **Fallback Action:** The UI prompts the physician to click **"Re-run Pipeline"** to restart execution from the raw transcript.

#### 5. Database Downtime During Approval (`POST /approve`)
- **Retry Policy:** The system executes 3 exponential retries (1s, 2s, 4s) to Supabase.
- **Exhaustion Handling:** If Supabase remains unreachable, return `503 Service Unavailable`.
- **UI UX Recovery:** Streamlit displays a clear alert banner:
  > ⚠️ **Database Temporarily Unreachable:** Your edited clinical documentation is preserved in your active session. Please wait a moment and click **"Approve & Save"** again.

---

## 5. User Interface (UI) & User Experience (UX) Design

The Streamlit UI is structured into **3 core screens**:

### Screen 1: Consultation Input & Patient Selection

```
+-----------------------------------------------------------------------+
|  AI Clinical Documentation Assistant                                  |
|  [Select Doctor Profile: Dr. Alex Smith, MD  v]                       |
+-----------------------------------------------------------------------+
|  PATIENT SELECTION                                                    |
|  Enter Patient Code / ID: [ P-98214            ]  (Search)             |
|  Patient Name: John Doe | DOB: 1982-05-14 | Allergies: Penicillin   |
+-----------------------------------------------------------------------+
|  CONSULTATION INPUT                                                   |
|  (o) Type / Paste Consultation Text     ( ) Upload Audio Dictation   |
|  +-----------------------------------------------------------------+  |
|  | Doctor: Patient reports severe cough for 4 days...              |  |
|  | Patient: Yes, and mild fever last night.                        |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  [ Generate Clinical Documentation (Run Pipeline) ]                    |
+-----------------------------------------------------------------------+
```

---

### Screen 2: Real-time Multi-Agent Pipeline Execution

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

```
+-----------------------------------------------------------------------+
|  REVIEW & APPROVAL DASHBOARD  -- Patient: John Doe (P-98214)          |
+-----------------------------------------------------------------------+
|  DOCUMENTATION REVIEW WARNINGS & FLAGS                                |
|  [!] Alert: Severe Penicillin allergy noted in history.               |
|  [*] Warning: ICD-10 coding suggestion: J20.9 (Acute Bronchitis).    |
+-----------------------------------------------------------------------+
|  [ Tab 1: SOAP Note ] [ Tab 2: Summary ] [ Tab 3: Treatment ] [ Tab 4: Followup ]
|                                                                       |
|  SUBJECTIVE (Editable)                                                |
|  +-----------------------------------------------------------------+  |
|  | Patient reports severe cough for 4 days with low-grade fever... |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  OBJECTIVE (Editable)                                                 |
|  +-----------------------------------------------------------------+  |
|  | Temp: 99.8 F, BP: 122/80, HR: 76. Lungs: Clear to auscultation.   |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  ASSESSMENT (Editable)                                                |
|  +-----------------------------------------------------------------+  |
|  | Acute viral upper respiratory infection.                        |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  PLAN (Editable)                                                      |
|  +-----------------------------------------------------------------+  |
|  | Hydration, rest, OTC Acetaminophen 500mg Q6H PRN.                 |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
|  ACTIONS                                                              |
|  [ EDIT ALL FIELDS ]     [ REJECT & DISCARD ]     [ APPROVE & SAVE ]  |
+-----------------------------------------------------------------------+
```

---

## 6. Security, Privacy & Non-Prescriptive Guardrails

1. **Non-Prescriptive Guardrail:**
   - The system prompt for `Treatment Planner` strictly forbids introducing medications not found in `SOAP.plan` or direct transcript input.
   - The `Documentation Reviewer` runs cross-checks between `transcript` vs `medications`.

2. **Data Privacy (HIPAA Alignment):**
   - Application execution logs do **not** log patient PII or raw text—only token counts, agent IDs, latencies, and execution status.
   - Database queries enforced via Supabase Row-Level Security (RLS) policies scoped to `doctor_id`.

3. **Auditability (Metadata-Only):**
   - Every approval logs the exact timestamp, doctor ID, action type, consultation ID, and metadata (`edited_fields`, `latency_ms`, `rejection_reason`) in `audit_logs` for compliance tracking without storing raw PII in generic logs.

---

## 7. Project Directory Structure

```
ai_clinical_documentation_assistant/
│
├── specs/
│   ├── idea.md                    <-- Requirements, problem statement & rubric scope
│   └── design.md                  <-- Single Canonical Master Design Spec
│
├── backend/
│   ├── agents/
│   │   ├── history_agent.py
│   │   ├── note_writer.py
│   │   ├── summary_agent.py
│   │   ├── treatment_agent.py
│   │   ├── followup_agent.py
│   │   └── reviewer.py
│   │
│   ├── graph/
│   │   ├── state.py
│   │   └── workflow.py
│   │
│   ├── memory/
│   │   └── supabase.py
│   │
│   ├── tools/
│   │   ├── whisper.py
│   │   └── openai.py
│   │
│   ├── schemas/
│   │   └── models.py
│   │
│   ├── api/
│   │   └── endpoints.py
│   │
│   └── main.py
│
├── frontend/
│   └── streamlit_app.py
│
├── docs/
│   └── architecture.png           <-- Architecture diagram export
│
├── requirements.txt
└── README.md
```
