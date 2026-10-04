"""Private document storage with local-development and Supabase backends."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

from .settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DOCUMENTS = ROOT / "data" / "documents"


def _storage_headers(content_type: str | None = None) -> dict[str, str]:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": "Bearer " + settings.supabase_service_role_key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def save_document(object_key: str, data: bytes, content_type: str) -> tuple[str, str]:
    """Store document bytes and return (backend, storage path)."""
    settings = get_settings()
    if settings.storage_backend == "local":
        target = (LOCAL_DOCUMENTS / Path(*PurePosixPath(object_key).parts)).resolve()
        target.relative_to(LOCAL_DOCUMENTS.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return "local", object_key

    key = quote(object_key, safe="/")
    url = f"{settings.supabase_url}/storage/v1/object/{quote(settings.storage_bucket, safe='')}/{key}"
    try:
        response = httpx.post(url, headers={**_storage_headers(content_type), "x-upsert": "false"}, content=data, timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError("The document could not be saved to Supabase Storage.") from error
    return "supabase", object_key


def delete_document(backend: str, object_key: str) -> None:
    settings = get_settings()
    if backend == "local":
        target = (LOCAL_DOCUMENTS / Path(*PurePosixPath(object_key).parts)).resolve()
        try:
            target.relative_to(LOCAL_DOCUMENTS.resolve())
        except ValueError:
            return
        target.unlink(missing_ok=True)
        return
    if backend != "supabase" or not settings.supabase_url:
        return
    url = f"{settings.supabase_url}/storage/v1/object/{quote(settings.storage_bucket, safe='')}"
    try:
        response = httpx.delete(url, headers=_storage_headers("application/json"), json={"prefixes": [object_key]}, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError:
        # Keep the original API failure as the useful error if cleanup itself fails.
        return


def signed_download_url(backend: str, object_key: str, expires_seconds: int = 300) -> str:
    settings = get_settings()
    if backend == "local":
        target = (LOCAL_DOCUMENTS / Path(*PurePosixPath(object_key).parts)).resolve()
        target.relative_to(LOCAL_DOCUMENTS.resolve())
        if not target.is_file():
            raise FileNotFoundError("The stored document was not found.")
        return "local:" + object_key
    if backend != "supabase":
        raise RuntimeError("This document has an unknown storage backend.")
    key = quote(object_key, safe="/")
    url = f"{settings.supabase_url}/storage/v1/object/sign/{quote(settings.storage_bucket, safe='')}/{key}"
    try:
        response = httpx.post(url, headers=_storage_headers("application/json"), json={"expiresIn": expires_seconds}, timeout=15)
        response.raise_for_status()
        signed = response.json().get("signedURL")
        if not signed:
            raise RuntimeError("Supabase did not return a signed document URL.")
        if signed.startswith("http://") or signed.startswith("https://"):
            return signed
        if signed.startswith("/storage/v1/"):
            return settings.supabase_url + signed
        return settings.supabase_url + "/storage/v1" + (signed if signed.startswith("/") else "/" + signed)
    except httpx.HTTPError as error:
        raise RuntimeError("A secure download link could not be created.") from error


def local_file_path(object_key: str) -> Path:
    target = (LOCAL_DOCUMENTS / Path(*PurePosixPath(object_key).parts)).resolve()
    target.relative_to(LOCAL_DOCUMENTS.resolve())
    return target
