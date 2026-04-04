"""Dev data seeding — fake users, workflow requests, and resource bookings."""

import logging
import random as _random
from contextlib import asynccontextmanager
from datetime import date, timedelta

from not_dot_net.backend.db import session_scope, get_user_db
from not_dot_net.backend.schemas import UserCreate
from not_dot_net.backend.users import get_user_manager

logger = logging.getLogger("not_dot_net.seeding")


async def seed_fake_users() -> None:
    """Seed ~100 fake users + ~20 workflows for development."""
    from not_dot_net.backend.seed_data import get_fake_users
    from fastapi_users.exceptions import UserAlreadyExists

    created_users = []
    async with session_scope() as session:
        async with asynccontextmanager(get_user_db)(session) as user_db:
            async with asynccontextmanager(get_user_manager)(user_db) as user_manager:
                count = 0
                for fake in get_fake_users():
                    try:
                        user = await user_manager.create(
                            UserCreate(
                                email=fake["email"],
                                password="dev",
                                is_active=True,
                                is_superuser=False,
                            )
                        )
                        for field in ("full_name", "phone", "office", "team", "title", "employment_status"):
                            setattr(user, field, fake.get(field))
                        if fake.get("start_date"):
                            user.start_date = date.fromisoformat(fake["start_date"])
                        if fake.get("end_date"):
                            user.end_date = date.fromisoformat(fake["end_date"])
                        user.role = fake["role"]
                        session.add(user)
                        created_users.append(user)
                        count += 1
                    except UserAlreadyExists:
                        pass
                await session.commit()
                if count:
                    logger.info("Seeded %d fake users", count)

    if created_users:
        await _seed_fake_workflows(created_users)
    await _seed_resources_and_bookings(created_users)


async def _seed_fake_workflows(users: list) -> None:
    """Seed ~20 workflow requests in various states."""
    from not_dot_net.backend.seed_data import WORKFLOW_SEEDS
    from not_dot_net.backend.workflow_service import create_request, submit_step

    rng = _random.Random(42)

    staff = [u for u in users if u.role in ("staff", "director", "admin")]
    directors = [u for u in users if u.role == "director"]

    if not staff:
        return

    count = 0
    for seed in WORKFLOW_SEEDS:
        creator = rng.choice(staff)
        try:
            req = await create_request(
                workflow_type=seed["type"],
                created_by=creator.id,
                data=seed["data"],
            )

            if seed["step"] == "request" and seed["action"] is None:
                pass
            elif seed["action"] == "submit":
                await submit_step(req.id, creator.id, "submit", data={})
            elif seed["action"] == "approve":
                await submit_step(req.id, creator.id, "submit", data={})
                approver = rng.choice(directors) if directors else creator
                if seed["type"] == "onboarding" and seed["step"] in ("admin_validation", "done"):
                    await submit_step(req.id, None, "submit", data=seed["data"])
                await submit_step(
                    req.id, approver.id, "approve",
                    comment=seed.get("comment"),
                )
            elif seed["action"] == "reject":
                await submit_step(req.id, creator.id, "submit", data={})
                approver = rng.choice(directors) if directors else creator
                if seed["type"] == "onboarding" and seed["step"] == "rejected":
                    await submit_step(req.id, None, "submit", data=seed["data"])
                await submit_step(
                    req.id, approver.id, "reject",
                    comment=seed.get("comment"),
                )

            count += 1
        except Exception as e:
            logger.warning("Seed workflow failed: %s", e)

    if count:
        logger.info("Seeded %d workflow requests", count)


async def _seed_resources_and_bookings(users: list) -> None:
    """Seed resources and a few sample bookings."""
    from not_dot_net.backend.seed_data import SEED_RESOURCES
    from not_dot_net.backend.booking_service import (
        create_resource,
        create_booking,
        list_resources,
    )

    existing = await list_resources(active_only=False)
    if existing:
        return

    rng = _random.Random(42)
    resources = []
    for seed in SEED_RESOURCES:
        res = await create_resource(
            name=seed["name"],
            resource_type=seed["type"],
            description=seed.get("description", ""),
            location=seed.get("location", ""),
            specs=seed.get("specs"),
        )
        resources.append(res)

    if not users:
        logger.info("Seeded %d resources", len(resources))
        return

    today = date.today()
    count = 0
    for res in resources[:5]:
        booker = rng.choice(users)
        start = today + timedelta(days=rng.randint(1, 30))
        end = start + timedelta(days=rng.randint(1, 14))
        try:
            await create_booking(res.id, booker.id, start, end, note="Dev seed booking")
            count += 1
        except Exception:
            pass

    logger.info("Seeded %d resources, %d bookings", len(resources), count)
