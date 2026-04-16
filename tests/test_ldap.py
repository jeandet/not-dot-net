import pytest
from ldap3 import Server, Connection, MOCK_SYNC, OFFLINE_AD_2012_R2

from not_dot_net.backend.auth.ldap import ldap_authenticate, LdapConfig, LdapUserInfo

LDAP_CFG = LdapConfig(url="fake", domain="example.com", base_dn="dc=example,dc=com")

FAKE_USERS = {
    "jdoe": {"mail": "jdoe@example.com", "displayName": "John Doe", "givenName": "John", "sn": "Doe", "password": "secret"},
    "nomail": {"mail": None, "displayName": "No Mail", "givenName": "No", "sn": "Mail", "password": "secret"},
}


def fake_ldap_connect(ldap_cfg: LdapConfig, username: str, password: str) -> Connection:
    """Build a MOCK_SYNC connection pre-populated with fake AD entries."""
    server = Server("fake_ad", get_info=OFFLINE_AD_2012_R2)
    conn = Connection(server, user=f"{username}@{ldap_cfg.domain}", password=password, client_strategy=MOCK_SYNC)

    for uid, attrs in FAKE_USERS.items():
        entry_attrs = {
            "sAMAccountName": uid,
            "userPassword": attrs["password"],
            "objectClass": "person",
        }
        for attr in ("mail", "displayName", "givenName", "sn"):
            if attrs.get(attr):
                entry_attrs[attr] = attrs[attr]
        conn.strategy.add_entry(f"cn={uid},ou=users,{ldap_cfg.base_dn}", entry_attrs)

    conn.bind()

    if FAKE_USERS.get(username, {}).get("password") != password:
        from ldap3.core.exceptions import LDAPBindError
        raise LDAPBindError("Invalid credentials")

    return conn


def test_successful_authentication():
    result = ldap_authenticate("jdoe", "secret", LDAP_CFG, connect=fake_ldap_connect)
    assert result is not None
    assert result.email == "jdoe@example.com"
    assert result.full_name == "John Doe"
    assert result.given_name == "John"
    assert result.surname == "Doe"


def test_wrong_password_returns_none():
    result = ldap_authenticate("jdoe", "wrong", LDAP_CFG, connect=fake_ldap_connect)
    assert result is None


def test_unknown_user_returns_none():
    result = ldap_authenticate("nobody", "secret", LDAP_CFG, connect=fake_ldap_connect)
    assert result is None


def test_user_without_mail_returns_none():
    result = ldap_authenticate("nomail", "secret", LDAP_CFG, connect=fake_ldap_connect)
    assert result is None
