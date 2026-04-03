import uuid

from not_dot_net.backend.db import User, session_scope


async def test_user_role_is_string():
    async with session_scope() as session:
        user = User(
            id=uuid.uuid4(),
            email="test@test.com",
            hashed_password="x",
            role="staff",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.role == "staff"
        assert isinstance(user.role, str)


async def test_user_default_role_is_empty():
    async with session_scope() as session:
        user = User(
            id=uuid.uuid4(),
            email="default@test.com",
            hashed_password="x",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.role == ""
