from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.profile_photo import (
    profile_photo_data_uri,
    profile_photo_max_bytes,
    profile_photo_mime,
    remove_profile_photo,
    save_profile_photo,
    validate_profile_photo,
)


JPEG_BYTES = b"\xff\xd8\xff\xe0profile-photo"
PNG_BYTES = b"\x89PNG\r\n\x1a\nprofile-photo"


def test_profile_photo_mime_detects_supported_images():
    assert profile_photo_mime(JPEG_BYTES) == "image/jpeg"
    assert profile_photo_mime(PNG_BYTES) == "image/png"


def test_profile_photo_mime_rejects_unknown_content():
    assert profile_photo_mime(b"not an image") is None


def test_profile_photo_data_uri_uses_detected_mime_type():
    assert profile_photo_data_uri(PNG_BYTES).startswith("data:image/png;base64,")
    assert profile_photo_data_uri(JPEG_BYTES).startswith("data:image/jpeg;base64,")


def test_validate_profile_photo_accepts_jpg_and_png():
    assert validate_profile_photo(JPEG_BYTES, "avatar.jpg") is None
    assert validate_profile_photo(JPEG_BYTES, "avatar.jpeg") is None
    assert validate_profile_photo(PNG_BYTES, "avatar.png") is None


def test_validate_profile_photo_rejects_bad_extension():
    assert validate_profile_photo(PNG_BYTES, "avatar.gif") == "profile_photo_invalid_type"


def test_validate_profile_photo_rejects_content_mismatch():
    assert validate_profile_photo(b"not an image", "avatar.png") == "profile_photo_invalid_content"


def test_validate_profile_photo_rejects_large_file():
    content = JPEG_BYTES + b"x" * profile_photo_max_bytes(1)
    assert validate_profile_photo(content, "avatar.jpg", max_size_mb=1) == "profile_photo_too_large"


def test_profile_photo_max_bytes_uses_megabytes():
    assert profile_photo_max_bytes(2) == 2 * 1024 * 1024


async def test_save_and_remove_profile_photo():
    async with session_scope() as session:
        user = User(email="photo@test.dev", hashed_password="x")
        session.add(user)
        await session.commit()
        user_id = user.id

    assert await save_profile_photo(user_id, PNG_BYTES) is True

    async with session_scope() as session:
        user = await session.get(User, user_id)
        assert user.photo == PNG_BYTES

    assert await remove_profile_photo(user_id) is True

    async with session_scope() as session:
        user = await session.get(User, user_id)
        assert user.photo is None
