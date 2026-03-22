from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
    PydanticBaseSettingsSource,
)


class LDAPSettings(BaseModel):
    url: str = "ldap://localhost"
    domain: str = "example.com"
    base_dn: str = "dc=example,dc=com"
    port: int = 389


class AuthSettings(BaseModel):
    ldap: LDAPSettings = LDAPSettings()


class UsersSettings(BaseModel):
    auth: AuthSettings = AuthSettings()


class BackendSettings(BaseModel):
    users: UsersSettings = UsersSettings()
    database_url: str = "sqlite+aiosqlite:///./test.db"


class FieldConfig(BaseModel):
    name: str
    type: str  # text, email, textarea, date, select, file
    required: bool = False
    label: str = ""
    options_key: str | None = None  # for select: key in Settings (e.g. "teams")


class NotificationRuleConfig(BaseModel):
    event: str  # submit, approve, reject
    step: str | None = None  # None = match any step
    notify: list[str]  # role names or contextual: requester, target_person


class WorkflowStepConfig(BaseModel):
    key: str
    type: str  # form, approval
    assignee_role: str | None = None
    assignee: str | None = None  # contextual: target_person, requester
    fields: list[FieldConfig] = []
    actions: list[str] = []
    partial_save: bool = False


class WorkflowConfig(BaseModel):
    label: str
    start_role: str = "staff"
    target_email_field: str | None = None
    steps: list[WorkflowStepConfig]
    notifications: list[NotificationRuleConfig] = []


class MailSettings(BaseModel):
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_tls: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = "noreply@not-dot-net.dev"
    dev_mode: bool = True
    dev_catch_all: str = ""


class Settings(BaseSettings):
    app_name: str = "LPP Intranet"
    admin_email: str = "admin@not-dot-net.dev"
    admin_password: str = "admin"
    jwt_secret: str = "dev-only-change-this-in-production"
    storage_secret: str = "dev-only-change-this-in-production"
    backend: BackendSettings = BackendSettings()
    teams: list[str] = [
        "Plasma Physics",
        "Instrumentation",
        "Space Weather",
        "Theory & Simulation",
        "Administration",
    ]
    # "mail_config" alias avoids collision with MAIL env var (/var/spool/mail/...)
    # YAML key is "mail_config:", not "mail:"
    mail: MailSettings = Field(default_factory=MailSettings, alias="mail_config")
    workflows: dict[str, WorkflowConfig] = {
        "vpn_access": WorkflowConfig(
            label="VPN Access Request",
            start_role="staff",
            target_email_field="target_email",
            steps=[
                WorkflowStepConfig(
                    key="request",
                    type="form",
                    assignee_role="staff",
                    fields=[
                        FieldConfig(name="target_name", type="text", required=True, label="Person Name"),
                        FieldConfig(name="target_email", type="email", required=True, label="Person Email"),
                        FieldConfig(name="justification", type="textarea", required=False, label="Justification"),
                    ],
                    actions=["submit"],
                ),
                WorkflowStepConfig(
                    key="approval",
                    type="approval",
                    assignee_role="director",
                    actions=["approve", "reject"],
                ),
            ],
            notifications=[
                NotificationRuleConfig(event="submit", step="request", notify=["director"]),
                NotificationRuleConfig(event="approve", notify=["requester", "target_person"]),
                NotificationRuleConfig(event="reject", notify=["requester"]),
            ],
        ),
        "onboarding": WorkflowConfig(
            label="Onboarding",
            start_role="staff",
            target_email_field="person_email",
            steps=[
                WorkflowStepConfig(
                    key="request",
                    type="form",
                    assignee_role="staff",
                    fields=[
                        FieldConfig(name="person_name", type="text", required=True),
                        FieldConfig(name="person_email", type="email", required=True),
                        FieldConfig(name="role_status", type="select", options_key="roles", required=True),
                        FieldConfig(name="team", type="select", options_key="teams", required=True),
                        FieldConfig(name="start_date", type="date", required=True),
                        FieldConfig(name="end_date", type="date", required=False, label="End Date"),
                        FieldConfig(name="note", type="textarea", required=False),
                    ],
                    actions=["submit"],
                ),
                WorkflowStepConfig(
                    key="newcomer_info",
                    type="form",
                    assignee="target_person",
                    partial_save=True,
                    fields=[
                        FieldConfig(name="id_document", type="file", required=True, label="ID Copy"),
                        FieldConfig(name="rib", type="file", required=True, label="Bank Details (RIB)"),
                        FieldConfig(name="photo", type="file", required=False, label="Badge Photo"),
                        FieldConfig(name="phone", type="text", required=True),
                        FieldConfig(name="emergency_contact", type="text", required=True),
                    ],
                    actions=["submit"],
                ),
                WorkflowStepConfig(
                    key="admin_validation",
                    type="approval",
                    assignee_role="admin",
                    actions=["approve", "reject"],
                ),
            ],
            notifications=[
                NotificationRuleConfig(event="submit", step="request", notify=["target_person"]),
                NotificationRuleConfig(event="submit", step="newcomer_info", notify=["admin"]),
                NotificationRuleConfig(event="approve", notify=["requester", "target_person"]),
                NotificationRuleConfig(event="reject", notify=["requester"]),
            ],
        ),
    }

    model_config = SettingsConfigDict(yaml_file="config.yaml")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )


_settings: Settings | None = None


def init_settings(config_file: str | None = None) -> Settings:
    global _settings
    kwargs = {}
    if config_file is not None:
        kwargs["_yaml_file"] = config_file
    _settings = Settings(**kwargs)
    return _settings


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings not initialized — call init_settings() first")
    return _settings
