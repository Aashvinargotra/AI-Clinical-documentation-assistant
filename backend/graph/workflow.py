"""LangGraph Workflow Compilation Engine.

Constructs and compiles the multi-agent state graph orchestrating parallel fan-out
execution of patient history retrieval and clinical SOAP note generation, followed by
conditional routing for unresolved patient records and sequential fan-in execution
of medical summary, treatment planning, follow-up coordination, and reviewer quality auditing.
"""

import logging
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from backend.graph.state import MedicalState
from backend.agents.history_agent import patient_history_node
from backend.agents.note_writer import clinical_note_writer_node
from backend.agents.summary_agent import medical_summary_node
from backend.agents.treatment_agent import treatment_planner_node
from backend.agents.followup_agent import followup_coordinator_node
from backend.agents.reviewer import documentation_reviewer_node

logger = logging.getLogger("workflow")


def route_patient_lookup(state: MedicalState) -> str:
    """Conditional router: checks if History Agent resolved the patient record.
    
    If patient history is missing or flagged as patient_unresolved, routes to
    INTERRUPT_UNRESOLVED_PATIENT interrupt node. Otherwise proceeds to summary_agent.
    """
    history = state.get("history")
    if not history or history.get("patient_unresolved"):
        logger.warning(
            f"Router: Unresolved patient detected for patient_id '{state.get('patient_id')}'. Routing to INTERRUPT_UNRESOLVED_PATIENT."
        )
        return "INTERRUPT_UNRESOLVED_PATIENT"
    return "summary_agent"


def unresolved_patient_node(state: MedicalState) -> Dict[str, Any]:
    """LangGraph node execution function for unresolved patient record interrupts."""
    patient_id = state.get("patient_id", "UNKNOWN")
    logger.warning(f"INTERRUPT_UNRESOLVED_PATIENT node executed for patient_id: '{patient_id}'")
    current_logs = list(state.get("error_logs") or [])
    error_msg = f"UNRESOLVED_PATIENT: Patient code '{patient_id}' not found in EHR database."
    if error_msg not in current_logs:
        current_logs.append(error_msg)
    return {
        "error_logs": current_logs
    }


def build_graph(checkpointer: Optional[Any] = None):
    """Builds and compiles the LangGraph StateGraph workflow with MemorySaver checkpointer support."""
    logger.info("Initializing LangGraph StateGraph for Medical Documentation Engine...")
    builder = StateGraph(MedicalState)

    # 1. Add All Agent & Interrupt Nodes
    builder.add_node("history_agent", patient_history_node)
    builder.add_node("note_writer", clinical_note_writer_node)
    builder.add_node("INTERRUPT_UNRESOLVED_PATIENT", unresolved_patient_node)
    builder.add_node("summary_agent", medical_summary_node)
    builder.add_node("treatment_agent", treatment_planner_node)
    builder.add_node("followup_agent", followup_coordinator_node)
    builder.add_node("reviewer_agent", documentation_reviewer_node)

    # 2. Parallel Fan-Out Edges (START -> History Agent & Note Writer concurrently)
    builder.add_edge(START, "history_agent")
    builder.add_edge(START, "note_writer")

    # 3. Conditional Routing from History Agent
    builder.add_conditional_edges(
        "history_agent",
        route_patient_lookup,
        {
            "INTERRUPT_UNRESOLVED_PATIENT": "INTERRUPT_UNRESOLVED_PATIENT",
            "summary_agent": "summary_agent"
        }
    )

    # 4. Edges for Interrupt and Sequential Pipeline
    builder.add_edge("INTERRUPT_UNRESOLVED_PATIENT", END)
    builder.add_edge(["history_agent", "note_writer"], "summary_agent")
    builder.add_edge("summary_agent", "treatment_agent")
    builder.add_edge("treatment_agent", "followup_agent")
    builder.add_edge("followup_agent", "reviewer_agent")
    builder.add_edge("reviewer_agent", END)

    # 5. Compile Graph Engine with MemorySaver checkpointer
    if checkpointer is None:
        checkpointer = MemorySaver()

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("LangGraph workflow compiled with MemorySaver checkpointer successfully.")
    return graph

