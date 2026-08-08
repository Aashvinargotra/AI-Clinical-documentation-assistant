# Engineering & Technical Execution Guide (`specs/engineering.md`)

## 1. Engineering Overview & Principles

The **AI Clinical Documentation Assistant** is built adhering to production-grade software engineering principles tailored for AI-assisted healthcare workflows.

### Core Engineering Principles
1. **Strict Type Safety & Schema Validation:** All data flowing between agents, backend services, API endpoints, and the database must be validated using Pydantic models (for API endpoints) and Python `TypedDict` (for LangGraph state machine).
2. **Multi-Provider Key Rotation & Failover:** LLM operations use a resilient key rotation manager (`LLMRotationManager`) supporting Groq, NVIDIA NIM, OpenRouter, Google Gemini, and OpenAI. If any provider hits a rate-limit (HTTP 429) or quota limit, the system automatically fails over to the next provider without crashing.
3. **Stateless API Gateway with In-Memory Orchestration:** FastAPI backend acts as a stateless gateway, delegating workflow state execution to LangGraph threads.
4. **Zero-PII Telemetry:** Logs record operational metrics (token count, latency, HTTP status, provider failovers, agent execution timing) without storing raw patient consultation text or protected health information (PHI).

---

## 2. Directory Structure & Module Breakdown

```
ai_clinical_documentation_assistant/
│
├── specs/
│   ├── idea.md                    <-- Business goals, requirements & rubric
│   ├── design.md                  <-- System design, schemas, API contracts & UI wireframes
│   └── engineering.md             <-- Technical execution, setup, testing & developer guide
│
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── history_agent.py       <-- Queries Supabase for past patient EHR & risk flags
│   │   ├── note_writer.py         <-- Converts consultation text into structured SOAP format
│   │   ├── summary_agent.py       <-- Synthesizes chief complaint, diagnosis & discharge summary
│   │   ├── treatment_agent.py     <-- Formats doctor-prescribed medications & monitoring orders
│   │   ├── followup_agent.py      <-- Generates follow-up dates, lab orders & patient instructions
│   │   └── reviewer.py            <-- Runs completeness validation, flags issues & ICD-10 suggestions
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py               <-- EXCLUSIVE HOME: Defines MedicalState TypedDict & initializers
│   │   └── workflow.py            <-- Compiles LangGraph StateGraph (Fan-out + Sequential)
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── supabase.py            <-- Supabase client, queries, RLS handlers & audit logging
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── whisper.py             <-- OpenAI Whisper audio transcription wrapper
│   │   └── llm_provider.py        <-- Multi-provider LLM key rotation & automatic failover engine
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── models.py              <-- API Pydantic models (ConsultationStatus, SOAPNote, API Requests)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints.py           <-- FastAPI routers (/transcribe, /process, /approve, /reject)
│   │
│   └── main.py                    <-- FastAPI app instantiation, CORS & server entrypoint
│
├── frontend/
│   └── streamlit_app.py           <-- Streamlit multi-screen UI & stateful API client
│
├── tests/                         <-- Unit & integration test suite
│   ├── test_agents.py             <-- Agent output schema & guardrail tests
│   ├── test_graph.py              <-- LangGraph fan-out, fan-in & interrupt tests
│   └── test_api.py                <-- FastAPI endpoint tests (/process, /approve, /reject)
│
├── docs/
│   └── architecture.png           <-- Diagram export
│
├── .env.example                   <-- Environment variables template with rotation keys
├── requirements.txt               <-- Python dependency specifications
└── README.md                      <-- Project overview & documentation index
```

---

## 3. Local Development & Setup Guide

### 3.1 Environment Prerequisites
- **Python:** 3.10 or higher
- **Git:** 2.30 or higher
- **Supabase Account:** Active PostgreSQL database project
- **LLM API Keys:** Groq, NVIDIA NIM, OpenRouter, Gemini, or OpenAI API key

### 3.2 Environment Template (`.env.example`)

Copy `.env.example` to `.env` in the project root directory:
```env
# Multi-Provider LLM API Configuration (Automatic Key Rotation & Failover)
GROQ_API_KEY=gsk_your_groq_key
NVIDIA_API_KEY=nvapi_your_nvidia_key
GEMINI_API_KEY=your_gemini_key
OPENROUTER_API_KEY=sk-or-v1_your_openrouter_key
OPENAI_API_KEY=sk-proj_your_openai_key

# Primary LLM Rotation Order (Comma-separated)
LLM_PROVIDER_ORDER=groq,nvidia,openrouter,gemini,openai

# Supabase Database Configuration
SUPABASE_URL=https://bvkdxgavyhbieayxeogu.supabase.co
SUPABASE_KEY=sb_publishable_-1t35nLcll3ird2wLmZf6Q_KiXXHGJQ

# Server Configuration
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
ENVIRONMENT=development
```

---

## 4. Execution & Running the Application

### 4.1 Running the Backend Server (FastAPI)

Launch the backend service using `uvicorn`:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive Swagger API docs: `http://localhost:8000/docs`
- ReDoc API documentation: `http://localhost:8000/redoc`

### 4.2 Running the Frontend Client (Streamlit)

In a separate terminal window:
```bash
streamlit run frontend/streamlit_app.py
```
- Local Web Interface: `http://localhost:8501`

---

## 5. Agent Development & Multi-Provider Rotation Pattern

### 5.1 Note Writer Agent Node Pattern
Every agent node in `backend/agents/` utilizes `llm_rotator.invoke_structured_chain_with_failover()`. If one key is rate-limited or exhausted, the rotator automatically fails over to the next provider in the chain (Groq → NVIDIA NIM → OpenRouter → Gemini → OpenAI):

```python
# backend/agents/note_writer.py
from langchain_core.prompts import ChatPromptTemplate
from backend.schemas.models import SOAPNote
from backend.graph.state import MedicalState
from backend.tools.llm_provider import llm_rotator

SYSTEM_PROMPT = """You are an expert Clinical Note Writer.
Your task is to convert raw doctor-patient consultation text into a structured SOAP note.

Rules:
1. Extract vital signs and physical exam findings only if present in the input. Do NOT fabricate numbers.
2. Subjective: Patient-reported history, symptoms, and chief complaint.
3. Objective: Physical exam findings, vital signs, lab values.
4. Assessment: Primary clinical diagnosis or impression.
5. Plan: Physician-stated treatment, prescriptions, and next steps.
"""

def clinical_note_writer_node(state: MedicalState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Consultation Transcript:\n{consultation_text}")
    ])
    
    # Executes with automatic multi-provider rotation & failover
    result: SOAPNote = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={"consultation_text": state["consultation_text"]},
        schema_model=SOAPNote,
        temperature=0.0
    )
    
    return {"soap_note": result.model_dump()}
```

---

### 5.2 Treatment Planner Non-Prescriptive Safety Guardrail Example

The system enforces a **strict non-prescriptive safety mandate** in `backend/agents/treatment_agent.py`:

```python
# backend/agents/treatment_agent.py
from langchain_core.prompts import ChatPromptTemplate
from backend.schemas.models import TreatmentPlan
from backend.graph.state import MedicalState
from backend.tools.llm_provider import llm_rotator

TREATMENT_SYSTEM_PROMPT = """You are a Clinical Treatment Formatting Assistant.

CRITICAL SAFETY MANDATE (STRICT NON-PRESCRIPTIVE GUARDRAIL):
1. You must ONLY format medications, dosages, and instructions EXPLICITLY stated by the attending physician in the SOAP plan or consultation text.
2. You are STRICTLY FORBIDDEN from independently prescribing new medications, suggesting dosage changes, or adding drugs not explicitly mentioned by the doctor.
3. Cross-check formatted medications against historical allergies ({allergies}). If a contraindication exists, include a warning flag in treatment_summary.
"""

def treatment_planner_node(state: MedicalState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", TREATMENT_SYSTEM_PROMPT),
        ("human", "SOAP Plan:\n{soap_plan}\n\nPatient History Allergies:\n{allergies}")
    ])
    
    result: TreatmentPlan = llm_rotator.invoke_structured_chain_with_failover(
        prompt_template=prompt,
        input_data={
            "soap_plan": state["soap_note"].get("plan", ""),
            "allergies": state["history"].get("allergies", [])
        },
        schema_model=TreatmentPlan,
        temperature=0.0
    )
    
    return {"treatment_plan": result.model_dump()}
```

---

### 5.3 Design.md Section 4.4 Failure Protocol Implementation Matrix

| Design.md §4.4 Failure Case | Target File | Implementation Mechanism & Behavior |
|---|---|---|
| **1. Unresolved Patient Record** | `backend/graph/workflow.py` | `INTERRUPT_UNRESOLVED_PATIENT` conditional edge triggers when History Agent returns `None`. Pauses execution and prompts UI for patient lookup. |
| **2. LLM Provider Key Exhaustion** | `backend/tools/llm_provider.py` | `LLMRotationManager` detects HTTP 429/quota error, logs failover warning, and automatically retries request via Groq → NVIDIA → OpenRouter → Gemini → OpenAI chain. |
| **3. Whisper Audio Failure** | `backend/api/endpoints.py` | Catch audio exception in FastAPI endpoint, set `status = "FAILED"`, and trigger Streamlit fallback text-dictation editor. |
| **4. Backend Process Restart** | `backend/graph/workflow.py` | `MemorySaver` in-process RAM reset mid-pipeline prompts doctor in Streamlit to re-trigger consultation execution. |
| **5. Supabase DB Outage** | `backend/memory/supabase.py` | `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))` wrapper. On failure, returns HTTP `503`, preserving edits in active session. |

---

## 6. LangGraph State Workflow Compilation

`backend/graph/workflow.py` constructs and compiles the state graph:

```python
# backend/graph/workflow.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from backend.graph.state import MedicalState # Exclusive TypedDict home
from backend.agents.history_agent import patient_history_node
from backend.agents.note_writer import clinical_note_writer_node
from backend.agents.summary_agent import medical_summary_node
from backend.agents.treatment_agent import treatment_planner_node
from backend.agents.followup_agent import followup_coordinator_node
from backend.agents.reviewer import documentation_reviewer_node

def route_patient_lookup(state: MedicalState) -> str:
    # Trigger interrupt node if History Agent fails to find matching patient row
    if not state.get("history") or state["history"].get("patient_unresolved"):
        return "INTERRUPT_UNRESOLVED_PATIENT"
    return "summary_agent"

def build_graph():
    builder = StateGraph(MedicalState)
    
    # 1. Add Agent Nodes
    builder.add_node("history_agent", patient_history_node)
    builder.add_node("note_writer", clinical_note_writer_node)
    builder.add_node("summary_agent", medical_summary_node)
    builder.add_node("treatment_agent", treatment_planner_node)
    builder.add_node("followup_agent", followup_coordinator_node)
    builder.add_node("reviewer_agent", documentation_reviewer_node)
    
    # 2. Parallel Fan-Out Edges (START -> History & Note Writer concurrently)
    builder.add_edge(START, "history_agent")
    builder.add_edge(START, "note_writer")
    
    # 3. Conditional Routing & Sequential Fan-In Edges
    builder.add_conditional_edges("history_agent", route_patient_lookup)
    builder.add_edge(["history_agent", "note_writer"], "summary_agent")
    builder.add_edge("summary_agent", "treatment_agent")
    builder.add_edge("treatment_agent", "followup_agent")
    builder.add_edge("followup_agent", "reviewer_agent")
    builder.add_edge("reviewer_agent", END)
    
    # 4. Compile with MemorySaver checkpointer
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)
```

---

## 7. Requirements Specification (`requirements.txt`)

```text
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9
streamlit>=1.31.0
langgraph>=0.1.0
langchain>=0.1.7
langchain-openai>=0.0.6
openai>=1.12.0
pydantic>=2.6.0
supabase>=2.3.0
tenacity>=8.2.3
python-dotenv>=1.0.0
httpx>=0.26.0
pytest>=8.0.0
```

---

## 8. Testing & Quality Assurance

### 8.1 Automated Test Execution
Run test suite using `pytest`:
```bash
pytest tests/ -v
```

### 8.2 Test Suite Categories

1. **Schema & Safety Guardrail Tests (`tests/test_agents.py`):**
   - Verify `Treatment Planner` raises a validation error if unmentioned medications are introduced.
   - Verify `Documentation Reviewer` output includes `passed_qc: bool` and flags missing fields.

2. **Graph Workflow & Provider Rotation Tests (`tests/test_graph.py`):**
   - **Multi-Provider Failover Test:** Verify `LLMRotationManager` automatically fails over to NVIDIA NIM when Groq returns HTTP 429.
   - **Unresolved Patient Interrupt:** Verify conditional router redirects to `INTERRUPT_UNRESOLVED_PATIENT` when history lookup returns `None`.
   - **Parallel Fan-Out Key Merge:** Verify `history_agent` and `note_writer` execution results merge without key collision in `MedicalState`.

3. **API Endpoint & Outage Tests (`tests/test_api.py`):**
   - Test `/api/v1/transcribe` multipart file upload handling.
   - Test `/api/v1/consultation/process`, `/approve`, and `/reject` endpoint responses.
   - **DB Outage Handling:** Verify API returns HTTP `503 Service Unavailable` when Supabase retry attempts exhaust.

---

## 9. Security, HIPAA Compliance & Logging Guidelines

1. **Log Configuration:** Configure Python `logging` to filter sensitive patient parameters. Log entries must follow standard JSON output format:
   ```json
   {
     "timestamp": "2026-08-08T14:55:00Z",
     "level": "INFO",
     "event": "PROVIDER_FAILOVER",
     "failed_provider": "Groq",
     "active_provider": "NVIDIA NIM",
     "consultation_id": "c7b2e8a1-4f90-41a2-8e3b-9a8f21e0b1a2",
     "latency_ms": 1150
   }
   ```
2. **Environment Variables Security:** Never commit `.env` or credentials to git repository (`.gitignore` enforces `.env` exclusion).
