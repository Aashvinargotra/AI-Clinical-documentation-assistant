# AI Clinical Documentation Assistant

An AI multi-agent system that converts doctor–patient consultation information into structured clinical documentation, discharge summaries, follow-up plans, and organized medical records.

**Domain:** Healthcare

---

## 1. Problem Analysis

### Business Context
Doctors spend a significant amount of time writing documentation instead of treating patients. Manual documentation causes:
- Physician burnout
- Inconsistent records
- Missing information
- Delayed discharge summaries
- Poor follow-up management

Hospitals need an assistant that automatically converts consultation data into structured documentation, while keeping the physician firmly in control of what gets saved.

### Stakeholders

**Primary**
- Doctors
- Nurses
- Specialists

**Secondary**
- Hospital administrators
- Medical coders
- Patients

### Problem Statement
Healthcare professionals spend excessive time documenting consultations manually, resulting in increased administrative burden, inconsistent clinical notes, delayed discharge summaries, and poor follow-up coordination. An AI-powered multi-agent assistant can automate documentation while keeping physicians in control through approval workflows.

### Objectives
- Summarize consultations
- Create structured SOAP notes
- Organize patient history
- Generate discharge summaries
- Suggest follow-up actions
- Maintain structured documentation
- Require doctor approval before anything is saved

### Design Principle (Safety)
Agents **summarize, organize, and flag** — they never generate a diagnosis or a medication the doctor did not already indicate. All clinical judgment stays with the physician; the system's job is to reduce the paperwork around that judgment, not to replace it.

---

## 2. Multi-Agent Design

### Agent Architecture

```
                        Doctor
                          │
                Text / Audio Upload
                          │
                   Whisper (optional)
                          │
                  Orchestrator Agent
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
       History Agent          Clinical Note Writer
              │                       │
              └───────────┬───────────┘
                           ▼
                   Medical Summary Agent
                           │
                           ▼
                    Treatment Planner
                           │
                           ▼
                 Follow-up Coordinator
                           │
                           ▼
                Documentation Reviewer
                           │
                           ▼
                Doctor Approval UI
                           │
                           ▼
                     Supabase (DB)
```

> **Why this shape:** History Agent only needs the patient ID (not the current consultation), so it can run in parallel with Clinical Note Writer. Everything downstream — Summary, Treatment Planner, Follow-up — depends on the SOAP note's `assessment`/`plan`, so those stay sequential. This replaces the three inconsistent diagrams from the earlier draft with one flow used everywhere in the project (docs, code, and demo).

### Roles of Each Agent

**1. Patient History Agent**
Organizes previous visits, allergies, medications, surgeries, chronic diseases, family history.

- Input: Patient ID → patient records
- Output:
```json
{
  "history": {},
  "allergies": [],
  "current_medications": [],
  "risk_flags": []
}
```

**2. Clinical Note Writer**
Creates a structured SOAP note from the raw consultation (text or transcribed audio).

- Output:
```json
{
  "soap": {
    "subjective": "",
    "objective": "",
    "assessment": "",
    "plan": ""
  }
}
```

**3. Medical Summary Agent**
Produces the consultation summary, discharge summary, and referral summary — pulling from both the SOAP note and patient history.

- Output:
```json
{
  "summary": "",
  "diagnosis": "",
  "key_findings": []
}
```

**4. Treatment Planner**
Does **not** prescribe. It organizes what the physician already decided:
- Formats medications already chosen
- Highlights monitoring requirements
- Drafts follow-up recommendations

- Output:
```json
{
  "treatment_plan": "",
  "medications": [],
  "followup_recommendation": ""
}
```

**5. Follow-up Coordinator**
Creates reminders, appointment slots, a monitoring checklist, and patient instructions.

- Output:
```json
{
  "followup_date": "",
  "tests": [],
  "patient_instructions": ""
}
```

**6. Documentation Reviewer**
Checks the assembled record for missing fields, inconsistent notes, formatting issues, duplicated information, and (optionally) ICD coding suggestions.

- Output:
```json
{
  "issues": [],
  "warnings": [],
  "approved": false
}
```

### Agent Interaction & Handoff Flow
1. Doctor uploads consultation (text or audio)
2. **History Agent** and **Clinical Note Writer** run in parallel
3. **Medical Summary Agent** consumes both outputs
4. **Treatment Planner** consumes the summary + SOAP plan
5. **Follow-up Coordinator** consumes the treatment plan
6. **Documentation Reviewer** checks the full assembled record
7. **Doctor Approval UI** — approve / edit / reject
8. On approval only → **Supabase** save

### Tool Integration Overview

| Tool | Purpose |
|---|---|
| OpenAI API | LLM reasoning for all six agents |
| Whisper API | Speech-to-text consultation transcription |
| Supabase | Patient/document storage, session state |
| LangGraph | Multi-agent orchestration and state graph |
| FastAPI | Backend API layer |
| Streamlit | Frontend (data entry + approval UI) |
| Tavily Search *(optional)* | Retrieve clinical guidelines / public references |

---

## 3. Implementation

### Agents (6, minimum 5 required)
History Agent, Clinical Note Writer, Medical Summary Agent, Treatment Planner, Follow-up Coordinator, Documentation Reviewer.

### Tools/APIs (6, minimum 5 required)
OpenAI API, Whisper API, Supabase, LangGraph, FastAPI, Streamlit.

### Agent Handoffs
Handled via LangGraph's state graph — each agent reads the fields it needs from shared state and writes its own output back in, rather than passing free-text between agents. See state shape below.

### Memory / Context Management

**Short-term (in-session)**
- Conversation state
- Consultation transcript
- Doctor edits made during the approval step

**Long-term (Supabase)**
- Patient history across visits
- Allergies
- Medications
- Follow-ups

**LangGraph State Object**
```python
state = {
    "patient_id": "",
    "history": {},
    "consultation": "",
    "soap_note": {},
    "summary": {},
    "treatment": {},
    "followup": {},
    "review": {}
}
```

### Structured Outputs
Every agent returns JSON (schemas above) rather than free text, so the frontend can render editable fields instead of a wall of prose, and the Reviewer can programmatically check for missing keys.

### Human Approval
Before saving, the doctor sees:
- Generated SOAP note
- Summary
- Treatment plan
- Follow-up plan

With three actions: **Approve**, **Edit**, **Reject**. Only an approved record is written to Supabase.

### Privacy & Compliance Notes
Since this handles patient history, allergies, and medications:
- Row-level access control on Supabase (a doctor sees only their own patients)
- No PII in application logs — log agent execution/timing/status, not patient content
- Data encrypted at rest (Supabase default) and in transit (HTTPS)
- This is a portfolio/assignment project, not a certified clinical system — README should state it is **not** for real patient use without proper compliance review (HIPAA or local equivalent)

---

## 4. Advanced Features (Optional / Stretch)

- **Planning:** Orchestrator dynamically skips agents based on available input — e.g., if there's no discharge context, Summary Agent produces only a consultation summary, not a discharge summary.
- **RAG:** Retrieve from a small set of hospital SOPs, discharge templates, and documentation standards to ground the Clinical Note Writer and Reviewer. Scoped to 3–4 sample documents for the assignment, not a full corpus.
- **Long-term memory:** Each visit updates the patient timeline — medications, diagnoses, labs, surgeries — in Supabase.
- **Reflection:** Documentation Reviewer explicitly checks: Is the allergy section missing? Is assessment empty? Is medication duplicated? Is follow-up missing? Does the summary contradict the history?
- **Parallel execution:** History Agent + Clinical Note Writer run concurrently (see architecture diagram).
- **Error handling & logging:**
  - Missing patient ID → ask doctor
  - Incomplete consultation → ask for clarification
  - Database failure → retry
  - LLM timeout → retry once, then fallback response
  - Log timestamps, agent execution, latency, approval status, errors
- **Multi-modal input:** Typed consultation, uploaded audio, dictated speech now; PDF lab reports and OCR on handwritten notes listed as future work (not MVP-critical).
- **Session persistence:** Resume unfinished documentation if the session is interrupted.

---

## 5. Deliverables

| Deliverable | Status | Notes |
|---|---|---|
| Complete source code | ☐ | Backend (FastAPI + LangGraph agents) + Frontend (Streamlit) |
| Agent architecture diagram | ☐ | Export the Section 2 diagram as `docs/architecture.png` |
| Project documentation | ☐ | This file + inline docstrings + `/docs` folder |
| GitHub repository with README | ☐ | Setup instructions, env vars, safety/compliance note, architecture summary |
| Demo video (5–10 min) | ☐ | Walk through: upload consultation → agent pipeline → doctor approval → saved record |
| Presentation (10–12 slides) | ☐ | Problem → architecture → agent roles → demo screenshots → advanced features → learnings |

### Testing / Evaluation Approach
- Build 3–5 synthetic sample consultations (varying completeness: full visit, missing allergies, missing follow-up) to test the Reviewer's ability to flag real issues.
- Manually verify each agent's JSON output matches its schema before wiring into the next agent.
- Confirm no record reaches Supabase without an explicit "Approve" from the doctor persona in the demo.

---

## 6. MVP Scope (What to Actually Build)

To keep the project achievable within internship timelines while still satisfying the full rubric:

- **Frontend:** Streamlit — patient details + consultation text/audio entry + approval screen.
- **Backend:** FastAPI with LangGraph orchestrating the six agents (History + Clinical Note in parallel; rest sequential).
- **AI:** OpenAI API for generation, Whisper for optional transcription.
- **Database:** Supabase for patient records, generated notes, and session state.
- **Workflow:** Consultation → (History ∥ Clinical Note) → Summary → Treatment Planner → Follow-up → Reviewer → Doctor Approval → Save.
- **Outputs:** Structured JSON per agent, rendered as readable SOAP note, discharge summary, and follow-up instructions.

**Build first (core rubric):** All 6 agents, LangGraph orchestration with one parallel branch, structured outputs, Supabase persistence, Streamlit approval UI, basic retry/error handling, logging.

**Add if time allows (stretch):** Whisper transcription, small-scale RAG over sample hospital SOPs.

**Cut first if behind schedule:** OCR for handwritten notes, PDF lab report ingestion, full session-resume — keep these as "future work" in the presentation rather than build targets.

---

## 7. Folder Structure

```
clinical-documentation-assistant/
│
├── backend/
│   ├── agents/
│   │     history_agent.py
│   │     note_writer.py
│   │     summary_agent.py
│   │     treatment_agent.py
│   │     followup_agent.py
│   │     reviewer.py
│   │
│   ├── graph/
│   │     workflow.py
│   │
│   ├── memory/
│   │     supabase.py
│   │
│   ├── tools/
│   │     whisper.py
│   │     openai.py
│   │
│   ├── schemas/
│   ├── api/
│   └── main.py
│
├── frontend/
│      streamlit_app.py
│
├── docs/
│      architecture.png
│      idea.md
│
├── README.md
│
└── requirements.txt
```
