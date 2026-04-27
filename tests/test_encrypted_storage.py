import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from not_dot_net.backend.secrets import AppSecrets, generate_secrets_file, read_secrets_file


def test_app_secrets_has_file_encryption_key():
    s = AppSecrets(jwt_secret="j", storage_secret="s", file_encryption_key="k")
    assert s.file_encryption_key == "k"


def test_generate_secrets_file_includes_encryption_key():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "secrets.key"
        secrets = generate_secrets_file(path)
        assert secrets.file_encryption_key
        assert len(secrets.file_encryption_key) > 20
        reloaded = read_secrets_file(path)
        assert reloaded.file_encryption_key == secrets.file_encryption_key


from not_dot_net.backend.encrypted_storage import (
    store_encrypted, read_encrypted, mark_for_retention, delete_expired,
    EncryptedFile, ACCESS_PERSONAL_DATA,
)
from not_dot_net.backend.db import session_scope


@pytest.mark.asyncio
async def test_store_and_read_encrypted_roundtrip():
    content = b"This is a secret document"
    filename = "id_card.pdf"
    uploader_id = uuid.uuid4()

    enc_file = await store_encrypted(content, filename, "application/pdf", uploader_id)
    assert enc_file.id is not None
    assert enc_file.original_filename == filename
    assert enc_file.wrapped_dek is not None
    assert enc_file.nonce is not None

    decrypted, name, ctype = await read_encrypted(enc_file.id, actor_id=uploader_id)
    assert decrypted == content
    assert name == filename
    assert ctype == "application/pdf"


@pytest.mark.asyncio
async def test_encrypted_blob_is_not_plaintext():
    content = b"Super secret bank details RIB"
    enc_file = await store_encrypted(content, "rib.pdf", "application/pdf", None)
    blob = Path(enc_file.storage_path).read_bytes()
    assert blob != content


@pytest.mark.asyncio
async def test_read_encrypted_nonexistent_raises():
    with pytest.raises(ValueError, match="not found"):
        await read_encrypted(uuid.uuid4(), actor_id=uuid.uuid4())


def test_access_personal_data_permission_registered():
    from not_dot_net.backend.permissions import get_permissions
    perms = get_permissions()
    assert ACCESS_PERSONAL_DATA in perms


@pytest.mark.asyncio
async def test_mark_for_retention():
    enc_file = await store_encrypted(b"data", "f.pdf", "application/pdf", None)
    await mark_for_retention(enc_file.id, days=30)
    async with session_scope() as session:
        reloaded = await session.get(EncryptedFile, enc_file.id)
        assert reloaded.retained_until is not None


@pytest.mark.asyncio
async def test_delete_expired_removes_past_retention():
    enc_file = await store_encrypted(b"old data", "old.pdf", "application/pdf", None)
    async with session_scope() as session:
        reloaded = await session.get(EncryptedFile, enc_file.id)
        reloaded.retained_until = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()
    count = await delete_expired()
    assert count == 1
    async with session_scope() as session:
        assert await session.get(EncryptedFile, enc_file.id) is None


@pytest.mark.asyncio
async def test_delete_expired_keeps_future_retention():
    enc_file = await store_encrypted(b"fresh data", "fresh.pdf", "application/pdf", None)
    await mark_for_retention(enc_file.id, days=30)
    count = await delete_expired()
    assert count == 0
