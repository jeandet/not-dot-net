"""Pure-function workflow step machine. No DB, no side effects."""

from not_dot_net.backend.roles import Role, has_role
from not_dot_net.config import WorkflowConfig, WorkflowStepConfig


def get_current_step_config(request, workflow: WorkflowConfig) -> WorkflowStepConfig | None:
    """Get the step config for the request's current step."""
    for step in workflow.steps:
        if step.key == request.current_step:
            return step
    return None


def get_step_progress(request, workflow: WorkflowConfig) -> tuple[int, int]:
    """Return (current_step_1based, total_steps) for progress display.

    Terminal statuses (completed/rejected) return (total, total) or (0, total).
    """
    total = len(workflow.steps)
    if request.status == "completed":
        return (total, total)
    if request.status == "rejected":
        step_keys = [s.key for s in workflow.steps]
        idx = step_keys.index(request.current_step) if request.current_step in step_keys else 0
        return (idx + 1, total)
    step_keys = [s.key for s in workflow.steps]
    if request.current_step in step_keys:
        return (step_keys.index(request.current_step) + 1, total)
    return (0, total)


def get_available_actions(request, workflow: WorkflowConfig) -> list[str]:
    """Get actions available for the current step. Empty if request is terminal."""
    if request.status in ("completed", "rejected", "cancelled"):
        return []
    step = get_current_step_config(request, workflow)
    if step is None:
        return []
    actions = list(step.actions)
    if step.partial_save and "save_draft" not in actions:
        actions.append("save_draft")
    return actions


def compute_next_step(
    workflow: WorkflowConfig, current_step_key: str, action: str
) -> tuple[str | None, str]:
    """Given an action, return (next_step_key, new_status).

    Returns (None, "completed") if last step approved.
    Returns (None, "rejected") if rejected.
    """
    if action == "reject":
        return (None, "rejected")

    if action == "save_draft":
        return (current_step_key, "in_progress")

    # submit or approve → advance to next step
    step_keys = [s.key for s in workflow.steps]
    idx = step_keys.index(current_step_key)
    if idx + 1 < len(step_keys):
        return (step_keys[idx + 1], "in_progress")
    return (None, "completed")


def can_user_act(user, request, workflow: WorkflowConfig) -> bool:
    """Check if a user can act on the current step."""
    step = get_current_step_config(request, workflow)
    if step is None:
        return False

    # Role-based assignment
    if step.assignee_role:
        return has_role(user, Role(step.assignee_role))

    # Contextual assignment
    if step.assignee == "target_person":
        return user.email == request.target_email
    if step.assignee == "requester":
        return str(user.id) == str(request.created_by)

    # NOTE: `assignee: step:<key>:actor` is deferred to Plan 2/3 when event
    # history queries are wired up. Not needed for onboarding or VPN workflows.

    return False


def get_completion_status(
    request, step: WorkflowStepConfig, files: dict[str, bool]
) -> dict[str, bool]:
    """For a form step, return {field_name: is_filled} for required fields only."""
    status = {}
    for field in step.fields:
        if not field.required:
            continue
        if field.type == "file":
            status[field.name] = files.get(field.name, False)
        else:
            value = request.data.get(field.name)
            status[field.name] = bool(value)
    return status
