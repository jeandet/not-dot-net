from typing import Any, Literal

from pydantic import BaseModel, Field

from not_dot_net.backend.app_config import section


# --- Workflow schema models (imported by notifications.py, workflow_engine.py, etc.) ---

class FieldConfig(BaseModel):
    name: str
    type: str  # text, email, textarea, date, select, file, phone, location, checkbox
    required: bool = False
    label: str = ""
    options_key: str | None = None  # for select: key in Settings (e.g. "teams")
    encrypted: bool = False
    half_width: bool = False
    visible_when: dict[str, Any] | None = None


def is_field_visible(field: FieldConfig, data: dict) -> bool:
    """A field is visible iff every (key, value) in `visible_when` matches `data`.
    No rule means always visible. Missing keys are treated as mismatches."""
    rule = field.visible_when
    if not rule:
        return True
    return all(data.get(k) == v for k, v in rule.items())


class NotificationRuleConfig(BaseModel):
    event: str  # submit, approve, reject
    step: str | None = None  # None = match any step
    notify: list[str]  # role names or contextual: requester, target_person


class StepEffectConfig(BaseModel):
    on_action: str
    kind: Literal[
        "ad_add_to_groups",
        "ad_remove_from_groups",
        "ad_enable_account",
        "ad_disable_account",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepConfig(BaseModel):
    key: str
    type: str  # form, approval
    assignee_role: str | None = None
    assignee_permission: str | None = None
    assignee: str | None = None  # contextual: target_person, requester
    fields: list[FieldConfig] = []
    actions: list[str] = []
    partial_save: bool = False
    corrections_target: str | None = None
    effects: list[StepEffectConfig] = Field(default_factory=list)


class WorkflowConfig(BaseModel):
    label: str
    start_role: str = "staff"
    target_email_field: str | None = None
    steps: list[WorkflowStepConfig]
    notifications: list[NotificationRuleConfig] = []
    document_instructions: dict[str, list[str]] = {}


# --- OrgConfig section ---

class OrgConfig(BaseModel):
    app_name: str = "LPP Intranet"
    base_url: str = "http://localhost:8088"
    teams: list[str] = [
        "Plasma Physics",
        "Instrumentation",
        "Space Weather",
        "Theory & Simulation",
        "Administration",
    ]
    sites: list[str] = ["Palaiseau", "Jussieu"]
    employment_statuses: list[str] = ["CDD", "CDI", "Intern", "PhD", "PostDoc", "Visiting Researcher"]
    employers: list[str] = ["CNRS", "Sorbonne Université", "Polytechnique", "CNES", "Other"]
    transport_modes: list[str] = ["Train", "Avion", "Voiture personnelle", "Voiture de service", "Autre"]
    funding_sources: list[str] = [
        "Sorbonne Université",
        "Polytechnique",
        "CNES",
        "ANR",
        "ESA",
        "Autre",
    ]
    allowed_origins: list[str] = []


org_config = section("org", OrgConfig, label="Organization")


# --- BookingsConfig section ---

class BookingsConfig(BaseModel):
    os_choices: list[str] = ["Windows", "Ubuntu", "Fedora"]
    software_tags: dict[str, list[str]] = {
        "Windows": ["Office 365", "MATLAB", "IDL", "Python (Anaconda)", "LabVIEW", "SolidWorks"],
        "Ubuntu": ["Python", "MATLAB", "IDL", "GCC", "LaTeX", "Docker"],
        "Fedora": ["Python", "MATLAB", "IDL", "GCC", "LaTeX", "Docker", "Toolbox"],
    }
    minimum_lead_days: int = Field(default=7, ge=0)
    resource_setup_buffer_days: int = Field(default=7, ge=0)
    reminder_lead_days: int | None = Field(default=1, ge=0)


bookings_config = section("bookings", BookingsConfig, label="Bookings")


# --- DashboardConfig section ---

class DashboardConfig(BaseModel):
    urgency_fresh_days: int = 2
    urgency_aging_days: int = 7


dashboard_config = section("dashboard", DashboardConfig, label="Dashboard")
