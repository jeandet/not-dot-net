"""Tests for the new-request tab — workflow listing and rendering."""

from types import SimpleNamespace

import pytest
from nicegui import ui
from nicegui.testing import User

from not_dot_net.backend.workflow_service import workflows_config, WorkflowsConfig
from not_dot_net.config import WorkflowConfig, WorkflowStepConfig


@pytest.fixture
async def admin_user():
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        email="admin@test",
        is_superuser=True,
        is_active=True,
        role="admin",
    )


async def test_new_request_skips_workflows_without_steps(user: User, admin_user):
    """Reproducer: a workflow with no steps must not crash the new-request page."""
    from not_dot_net.frontend.new_request import render
    await workflows_config.set(WorkflowsConfig(workflows={
        "empty": WorkflowConfig(label="Empty", steps=[]),
        "good": WorkflowConfig(label="Good", steps=[
            WorkflowStepConfig(key="s", type="form"),
        ]),
    }))

    @ui.page("/_nr_empty")
    async def _page():
        await render(admin_user)

    await user.open("/_nr_empty")
    # The "Good" workflow card must render; the "Empty" one must be skipped silently.
    await user.should_see("Good")
    await user.should_not_see("Empty")
