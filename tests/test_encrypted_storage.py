import pytest
from pathlib import Path
import tempfile

from not_dot_net.backend.secrets import AppSecrets, generate_secrets_file, read_secrets_file


def test_app_secrets_has_file_encryption_key():
    s = AppSecrets(jwt_secret="j", storage_secret="s", file_encryption_key="k")
    assert s.file_encryption_key == "k"


def test_generate_secrets_file_includes_encryption_key():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "secrets.key"
        secrets = generate_secrets_file(path)
        assert secrets.file_encryption_key
        assert len(secrets.file_encryption_key) > 20
        reloaded = read_secrets_file(path)
        assert reloaded.file_encryption_key == secrets.file_encryption_key
