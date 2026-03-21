from fastapi import APIRouter

from .local import router as local_router
from .ldap import router as ldap_router

router = APIRouter()
router.include_router(local_router)
router.include_router(ldap_router)
