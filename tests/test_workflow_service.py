import pytest
import uuid
from not_dot_net.backend.workflow_service import (
    create_request,
    submit_step,
    save_draft,
    list_user_requests,
    list_actionable,
    get_request_by_id,
)
from not_dot_net.backend.roles import Role
from not_dot_net.backend.db import Base, User, get_async_session
from not_dot_net.config import init_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from contextlib import asynccontextmanager
import not_dot_net.backend.db as db_module
import not_dot_net.backend.workflow_models  # noqa: F401


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up an in-memory SQLite DB for each test."""
    init_settings()  # defaults
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session


async def _create_user(email="staff@test.com", role=Role.STAFF) -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password="x",
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_create_request():
    user = await _create_user()
    req = await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    assert req.type == "vpn_access"
    assert req.current_step == "request"
    assert req.status == "in_progress"
    assert req.target_email == "alice@test.com"
    assert req.data["target_name"] == "Alice"


async def test_submit_step_advances():
    user = await _create_user()
    req = await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    updated = await submit_step(req.id, user.id, "submit", data={})
    assert updated.current_step == "approval"
    assert updated.status == "in_progress"


async def test_approve_completes_workflow():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    req = await submit_step(req.id, staff.id, "submit", data={})
    req = await submit_step(req.id, director.id, "approve", data={})
    assert req.status == "completed"


async def test_reject_terminates_workflow():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    req = await submit_step(req.id, staff.id, "submit", data={})
    req = await submit_step(req.id, director.id, "reject", data={}, comment="Not justified")
    assert req.status == "rejected"


async def test_save_draft():
    user = await _create_user()
    req = await create_request(
        workflow_type="onboarding",
        created_by=user.id,
        data={"person_name": "Bob", "person_email": "bob@test.com",
              "role_status": "intern", "team": "Plasma Physics",
              "start_date": "2026-04-01"},
    )
    # Advance to newcomer_info step
    req = await submit_step(req.id, user.id, "submit", data={})
    assert req.current_step == "newcomer_info"
    # Save partial data
    req = await save_draft(req.id, data={"phone": "+33 1 23 45"})
    assert req.data["phone"] == "+33 1 23 45"
    assert req.current_step == "newcomer_info"  # still same step


async def test_list_user_requests():
    user = await _create_user()
    await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "A", "target_email": "a@test.com"},
    )
    await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "B", "target_email": "b@test.com"},
    )
    requests = await list_user_requests(user.id)
    assert len(requests) == 2


async def test_list_actionable_by_role():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "A", "target_email": "a@test.com"},
    )
    # Submit first step to move to approval
    await submit_step(req.id, staff.id, "submit", data={})
    # Director should see it as actionable
    actionable = await list_actionable(director)
    assert len(actionable) == 1
    assert actionable[0].current_step == "approval"


async def test_get_request_by_id():
    user = await _create_user()
    req = await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    fetched = await get_request_by_id(req.id)
    assert fetched is not None
    assert fetched.id == req.id


async def test_get_request_by_id_not_found():
    fetched = await get_request_by_id(uuid.uuid4())
    assert fetched is None


async def test_token_generated_for_target_person_step():
    """After submitting the onboarding request step, a token should be generated for the newcomer_info step."""
    user = await _create_user()
    req = await create_request(
        workflow_type="onboarding",
        created_by=user.id,
        data={"person_name": "Bob", "person_email": "bob@test.com",
              "role_status": "intern", "team": "Plasma Physics",
              "start_date": "2026-04-01"},
    )
    req = await submit_step(req.id, user.id, "submit", data={})
    assert req.current_step == "newcomer_info"
    assert req.token is not None
    assert req.token_expires_at is not None


async def test_token_cleared_on_approval():
    """Token should be cleared after a non-draft action."""
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    req = await submit_step(req.id, staff.id, "submit", data={})
    req = await submit_step(req.id, director.id, "approve", data={})
    assert req.token is None
    assert req.token_expires_at is None


async def test_authorization_check_blocks_wrong_user():
    """submit_step with actor_user should raise PermissionError if user cannot act."""
    member = await _create_user(email="member@test.com", role=Role.MEMBER)
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    # member cannot submit on the staff-assigned request step
    with pytest.raises(PermissionError):
        await submit_step(req.id, member.id, "submit", data={}, actor_user=member)


async def test_list_actionable_returns_only_in_progress():
    """Completed requests should not appear in actionable list."""
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "A", "target_email": "a@test.com"},
    )
    req = await submit_step(req.id, staff.id, "submit", data={})
    req = await submit_step(req.id, director.id, "approve", data={})
    assert req.status == "completed"

    actionable = await list_actionable(director)
    assert len(actionable) == 0
