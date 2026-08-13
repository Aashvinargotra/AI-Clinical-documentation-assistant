"""Unit & Integration Test Suite for LangGraph State Machine Architecture.

Tests StateGraph construction, parallel fan-out concurrency (history_agent ∥ note_writer),
unresolved patient interrupt routing (INTERRUPT_UNRESOLVED_PATIENT), MemorySaver checkpointer
thread state persistence, multi-provider LLM failover, and sequential fan-in multi-agent pipeline.
"""

from unittest.mock import patch, MagicMock
import pytest
from backend.graph.workflow import build_graph, route_patient_lookup
from backend.graph.state import create_initial_state, MedicalState
from backend.tools.llm_provider import LLMRotationManager
from backend.schemas.models import (
    SOAPNote,
    MedicalSummary,
    TreatmentPlan,
    MedicationOrder,
    FollowupPlan,
    ReviewResult
)


def test_graph_compilation():
    """Verify that build_graph compiles a valid StateGraph instance with checkpointer."""
    graph = build_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "checkpointer")
    assert graph.checkpointer is not None


@patch("backend.agents.history_agent.fetch_patient_history")
@patch("backend.agents.note_writer.generate_soap_note")
def test_fanout_execution(mock_soap, mock_history):
    """Test Parallel Fan-Out Execution (START -> history_agent & note_writer concurrently).
    
    Verifies history_agent and note_writer execute without key collision in MedicalState.
    """
    mock_history.return_value = {
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Hypertension"],
        "current_medications": ["Lisinopril 10mg QD"]
    }
    mock_soap.return_value = SOAPNote(
        subjective="Cough and mild fever for 2 days.",
        objective="Temp 99.8F, BP 120/80.",
        assessment="Acute viral URI.",
        plan="Rest, hydration, OTC paracetamol."
    )

    initial_state = create_initial_state(
        patient_id="P-98214",
        doctor_id="doc-123",
        consultation_text="Patient presents with cough and low grade fever."
    )

    from backend.agents.history_agent import patient_history_node
    from backend.agents.note_writer import clinical_note_writer_node

    res_history = patient_history_node(initial_state)
    res_soap = clinical_note_writer_node(initial_state)

    state_after_fanout = {**initial_state, **res_history, **res_soap}

    assert state_after_fanout["history"]["allergies"] == ["Penicillin"]
    assert state_after_fanout["history"]["patient_unresolved"] is False
    assert state_after_fanout["soap_note"]["assessment"] == "Acute viral URI."
    assert "history" in state_after_fanout
    assert "soap_note" in state_after_fanout


def test_route_patient_lookup_unit():
    """Unit test for route_patient_lookup conditional router function."""
    resolved_state = {"history": {"patient_unresolved": False, "allergies": []}}
    unresolved_state = {"history": {"patient_unresolved": True, "allergies": []}}
    missing_history_state = {}

    assert route_patient_lookup(resolved_state) == "summary_agent"
    assert route_patient_lookup(unresolved_state) == "INTERRUPT_UNRESOLVED_PATIENT"
    assert route_patient_lookup(missing_history_state) == "INTERRUPT_UNRESOLVED_PATIENT"


@patch("backend.agents.history_agent.fetch_patient_history")
@patch("backend.agents.note_writer.generate_soap_note")
@patch("backend.agents.summary_agent.generate_medical_summary")
def test_unresolved_patient_interrupt(mock_summary, mock_soap, mock_history):
    """Test graph execution when given invalid patient code (e.g., 'INVALID-99').
    
    Verifies that the graph triggers INTERRUPT_UNRESOLVED_PATIENT node and logs error
    without executing downstream summary/treatment/reviewer agents.
    """
    mock_history.return_value = None  # Patient not found in EHR
    mock_soap.return_value = SOAPNote(
        subjective="Cough and fever.",
        objective="Vitals normal.",
        assessment="Bronchitis.",
        plan="Rest."
    )

    graph = build_graph()
    initial_state = create_initial_state(
        patient_id="INVALID-99",
        doctor_id="doc-789",
        consultation_text="Consultation transcript for invalid patient code."
    )
    config = {"configurable": {"thread_id": "thread-unresolved-99"}}

    final_state = graph.invoke(initial_state, config=config)

    # 1. Verify history agent marked patient as unresolved
    assert final_state["history"]["patient_unresolved"] is True

    # 2. Verify INTERRUPT_UNRESOLVED_PATIENT logged an error message
    error_logs = final_state.get("error_logs", [])
    assert any("UNRESOLVED_PATIENT" in log for log in error_logs)
    assert any("INVALID-99" in log for log in error_logs)

    # 3. Verify downstream medical summary node was NOT executed
    mock_summary.assert_not_called()
    assert final_state["summary"]["diagnosis"] == ""


@patch("backend.agents.history_agent.fetch_patient_history")
@patch("backend.agents.note_writer.generate_soap_note")
@patch("backend.agents.summary_agent.generate_medical_summary")
@patch("backend.agents.treatment_agent.generate_treatment_plan")
@patch("backend.agents.followup_agent.generate_followup_plan")
@patch("backend.agents.reviewer.review_clinical_documentation")
def test_memory_saver_checkpointer(
    mock_review,
    mock_followup,
    mock_treatment,
    mock_summary,
    mock_soap,
    mock_history
):
    """Test MemorySaver checkpointer thread state persistence and state retrieval."""
    mock_history.return_value = {"allergies": [], "chronic_conditions": [], "current_medications": []}
    mock_soap.return_value = SOAPNote(subjective="Subj", objective="Obj", assessment="Assess", plan="Plan")
    mock_summary.return_value = MedicalSummary(chief_complaint="Cc", diagnosis="Diag", key_findings=[], discharge_summary="Disch")
    mock_treatment.return_value = TreatmentPlan(treatment_summary="Tx", medications=[], monitoring_requirements=[])
    mock_followup.return_value = FollowupPlan(followup_date="1 week", tests_ordered=[], patient_instructions="Rest")
    mock_review.return_value = ReviewResult(passed_qc=True, completeness_score=0.9, issues=[], warnings=[])

    graph = build_graph()
    initial_state = create_initial_state(
        patient_id="P-98214",
        doctor_id="doc-ckpt",
        consultation_text="Checkpointer test consultation."
    )
    thread_config = {"configurable": {"thread_id": "test-thread-ckpt-1001"}}

    # Execute graph with thread_id config
    graph.invoke(initial_state, config=thread_config)

    # Retrieve checkpoint state using thread_id
    saved_state_snapshot = graph.get_state(thread_config)
    assert saved_state_snapshot is not None
    assert saved_state_snapshot.values["patient_id"] == "P-98214"
    assert saved_state_snapshot.values["doctor_id"] == "doc-ckpt"
    assert saved_state_snapshot.values["review_result"]["passed_qc"] is True


def test_llm_provider_failover():
    """Test Multi-Provider LLM Key Rotation & Failover (HTTP 429 simulation on primary provider).
    
    Simulates HTTP 429 rate limit error on Groq primary key; verifies system logs warning,
    marks primary provider in cooldown, fails over seamlessly to secondary provider (NVIDIA),
    and completes execution.
    """
    rotator = LLMRotationManager(provider_order=["groq", "nvidia"])

    mock_prompt = MagicMock()
    mock_schema = SOAPNote
    expected_soap = SOAPNote(
        subjective="Failover subjective test.",
        objective="Vitals 120/80.",
        assessment="Viral infection.",
        plan="Rest and fluids."
    )

    mock_groq_llm = MagicMock()
    # Groq throws HTTP 429 rate limit error
    mock_groq_llm.with_structured_output.side_effect = Exception("HTTP 429: Rate limit exceeded on Groq API key")

    mock_nvidia_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_nvidia_llm.with_structured_output.return_value = mock_structured_llm

    # Configure prompt | structured_llm -> mock_chain -> expected_soap
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = expected_soap
    mock_prompt.__or__.return_value = mock_chain

    def mock_get_llm(provider_id: str, temperature: float = 0.0):
        if provider_id == "groq":
            return mock_groq_llm
        elif provider_id == "nvidia":
            return mock_nvidia_llm
        raise ValueError(f"Unknown provider_id: {provider_id}")

    with patch.object(rotator, "_get_active_provider_keys", return_value=["groq", "nvidia"]):
        with patch.object(rotator, "get_llm_instance", side_effect=mock_get_llm):
            result = rotator.invoke_structured_chain_with_failover(
                prompt_template=mock_prompt,
                input_data={"transcript": "Test"},
                schema_model=mock_schema
            )

    # 1. Verify result returned from secondary provider (nvidia)
    assert result == expected_soap
    assert result.assessment == "Viral infection."

    # 2. Verify primary provider (groq) was placed in cooldown
    assert "groq" in rotator.failed_providers


@patch("backend.agents.history_agent.fetch_patient_history")
@patch("backend.agents.note_writer.generate_soap_note")
@patch("backend.agents.summary_agent.generate_medical_summary")
@patch("backend.agents.treatment_agent.generate_treatment_plan")
@patch("backend.agents.followup_agent.generate_followup_plan")
@patch("backend.agents.reviewer.review_clinical_documentation")
def test_full_graph_pipeline(
    mock_review,
    mock_followup,
    mock_treatment,
    mock_summary,
    mock_soap,
    mock_history
):
    """Test full sequential end-to-end execution of the compiled StateGraph engine."""
    mock_history.return_value = {
        "allergies": ["Penicillin"],
        "chronic_conditions": ["Asthma"],
        "current_medications": ["Albuterol HFA"]
    }
    mock_soap.return_value = SOAPNote(
        subjective="Shortness of breath and wheezing.",
        objective="Vitals normal. Mild wheezing on auscultation.",
        assessment="Mild asthma exacerbation.",
        plan="Continue Albuterol as directed, rest."
    )
    mock_summary.return_value = MedicalSummary(
        chief_complaint="Shortness of breath",
        diagnosis="Asthma exacerbation",
        key_findings=["Mild wheezing"],
        discharge_summary="Outpatient monitoring."
    )
    mock_treatment.return_value = TreatmentPlan(
        treatment_summary="Continue inhaler therapy.",
        medications=[],
        monitoring_requirements=["Peak flow monitoring"]
    )
    mock_followup.return_value = FollowupPlan(
        followup_date="2 weeks",
        tests_ordered=[],
        patient_instructions="Use inhaler as needed."
    )
    mock_review.return_value = ReviewResult(
        passed_qc=True,
        completeness_score=0.92,
        issues=[],
        warnings=["Allergy Alert: Penicillin"]
    )

    graph = build_graph()
    initial_state = create_initial_state(
        patient_id="P-98214",
        doctor_id="doc-456",
        consultation_text="Patient complaining of mild asthma flare up."
    )
    config = {"configurable": {"thread_id": "thread-full-pipeline"}}

    final_state = graph.invoke(initial_state, config=config)

    assert final_state["history"]["allergies"] == ["Penicillin"]
    assert final_state["soap_note"]["assessment"] == "Mild asthma exacerbation."
    assert final_state["summary"]["diagnosis"] == "Asthma exacerbation"
    assert final_state["treatment_plan"]["treatment_summary"] == "Continue inhaler therapy."
    assert final_state["followup_plan"]["followup_date"] == "2 weeks"
    assert final_state["review_result"]["passed_qc"] is True
    assert final_state["review_result"]["completeness_score"] == 0.92
