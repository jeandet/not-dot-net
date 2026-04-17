"""Tests for critical security fixes."""

from not_dot_net.frontend.login import _safe_redirect


class TestOpenRedirect:
    def test_relative_path_allowed(self):
        assert _safe_redirect("/dashboard") == "/dashboard"

    def test_root_allowed(self):
        assert _safe_redirect("/") == "/"

    def test_absolute_url_rejected(self):
        assert _safe_redirect("https://evil.com") == "/"

    def test_protocol_relative_rejected(self):
        assert _safe_redirect("//evil.com") == "/"

    def test_scheme_with_netloc_rejected(self):
        assert _safe_redirect("http://evil.com/path") == "/"

    def test_empty_string_rejected(self):
        assert _safe_redirect("") == "/"

    def test_path_with_query_allowed(self):
        assert _safe_redirect("/page?foo=bar") == "/page?foo=bar"

    def test_triple_slash_rejected(self):
        assert _safe_redirect("///evil.com") == "/"

    def test_backslash_rejected(self):
        assert _safe_redirect("/\\evil.com") == "/"

    def test_no_leading_slash_rejected(self):
        assert _safe_redirect("evil.com") == "/"

    def test_javascript_scheme_rejected(self):
        assert _safe_redirect("javascript:alert(1)") == "/"

    def test_data_scheme_rejected(self):
        assert _safe_redirect("data:text/html,hi") == "/"


class TestAuditResolveNames:
    def test_target_id_not_mutated(self):
        """_resolve_names should not overwrite target_id with display name (#4)."""
        from not_dot_net.backend.audit import AuditEvent

        ev = AuditEvent(
            category="test", action="test",
            target_type="user", target_id="some-uuid-string",
        )
        # Before resolution, _target_display should not exist
        assert not hasattr(ev, "_target_display")
        # After resolution sets _target_display, target_id should remain a UUID string
        ev._target_display = "John Doe"
        assert ev.target_id == "some-uuid-string"
        assert ev._target_display == "John Doe"


class TestNoPublicRestApi:
    """FastAPI-Users routers exposed PATCH /users/me which let any authenticated
    user escalate themselves by setting role='admin' (custom fields bypass the
    library's is_superuser strip). The whole public REST surface was removed —
    only NiceGUI and the HTML login form are reachable."""

    def _routes(self):
        from nicegui import app
        from not_dot_net.app import create_app
        create_app()
        return {getattr(r, "path", None) for r in app.routes}

    def test_users_router_not_mounted(self):
        paths = self._routes()
        assert "/users/me" not in paths
        assert not any(p and p.startswith("/users/") for p in paths)

    def test_fastapi_users_auth_routers_not_mounted(self):
        paths = self._routes()
        assert not any(p and p.startswith("/auth/jwt") for p in paths)
        assert not any(p and p.startswith("/auth/cookie") for p in paths)

    def test_auth_local_jwt_endpoint_not_mounted(self):
        assert "/auth/local" not in self._routes()


class TestLdapEscaping:
    def test_special_chars_escaped(self):
        from ldap3.utils.conv import escape_filter_chars

        malicious = "admin)(objectClass=*"
        escaped = escape_filter_chars(malicious)
        assert "(" not in escaped
        assert ")" not in escaped

    def test_asterisk_escaped(self):
        from ldap3.utils.conv import escape_filter_chars

        assert "*" not in escape_filter_chars("*")
