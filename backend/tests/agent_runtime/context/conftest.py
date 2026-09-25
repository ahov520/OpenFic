from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from app.agent_runtime.graph.state import AgentRuntimeState


@pytest.fixture(autouse=True)
def _stub_lore_part():
    """Stub the lore part for build_context tests.

    build_lore_pack queries characters/world info/chapter titles through
    ``session.execute()`` chains, which a plain ``AsyncMock`` session cannot
    express (``result.scalars().all()`` breaks). Tests here examine other
    parts, so lore is stubbed out the same way as rules/skills.
    """
    with patch(
        "app.agent_runtime.context.build_context.build_lore_pack",
        new=AsyncMock(return_value=None),
    ):
        yield


@pytest.fixture
def mock_session():
    """A mocked AsyncSession that returns AsyncMock for any awaited call."""
    return AsyncMock()


@pytest.fixture
def base_state() -> AgentRuntimeState:
    return {
        "session_id": "sess_test",
        "task_id": "task_test",
        "project_id": "proj_test",
        "model_config": {
            "provider_type": "openai",
            "model_id": "gpt-test",
            "api_key": "k",
            "base_url": "",
            "max_context_tokens": 100_000,
        },
        "active_agent": None,
        "is_completed": False,
        "error": None,
        "retry_count": 0,
        "user_request": "test",
        "current_revision_id": None,
    }


@pytest.fixture
def make_state(base_state):
    def _factory(**overrides: Any) -> AgentRuntimeState:
        merged: dict[str, Any] = {**base_state, **overrides}
        return cast(AgentRuntimeState, merged)
    return _factory
