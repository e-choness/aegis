from __future__ import annotations

import pytest

from src.aegis.services.conversation_storage import ConversationStorage
from src.aegis.services.langgraph_gateway import LangGraphGateway, WorkflowDefinition
from src.aegis.services.team_context import TeamContextManager
from src.aegis.services.tool_registry import ToolRegistry
from src.aegis.services.workflow_checkpoint import WorkflowCheckpointStore
from src.aegis.services.workflow_engine import WorkflowEngine
from src.aegis.services.workflow_queue import WorkflowQueue
from src.aegis.tools import register_builtin_tools


async def _engine_with_workflows(team_manager: TeamContextManager) -> WorkflowEngine:
    registry = ToolRegistry(team_context_manager=team_manager)
    register_builtin_tools(registry)
    gateway = LangGraphGateway(tool_registry=registry)
    await gateway.register_workflow(
        WorkflowDefinition(
            workflow_id="research",
            name="Research Workflow",
            description="Search and summarize",
            tier_requirement=1,
            data_classification="PUBLIC",
            allowed_tools=["web_search"],
            cost_estimate_usd=0.02,
        )
    )
    await gateway.register_workflow(
        WorkflowDefinition(
            workflow_id="expensive",
            name="Expensive Workflow",
            description="Costs too much for low-budget teams",
            allowed_tools=[],
            cost_estimate_usd=5.0,
        )
    )
    return WorkflowEngine(
        langgraph_gateway=gateway,
        conversation_storage=ConversationStorage(),
        checkpoint_store=WorkflowCheckpointStore(),
        workflow_queue=WorkflowQueue(),
        team_context_manager=team_manager,
    )


@pytest.fixture
def team_manager():
    manager = TeamContextManager()
    manager.register_team(
        "team-a",
        members={"alice"},
        permissions={"execute_workflow", "use_web_tools", "use_data_tools"},
        budget_remaining_usd=10.0,
    )
    manager.register_team(
        "team-low",
        members={"lou"},
        permissions={"execute_workflow", "use_web_tools"},
        budget_remaining_usd=0.01,
    )
    return manager


@pytest.mark.asyncio
async def test_execute_workflow_persists_status_history_and_checkpoints(team_manager):
    engine = await _engine_with_workflows(team_manager)
    context = team_manager.build_context("team-a", "alice")

    result = await engine.execute_workflow(
        context,
        "research",
        {"query": "What is RAG?", "max_results": 2},
    )

    assert result.status == "completed"
    assert result.workflow_id == "research"
    assert result.tool_calls[0]["tool"] == "web_search"
    assert result.output_data["tool_call_count"] == 1

    status = engine.get_workflow_status(result.workflow_instance_id)
    assert status is not None
    assert status.team_id == "team-a"
    assert status.status == "completed"
    assert status.tool_calls_count == 1

    history = await engine.get_conversation_history(result.workflow_instance_id)
    assert [message.role for message in history] == ["user", "assistant"]

    checkpoints = await engine.checkpoint_store.list_checkpoints(result.workflow_instance_id)
    assert [checkpoint.step_name for checkpoint in checkpoints] == ["started", "completed"]


@pytest.mark.asyncio
async def test_workflow_budget_failure_is_recorded(team_manager):
    engine = await _engine_with_workflows(team_manager)
    context = team_manager.build_context("team-low", "lou")

    result = await engine.execute_workflow(context, "expensive", {"query": "costly"})

    assert result.status == "failed"
    assert result.error == "Insufficient team budget for workflow"
    status = engine.get_workflow_status(result.workflow_instance_id)
    assert status is not None
    assert status.status == "failed"


@pytest.mark.asyncio
async def test_conversation_storage_is_team_scoped(team_manager):
    engine = await _engine_with_workflows(team_manager)
    context = team_manager.build_context("team-a", "alice")
    result = await engine.execute_workflow(context, "research", {"query": "tenant data"})

    team_a_conversations = await engine.conversation_storage.list_conversations("team-a")
    team_b_conversations = await engine.conversation_storage.list_conversations("team-b")

    assert len(team_a_conversations) == 1
    assert team_a_conversations[0]["conversation_id"] == result.conversation_id
    assert team_b_conversations == []


@pytest.mark.asyncio
async def test_resume_workflow_appends_user_message(team_manager):
    engine = await _engine_with_workflows(team_manager)
    context = team_manager.build_context("team-a", "alice")
    result = await engine.execute_workflow(context, "research", {"query": "first"})

    resumed = await engine.resume_workflow(result.workflow_instance_id, "follow up")

    assert resumed.status == "completed"
    history = await engine.get_conversation_history(result.workflow_instance_id)
    assert [message.role for message in history] == ["user", "assistant", "user", "assistant"]


@pytest.mark.asyncio
async def test_workflow_queue_orders_by_priority(team_manager):
    engine = await _engine_with_workflows(team_manager)
    context = team_manager.build_context("team-a", "alice")

    low = await engine.queue_workflow(context, "research", {"query": "low"}, priority=1)
    high = await engine.queue_workflow(context, "research", {"query": "high"}, priority=10)

    queued = await engine.workflow_queue.list_queue("team-a")
    assert [item["queue_id"] for item in queued] == [high, low]
