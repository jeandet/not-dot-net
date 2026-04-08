"""Custom markdown page model."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from not_dot_net.backend.db import Base


class Page(MappedAsDataclass, Base, kw_only=True):
    __tablename__ = "page"

    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    content: Mapped[str] = mapped_column(Text, default="")
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    sort_order: Mapped[int] = mapped_column(default=0)
    published: Mapped[bool] = mapped_column(default=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, default=None,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), default=None,
    )
