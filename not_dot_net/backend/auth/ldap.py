from fastapi import APIRouter, Depends, HTTPException, status
from ldap3 import Server, Connection, ALL
from ldap3.core.exceptions import LDAPBindError
from pydantic import BaseModel

from not_dot_net.backend.db import get_user_db
from not_dot_net.backend.users import get_jwt_strategy
from not_dot_net.config import get_settings

router = APIRouter(tags=["auth"])


class LDAPAuthRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


@router.post("/auth/ldap", response_model=TokenResponse)
async def ldap_login(
    credentials: LDAPAuthRequest,
    user_db=Depends(get_user_db),
):
    ldap_cfg = get_settings().backend.users.auth.ldap
    server = Server(ldap_cfg.url, get_info=ALL)

    try:
        user_dn = f"uid={credentials.username},{ldap_cfg.base_dn}"
        conn = Connection(server, user=user_dn, password=credentials.password, auto_bind=True)
    except LDAPBindError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LDAP credentials")

    try:
        conn.search(ldap_cfg.base_dn, f"(uid={credentials.username})", attributes=["mail"])
        if not conn.entries:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LDAP user not found")
        email = getattr(conn.entries[0], "mail", None)
        email_value = email.value if email is not None else None
    finally:
        conn.unbind()

    if not email_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LDAP did not return email")

    user = await user_db.get_by_email(email_value)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No local user mapped to this LDAP account",
        )

    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    return TokenResponse(access_token=token)
