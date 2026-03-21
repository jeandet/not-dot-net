import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    full_name: str | None = None
    phone: str | None = None
    office: str | None = None
    team: str | None = None
    title: str | None = None
    employment_status: str | None = None


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    full_name: str | None = None
    phone: str | None = None
    office: str | None = None
    team: str | None = None
    title: str | None = None
    employment_status: str | None = None