import pytest
import uuid
from contextlib import asynccontextmanager
from datetime import date

from not_dot_net.backend.db import User, get_async_session
from not_dot_net.backend.audit import list_audit_events, log_audit


async def _create_user(email="test@lpp.fr", **kwargs) -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(
            id=uuid.uuid4(), email=email, hashed_password="x",
            role="staff", phone="0100000000", office="A101", **kwargs,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_user_update_logs_audit_diff():
    user = await _create_user()
    old_values = {"phone": "0100000000", "office": "A101"}
    new_values = {"phone": "0199999999", "office": "B202"}

    diff = {k: v for k, v in new_values.items() if v != old_values.get(k)}
    changes = {k: {"old": old_values.get(k), "new": v} for k, v in diff.items()}

    await log_audit(
        "user", "update",
        actor_id=user.id, actor_email=user.email,
        target_type="user", target_id=user.id,
        detail=f"fields={','.join(diff.keys())}",
        metadata={"changes": changes},
    )

    events = await list_audit_events(category="user", action="update")
    assert len(events) == 1
    assert events[0].metadata_json["changes"]["phone"]["old"] == "0100000000"
    assert events[0].metadata_json["changes"]["phone"]["new"] == "0199999999"
    assert events[0].metadata_json["changes"]["office"]["new"] == "B202"
