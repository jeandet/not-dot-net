from fastapi import APIRouter

from .local import router as local_router

router = APIRouter()
router.include_router(local_router)
