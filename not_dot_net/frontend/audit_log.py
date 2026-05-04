"""Audit log viewer — admin-only tab showing system events."""

from datetime import datetime, timedelta, timezone

from nicegui import ui

from not_dot_net.backend.audit import list_audit_events
from not_dot_net.frontend.i18n import t
from not_dot_net.backend.permissions import permission

VIEW_AUDIT_LOG = permission("view_audit_log", "View audit log", "Access the audit log")

CATEGORIES = ["auth", "workflow", "booking", "resource", "user", "settings", "personal_data"]
FILTER_CONTROL_HEIGHT = "40px"

SEVERITY_FILTERS = {
    "": "All",
    "green": "Normal",
    "orange": "Sensitive",
    "red": "Critical",
}

SEVERITY_STYLES = {
    "green": {
        "label": "Normal",
        "row": "#DCEFE2",
    },
    "orange": {
        "label": "Sensitive",
        "row": "#FFE6B8",
    },
    "red": {
        "label": "Critical",
        "row": "#FFB3B3",
    },
}

TIME_PERIOD_DAYS = {
    "last_7_days": 7,
    "last_30_days": 30,
    "last_90_days": 90,
    "last_year": 365,
    "all_time": None,
}


def _since_from_period(period_key: str) -> datetime | None:
    days = TIME_PERIOD_DAYS.get(period_key)
    if days is None:
        return None
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def _audit_severity(category: str, action: str, detail: str | None) -> str:
    detail = detail or ""
    if category == "auth" and action == "login" and "is_superuser=True" in detail:
        return "red"
    if category == "auth" and action == "login" and "Login Failed" in detail:
        return "red"
    if category == "settings" and action == "update_role":
        return "red"
    if category == "settings" and action in {"update", "reset"}:
        if any(section in detail for section in ("section=roles", "section=ldap")):
            return "red"
        return "orange"
    if category == "personal_data" and action == "download":
        return "orange"
    if category == "settings" and action in {"export", "import", "ldap_sync"}:
        return "orange"
    if category == "workflow" and action == "resend_notification":
        return "orange"
    if category == "user" and action in {"add_tenure", "update_tenure", "delete_tenure"}:
        return "orange"
    if category == "user" and action == "update" and "role" in detail:
        return "red"
    return "green"


def _relative_time_label(dt: datetime | None) -> str:
    if dt is None:
        return ""
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    days = (today - dt.date()).days
    hour = dt.strftime("%Hh%M")
    if days == 0:
        return hour
    if days == 1:
        return f"hier {hour}"
    if days == 2:
        return f"avant-hier {hour}"
    return f"{days}d ago"


def render():
    container = ui.column().classes("w-full")

    async def refresh():
        await _render_log(container)

    ui.timer(0, refresh, once=True)


async def _render_log(
    container,
    category=None,
    actor_email=None,
    period="last_30_days",
    relative_time=False,
    severity_filter="",
):
    container.clear()

    since = _since_from_period(period)
    events = await list_audit_events(
        category=category, actor_email=actor_email, since=since, limit=500,
    )

    period_options = {k: t(k) for k in TIME_PERIOD_DAYS}
    relative_state = {"enabled": relative_time}
    severity_counts = {key: 0 for key in SEVERITY_STYLES}
    event_severities = {}
    for ev in events:
        severity = _audit_severity(ev.category, ev.action, ev.detail)
        event_severities[str(ev.id)] = severity
        severity_counts[severity] += 1

    with container:
        ui.label(t("audit_log")).classes("text-h6 mb-2")

        # Filters
        with ui.row().classes("items-end gap-2 mb-3"):
            period_select = ui.select(
                options=period_options,
                value=period,
                label=t("time_period"),
            ).props("outlined dense").classes("min-w-[160px]")

            cat_select = ui.select(
                options=[""] + CATEGORIES,
                value=category or "",
                label=t("category"),
            ).props("outlined dense clearable").classes("min-w-[150px]")

            email_input = ui.input(
                label=t("actor"),
                value=actor_email or "",
            ).props("outlined dense clearable").classes("min-w-[200px]")

            severity_select = ui.select(
                options=SEVERITY_FILTERS,
                value=severity_filter,
                label="Type",
            ).props("outlined dense").classes("min-w-[140px]")

            async def apply():
                c = cat_select.value or None
                e = email_input.value.strip() or None
                p = period_select.value
                s = severity_select.value or ""
                await _render_log(
                    container,
                    category=c,
                    actor_email=e,
                    period=p,
                    relative_time=relative_state["enabled"],
                    severity_filter=s,
                )

            ui.button(t("filter"), icon="search", on_click=apply).props(
                "flat color=primary"
            )

            async def toggle_time_display():
                relative_state["enabled"] = not relative_state["enabled"]
                for row in rows:
                    row["time"] = (
                        row["time_relative"]
                        if relative_state["enabled"]
                        else row["time_full"]
                    )
                table.rows = rows
                table.update()
                time_button.props(
                    f"flat round dense color={'primary' if relative_state['enabled'] else 'grey'}"
                )
                time_button.tooltip(
                    "Relative time" if relative_state["enabled"] else "Full timestamp"
                )

            with ui.element("div").style(
                f"height: {FILTER_CONTROL_HEIGHT}; display: flex; align-items: center;"
            ):
                time_button = ui.button(
                    icon="schedule",
                    on_click=toggle_time_display,
                ).props(
                    f"flat round dense color={'primary' if relative_state['enabled'] else 'grey'}"
                ).tooltip("Relative time" if relative_state["enabled"] else "Full timestamp")

            with ui.element("div").style(
                f"height: {FILTER_CONTROL_HEIGHT}; display: flex; align-items: center;"
            ):
                with ui.row().classes("items-center gap-1"):
                    for severity in ("green", "orange", "red"):
                        styles = SEVERITY_STYLES[severity]
                        ui.label(
                            f"{styles['label']} {severity_counts[severity]}"
                        ).classes("px-2 py-1 text-caption rounded-borders").style(
                            "background-color: "
                            f"{styles['row']}; color: #263238; "
                            "border: 1px solid rgba(0, 0, 0, 0.14); "
                            "line-height: 1.2;"
                        )

        if not events:
            ui.label(t("no_events")).classes("text-grey")
            return

        # Table
        columns = [
            {"name": "time", "label": t("time"), "field": "time", "sortable": True, "align": "left"},
            {"name": "category", "label": t("category"), "field": "category", "sortable": True, "align": "left"},
            {"name": "action", "label": t("action"), "field": "action", "sortable": True, "align": "left"},
            {"name": "actor", "label": t("actor"), "field": "actor", "sortable": True, "align": "left"},
            {"name": "target", "label": t("target"), "field": "target", "sortable": True, "align": "left"},
            {"name": "detail", "label": t("detail"), "field": "detail", "align": "left"},
        ]

        rows = []
        for ev in events:
            detail = ev.detail or ""
            severity = event_severities[str(ev.id)]
            if severity_filter and severity != severity_filter:
                continue
            styles = SEVERITY_STYLES[severity]
            rows.append({
                "_id": str(ev.id),
                "time": _relative_time_label(ev.created_at) if relative_time else (
                    ev.created_at.strftime("%Y-%m-%d %H:%M:%S") if ev.created_at else ""
                ),
                "time_full": ev.created_at.strftime("%Y-%m-%d %H:%M:%S") if ev.created_at else "",
                "time_relative": _relative_time_label(ev.created_at),
                "category": ev.category,
                "action": ev.action,
                "actor": ev.actor_display or "—",
                "target": f"{ev.target_type}: {ev.target_display}" if ev.target_type and ev.target_display else "—",
                "detail": detail,
                "severity": severity,
                "severity_row": styles["row"],
            })

        if not rows:
            ui.label(t("no_events")).classes("text-grey")
            return

        table = ui.table(
            columns=columns, rows=rows, row_key="_id",
            pagination={"rowsPerPage": 25},
        ).classes("w-full")
        table.props("flat bordered dense")

        table.add_slot("body", r'''
            <q-tr :props="props" :style="{ backgroundColor: props.row.severity_row }">
                <q-td key="time" :props="props">{{ props.row.time }}</q-td>
                <q-td key="category" :props="props">
                    <q-badge
                        :color="
                            props.row.category === 'auth' ? 'orange' :
                            props.row.category === 'workflow' ? 'primary' :
                            props.row.category === 'booking' ? 'teal' :
                            props.row.category === 'resource' ? 'purple' :
                            'grey'
                        "
                        :label="props.row.category"
                    />
                </q-td>
                <q-td key="action" :props="props">{{ props.row.action }}</q-td>
                <q-td key="actor" :props="props">{{ props.row.actor }}</q-td>
                <q-td key="target" :props="props">{{ props.row.target }}</q-td>
                <q-td key="detail" :props="props">{{ props.row.detail }}</q-td>
            </q-tr>
        ''')
