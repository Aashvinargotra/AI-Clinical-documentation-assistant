# AI Clinical Documentation Assistant

An AI multi-agent system that converts doctor–patient consultation information into structured clinical documentation (SOAP notes, clinical summaries, treatment plans, follow-up checklists, and automated compliance reviews) while enforcing a strict **Human-in-the-Loop (HITL)** physician approval safety policy.

**Domain:** Healthcare

---

## 📚 Project Specifications & Documentation

The project specifications are consolidated into the `specs/` directory:

1. **[`specs/idea.md`](file:///c:/Users/aashv/OneDrive/Desktop/PROJECTS/ai_clinical_documentation_assistant/specs/idea.md)**: Problem analysis, business context, stakeholder requirements, design principles, and evaluation rubric.
2. **[`specs/design.md`](file:///c:/Users/aashv/OneDrive/Desktop/PROJECTS/ai_clinical_documentation_assistant/specs/design.md)**: **Single Canonical Master Design Spec** containing:
   - Multi-agent LangGraph workflow diagram and execution strategy.
   - Database DDL schema (PostgreSQL / Supabase) & Row-Level Security (RLS) policies.
   - Pydantic JSON schemas and safety prompt guardrails for all 6 agents.
   - `ConsultationStatus` canonical enum specifications.
   - FastAPI REST API contracts (including `/approve` and `/reject`).
   - Streamlit Human-in-the-Loop approval UI mockups.
   - Graph error handling, retry policies, and metadata-only HIPAA audit logging.

---

## 🏛️ Multi-Agent Architecture

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

---

## ⚖️ Safety & Compliance Disclaimer

> **IMPORTANT SAFETY NOTICE:**  
> This system operates strictly as an administrative drafting assistant. AI agents **summarize, format, and flag warnings**—they **never** prescribe medications, formulate autonomous diagnoses, or persist records without explicit physician review and approval.
> This software is a portfolio/assignment project and is **not** certified for live clinical deployment without formal regulatory and compliance review (HIPAA or local equivalent).
