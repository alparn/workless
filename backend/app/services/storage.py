import uuid
from pathlib import Path

import aiofiles

from app.config import settings

ALLOWED_MIME_TYPES = frozenset({
    "application/pdf",
    "image/png",
    "image/jpeg",
})

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class StorageError(Exception):
    pass


def _client_dir(client_id: uuid.UUID) -> Path:
    return settings.upload_dir / str(client_id)


async def save_file(
    client_id: uuid.UUID,
    file_bytes: bytes,
    original_filename: str,
) -> str:
    """Persist uploaded bytes and return the relative storage path."""
    dest_dir = _client_dir(client_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4()}_{original_filename}"
    dest_path = dest_dir / safe_name
    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(file_bytes)

    return str(dest_path.relative_to(settings.upload_dir))


async def get_file(storage_path: str) -> bytes:
    """Read a previously stored file."""
    full_path = settings.upload_dir / storage_path
    if not full_path.exists():
        raise StorageError(f"File not found: {storage_path}")

    async with aiofiles.open(full_path, "rb") as f:
        return await f.read()


async def delete_file(storage_path: str) -> None:
    """Remove a stored file from disk."""
    full_path = settings.upload_dir / storage_path
    if full_path.exists():
        full_path.unlink()
