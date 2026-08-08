# Phased Development & Verification Plan (`specs/developmentPlan.md`)

## 1. Overview & Development Strategy

The **AI Clinical Documentation Assistant** is implemented using a structured, 6-phase development roadmap. To guarantee system reliability, safety, and rubric compliance, each subphase defines explicit **AI Work** (automated code generation, schema definition, and graph compilation) and **Human Work** (environment configuration, manual testing, and verification).

Every phase concludes with a mandatory **Human Verification & Benchmark Gate** featuring clear, measurable passing criteria that must be satisfied before proceeding to the next phase.

---

## Phase 1: Environment, Database & Schemas Setup

### Subphase 1.1: Project Environment & Dependency Initialization
- **AI Work:** Create `requirements.txt`, `.env.example`, `.gitignore`, and base package structure (`backend/`, `frontend/`, `tests/`).
- **Human Work:** 
  1. Create Python 3.10+ virtual environment (`python -m venv venv`).
  2. Install dependencies (`pip install -r requirements.txt`).
  3. Create `.env` from `.env.example` and populate `OPENAI_API_KEY`, `SUPABASE_URL`, and `SUPABASE_KEY`.

### Subphase 1.2: Database DDL Execution & Supabase RLS Setup
- **AI Work:** Provide complete SQL migration DDL script for `patients`, `consultations`, `clinical_documents`, and `audit_logs` tables along with Row-Level Security (RLS) policies.
- **Human Work:**
  1. Open Supabase SQL Editor in browser.
  2. Paste and execute the DDL script.
  3. Insert 2 synthetic test patient rows into `patients` table (`P-98214: John Doe`, `P-98215: Jane Smith`).
  4. Insert 2 synthetic test doctor profiles (`Doctor A: b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e`, `Doctor B: e7f8a9b0-c1d2-3e4f-5a6b-7c8d9e0f1a2b`).

### Subphase 1.3: Type & Schema Declarations
- **AI Work:**
  1. Implement `backend/schemas/models.py` containing API Request/Response Pydantic models and `ConsultationStatus` enum.
  2. Implement `backend/graph/state.py` as the **EXCLUSIVE home** for `MedicalState` `TypedDict`.
- **Human Work:** Run initial Pydantic schema validation tests (`pytest tests/test_schemas.py`).

---

### 🛡️ Phase 1 Human Verification & Benchmark Gate

| Verification Checklist Item | Manual Human Test Action | Benchmark / Passing Criteria |
|---|---|---|
| **Dependencies Installed** | Run `python -c "import fastapi, langgraph, supabase, openai, tenacity"` | Zero import errors returned |
| **Database Schema Active** | Inspect Supabase Table Editor in browser | All 4 tables (`patients`, `consultations`, `clinical_documents`, `audit_logs`) exist with primary keys |
| **Test Fixture Data Ready** | Query `SELECT * FROM patients;` in Supabase SQL Editor | Returns 2 test patient rows (`P-98214` and `P-98215`) |
| **SQL RLS Isolation Check** | Execute SQL: `SET LOCAL request.jwt.claim.sub = 'Doctor A UUID'; SELECT * FROM consultations WHERE doctor_id = 'Doctor B UUID';` | Returns **0 rows** (Row-Level Security isolates unauthorized physician data) |
| **Schema Type Safety** | Run `pytest tests/test_schemas.py -v` | 100% test pass rate for `ConsultationStatus` enum and Pydantic models |

---

## Phase 2: Individual AI Agents & Safety Guardrails

### Subphase 2.1: Parallel Agent Nodes Implementation
- **AI Work:** Implement `backend/agents/history_agent.py` (queries Supabase for past EHR & allergies) and `backend/agents/note_writer.py` (SOAP note structuring) using ChatOpenAI `.with_structured_output()` and `.with_retry(stop_after_attempt=3)`.
- **Human Work:** Run standalone node execution script providing test `patient_id` and sample transcript.

### Subphase 2.2: Sequential Agent Nodes & Non-Prescriptive Guardrail
- **AI Work:** 
  1. Implement `backend/agents/summary_agent.py` (synthesizes chief complaint, diagnosis, discharge summary).
  2. Implement `backend/agents/treatment_agent.py` enforcing the **strict non-prescriptive safety mandate** (formats doctor-stated meds only, checks contraindications against history allergies).
- **Human Work:** Inspect Treatment Planner output against raw transcript to verify zero unmentioned medications are introduced.

### Subphase 2.3: Follow-up & Reviewer Agents Implementation
- **AI Work:**
  1. Implement `backend/agents/followup_agent.py` (formats follow-up dates, tests ordered, patient instructions).
  2. Implement `backend/agents/reviewer.py` (evaluates `passed_qc`, completeness score, missing section warnings, and ICD-10 suggestions).
- **Human Work:** Test an incomplete transcript input to verify Reviewer Agent flags missing physical exam sections.

---

### 🛡️ Phase 2 Human Verification & Benchmark Gate

| Verification Checklist Item | Manual Human Test Action | Benchmark / Passing Criteria |
|---|---|---|
| **JSON Schema Adherence** | Run `pytest tests/test_agents.py -v` | All 6 agents return strictly valid JSON matching Pydantic response models |
| **Non-Prescriptive Guardrail** | Pass transcript with no medications mentioned to `treatment_agent` | `medications` array is `[]` (0 introduced medications) |
| **Allergy Conflict Sensitivity** | Pass `Penicillin` allergy history + transcript mentioning Penicillin | `treatment_summary` contains explicit contraindication warning flag |
| **Reviewer Quality Check** | Pass incomplete SOAP note (missing `Objective` vitals) to `reviewer` | `passed_qc` is `false` or `warnings` list contains missing section flag |

---

## Phase 3: LangGraph Orchestration & Resilience Engine

### Subphase 3.1: StateGraph Construction & Parallel Fan-Out Execution
- **AI Work:** Implement `backend/graph/workflow.py` linking Fan-Out (`START` -> `history_agent` ∥ `note_writer`) and Sequential Fan-In (`summary_agent` -> `treatment_agent` -> `followup_agent` -> `reviewer_agent`).
- **Human Work:** Run graph test script to observe concurrent execution timing.

### Subphase 3.2: Unresolved Patient Interrupt Node & Routing
- **AI Work:** Implement `INTERRUPT_UNRESOLVED_PATIENT` conditional router in `backend/graph/workflow.py` which triggers when History Agent returns `None` for a `patient_id` / `patient_code`.
- **Human Work:** Trigger graph execution with invalid patient code `"INVALID-99"` and verify execution pauses at interrupt node.

### Subphase 3.3: MemorySaver Checkpointer & Database Retry Wrappers
- **AI Work:** Integrate `MemorySaver` checkpointer in `workflow.py` and implement `@retry` exponential backoff wrappers (min 1s, max 4s, 3 attempts) in `backend/memory/supabase.py`.
- **Human Work:** Simulate network drop to verify retry attempts in log output.

---

### 🛡️ Phase 3 Human Verification & Benchmark Gate

| Verification Checklist Item | Manual Human Test Action | Benchmark / Passing Criteria |
|---|---|---|
| **Fan-Out Concurrency** | Run `pytest tests/test_graph.py -k "test_fanout_execution"` | `history_agent` and `note_writer` execute concurrently without key collision in `MedicalState` |
| **Interrupt Routing** | Run `pytest tests/test_graph.py -k "test_unresolved_patient_interrupt"` | Graph pauses execution at `INTERRUPT_UNRESOLVED_PATIENT` node when given `"INVALID-99"`; status remains `PROCESSING` |
| **LLM Retry Exhaustion** | Run `pytest tests/test_graph.py -k "test_llm_retry_exhaustion"` | Simulates 3 failed OpenAI API calls; agent sets `status = "FAILED"` gracefully |
| **DB Outage Retry & 503** | Run `pytest tests/test_api.py -k "test_db_outage_503"` | Executes 3 exponential retries to Supabase before returning HTTP `503 Service Unavailable` |
| **Pipeline Latency** | Benchmark total graph execution time for full visit input | Total AI pipeline latency is **< 30 seconds** |

---

## Phase 4: FastAPI REST API Gateway

### Subphase 4.1: Audio Transcription Endpoint (`/api/v1/transcribe`)
- **AI Work:** Implement `backend/tools/whisper.py` and `POST /api/v1/transcribe` endpoint supporting `UploadFile` with `python-multipart` validation.
- **Human Work:** Test audio file upload (`.mp3` or `.wav`) via FastAPI Swagger docs (`http://localhost:8000/docs`).

### Subphase 4.2: Pipeline Execution & Status Endpoints (`/process`, `/{id}`)
- **AI Work:** Implement `POST /api/v1/consultation/process` (triggers graph thread) and `GET /api/v1/consultation/{consultation_id}` (fetches status & state).
- **Human Work:** Submit consultation via POST request and poll status endpoint until `status: "AWAITING_APPROVAL"`.

### Subphase 4.3: Doctor Approval & Rejection Endpoints (`/approve`, `/reject`)
- **AI Work:** 
  1. Implement `POST /api/v1/consultation/{consultation_id}/approve` (writes row to `clinical_documents` & `audit_logs`).
  2. Implement `POST /api/v1/consultation/{consultation_id}/reject` (updates `consultations.status = 'REJECTED'` & writes rejection metadata to `audit_logs`).
- **Human Work:** Execute `/approve` and `/reject` calls; verify rows written in Supabase.

---

### 🛡️ Phase 4 Human Verification & Benchmark Gate

| Verification Checklist Item | Manual Human Test Action | Benchmark / Passing Criteria |
|---|---|---|
| **Audio Transcription** | Upload 10-second test dictation `.wav` to `/api/v1/transcribe` | Returns HTTP `200` with accurate text string in `transcript` field |
| **Whisper Failure Fallback** | Upload corrupted audio file to `/api/v1/transcribe` | Returns API error (`pytest tests/test_api.py -k "test_whisper_error_fallback"` passes), triggering Streamlit text dictation fallback |
| **Approval Persistence** | Send POST request to `/api/v1/consultation/{id}/approve` | Writes 1 row to `clinical_documents` and 1 row to `audit_logs` in Supabase |
| **Rejection Audit Trail** | Send POST request to `/api/v1/consultation/{id}/reject` with reason | `consultations.status` is `'REJECTED'`; 1 audit log entry written; 0 rows written to `clinical_documents` |
| **RLS API Cross-Doctor Gate** | Run `pytest tests/test_api.py -k "test_rls_cross_doctor_isolation"` | Doctor A receives **HTTP `404 Not Found`** when attempting to fetch Doctor B's consultation ID, preventing record existence leakage |

---

## Phase 5: Streamlit Human-in-the-Loop UI & Dashboard

### Subphase 5.1: Patient Selection & Consultation Ingestion Screen
- **AI Work:** Implement Screen 1 in `frontend/streamlit_app.py` (patient lookup search bar, text editor, audio file uploader widget).
- **Human Work:** Test searching patient `P-98214` and pasting consultation text in browser UI (`http://localhost:8501`).

### Subphase 5.2: Live Multi-Agent Execution Progress Screen
- **AI Work:** Implement Screen 2 live progress bar and agent status checklist displaying completed (`[v]`), running (`[>]`), and pending (`[ ]`) stages.
- **Human Work:** Click **`[ Generate Clinical Documentation ]`** and watch real-time execution transitions.

### Subphase 5.3: Doctor Approval & Review Dashboard (HITL)
- **AI Work:** Implement Screen 3 (Reviewer sidebar with allergy alerts & ICD-10 suggestions, tabbed SOAP/Summary/Treatment/Followup editors, `[ APPROVE & SAVE TO EHR ]`, and `[ REJECT CONSULTATION ]` action buttons).
- **Human Work:** Perform inline edits to the SOAP plan, click **`[ APPROVE & SAVE TO EHR ]`**, and verify saved edits in Supabase.

---

### 🛡️ Phase 5 Human Verification & Benchmark Gate

| Verification Checklist Item | Manual Human Test Action | Benchmark / Passing Criteria |
|---|---|---|
| **Patient Lookup UX** | Enter `P-98214` in Streamlit patient search bar | Displays `John Doe`, DOB `1982-05-14`, and `Penicillin` allergy badge |
| **Inline Editing Retention** | Modify Assessment text in Tab 1 before clicking Approve | Saved `soap_note.assessment` in Supabase reflects the physician's inline edit |
| **Doctor Workflow Measurement** | Time 3 end-to-end runs (Lookup -> Generate -> Review -> Edit -> Approve) | Measure and record total time across 3 test runs; evaluate against hypothesized **< 2 minute** target |

---

## Phase 6: Synthetic Evaluation, Security Audit & Release

### Subphase 6.1: Synthetic Evaluation Test Suite Execution
- **AI Work:** Create 8 automated test cases in `tests/` covering:
  1. **Content Quality Tests:**
     - `test_routine_visit_soap_generation()`
     - `test_allergy_contraindication_flagging()`
     - `test_incomplete_transcript_reviewer_warning()`
     - `test_audio_dictation_pipeline_end_to_end()`
  2. **Failure Injection Tests:**
     - `test_unresolved_patient_interrupt()`
     - `test_llm_retry_exhaustion()`
     - `test_whisper_error_fallback()`
     - `test_db_outage_503()`
- **Human Work:** Execute full automated test suite (`pytest tests/ -v`).

### Subphase 6.2: Security & HIPAA Telemetry Audit
- **AI Work:** Verify Python logger format prints JSON telemetry without raw transcript text.
- **Human Work:** Inspect server log files (`app.log`) and confirm zero PHI / PII text is present.

---

### 🛡️ Phase 6 Human Verification & Final Project Benchmarks

| Final Project Benchmark | Verification Method | Passing Criteria (Mandatory for Completion) |
|---|---|---|
| **Automated Test Suite Pass Rate** | Run `pytest tests/ -v` | **100% Pass Rate** across all 8 quality and failure-injection tests |
| **Zero PHI in Application Logs** | Search `app.log` for patient names or clinical text | **Zero PHI/PII matches** found (metadata logging only) |
| **Physician Gate Compliance** | Database audit check on `clinical_documents` table | **100% of persisted documents** have corresponding `doctor_id` approval audit log entry |
| **Non-Prescriptive Guardrail** | Review synthetic evaluation test outputs | **0% unmentioned medications** introduced by AI agents |
