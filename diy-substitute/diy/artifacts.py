from __future__ import annotations

import hashlib
import io
import re
import stat
import zipfile
from dataclasses import dataclass
from typing import Any, Mapping

from .core import Decision, hold, incomplete, parse_json_bytes, validate_result


MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 128
MAX_COMPRESSION_RATIO = 200
SHA256_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ArtifactSelection:
    metadata: Mapping[str, Any] | None
    decision: Decision | None


@dataclass(frozen=True)
class LoadedArtifact:
    payload: dict[str, Any] | None
    decision: Decision | None


def archive_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def artifact_name_for_run(run_id: int) -> str:
    return f"prwitness-{run_id}"


def select_artifact(
    artifacts: object,
    *,
    expected_name: str,
    expected_run_id: int,
    expected_head_sha: str,
) -> ArtifactSelection:
    """Select exactly one API artifact; never choose the first result silently."""

    if not isinstance(artifacts, list):
        return ArtifactSelection(None, incomplete("MALFORMED_API_RESPONSE"))
    candidates = [item for item in artifacts if isinstance(item, dict) and item.get("name") == expected_name]
    if not candidates:
        return ArtifactSelection(None, incomplete("MISSING_ARTIFACT", name=expected_name))
    if len(candidates) != 1:
        return ArtifactSelection(None, hold("DUPLICATE_ARTIFACT", count=len(candidates)))

    item = candidates[0]
    artifact_id = item.get("id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool) or artifact_id <= 0:
        return ArtifactSelection(None, incomplete("MALFORMED_ARTIFACT_METADATA"))
    if item.get("expired") is not False:
        return ArtifactSelection(None, incomplete("ARTIFACT_EXPIRED"))

    workflow_run = item.get("workflow_run")
    if not isinstance(workflow_run, dict):
        return ArtifactSelection(None, incomplete("MALFORMED_ARTIFACT_METADATA"))
    if workflow_run.get("id") != expected_run_id:
        return ArtifactSelection(None, hold("RUN_ID_CONFLICT"))
    artifact_head_sha = workflow_run.get("head_sha")
    if not isinstance(artifact_head_sha, str):
        return ArtifactSelection(None, incomplete("MALFORMED_ARTIFACT_METADATA"))
    if artifact_head_sha.lower() != expected_head_sha.lower():
        return ArtifactSelection(None, hold("SHA_CONFLICT"))

    size = item.get("size_in_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        return ArtifactSelection(None, incomplete("MALFORMED_ARTIFACT_METADATA"))
    if size > MAX_ARCHIVE_BYTES:
        return ArtifactSelection(None, incomplete("OVERSIZE_ARTIFACT", bytes=size))

    digest = item.get("digest")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        return ArtifactSelection(None, incomplete("MISSING_OR_INVALID_DIGEST"))
    return ArtifactSelection(item, None)


def _normalise_member_name(name: str) -> str:
    if "\x00" in name:
        raise ValueError("NUL member")
    value = name.replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("absolute member")
    parts = value.split("/")
    if any(part == ".." for part in parts):
        raise ValueError("parent traversal")
    normal = "/".join(part for part in parts if part not in {"", "."})
    if not normal:
        raise ValueError("empty member")
    return normal


def load_result_from_zip(
    archive: bytes,
    *,
    metadata: Mapping[str, Any] | None = None,
    require_digest: bool = True,
) -> LoadedArtifact:
    """Inspect ZIP metadata and read one JSON member without extracting or executing."""

    if not isinstance(archive, bytes):
        return LoadedArtifact(None, incomplete("MALFORMED_ZIP"))
    if len(archive) > MAX_ARCHIVE_BYTES:
        return LoadedArtifact(None, incomplete("OVERSIZE_ARCHIVE", bytes=len(archive)))

    if metadata is not None:
        expected_size = metadata.get("size_in_bytes")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool):
            return LoadedArtifact(None, incomplete("MALFORMED_ARTIFACT_METADATA"))
        if expected_size != len(archive):
            return LoadedArtifact(None, incomplete("SIZE_CONFLICT", expected=expected_size, observed=len(archive)))
        digest = metadata.get("digest")
        if require_digest and (not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None):
            return LoadedArtifact(None, incomplete("MISSING_OR_INVALID_DIGEST"))
        if isinstance(digest, str) and digest.lower() != archive_digest(archive).lower():
            return LoadedArtifact(None, incomplete("DIGEST_CONFLICT"))

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(archive))
    except (zipfile.BadZipFile, OSError):
        return LoadedArtifact(None, incomplete("MALFORMED_ZIP"))

    try:
        try:
            infos = zip_file.infolist()
        except (OSError, RuntimeError, zipfile.BadZipFile):
            return LoadedArtifact(None, incomplete("MALFORMED_ZIP"))
        if len(infos) > MAX_ENTRIES:
            return LoadedArtifact(None, incomplete("OVERSIZE_ENTRY_COUNT", count=len(infos)))
        names: set[str] = set()
        result_infos: list[zipfile.ZipInfo] = []
        total_uncompressed = 0
        for info in infos:
            try:
                normal = _normalise_member_name(info.filename)
            except ValueError as exc:
                return LoadedArtifact(None, incomplete("UNSAFE_ZIP_MEMBER", detail=str(exc)))
            if normal in names:
                return LoadedArtifact(None, incomplete("DUPLICATE_ZIP_MEMBER", name=normal))
            names.add(normal)

            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                return LoadedArtifact(None, incomplete("SYMLINK_ZIP_MEMBER", name=normal))
            if info.is_dir():
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                return LoadedArtifact(None, incomplete("OVERSIZE_ZIP_MEMBER", name=normal))
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                return LoadedArtifact(None, incomplete("OVERSIZE_UNCOMPRESSED", bytes=total_uncompressed))
            if info.file_size > 0 and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                return LoadedArtifact(None, incomplete("ZIP_COMPRESSION_RATIO", name=normal))
            if normal == "free-result.json":
                result_infos.append(info)

        if len(result_infos) == 0:
            return LoadedArtifact(None, incomplete("MISSING_RESULT"))
        if len(result_infos) != 1:
            return LoadedArtifact(None, incomplete("DUPLICATE_RESULT", count=len(result_infos)))
        try:
            result_bytes = zip_file.read(result_infos[0])
        except (OSError, RuntimeError, zipfile.BadZipFile):
            return LoadedArtifact(None, incomplete("UNREADABLE_RESULT"))
        payload, decision = parse_json_bytes(result_bytes)
        return LoadedArtifact(payload, decision)
    finally:
        zip_file.close()


def evaluate_artifact(
    archive: bytes,
    metadata: Mapping[str, Any],
    *,
    expected_head_sha: str | None = None,
    expected_base_sha: str | None = None,
    expected_run_id: int | None = None,
) -> Decision:
    """Run the ARTIFACT layer offline against a GitHub-shaped metadata object."""

    workflow_run = metadata.get("workflow_run") if isinstance(metadata, dict) else None
    run_id = expected_run_id if expected_run_id is not None else workflow_run.get("id") if isinstance(workflow_run, dict) else None
    head_sha = expected_head_sha if expected_head_sha is not None else workflow_run.get("head_sha") if isinstance(workflow_run, dict) else None
    name = metadata.get("name") if isinstance(metadata, dict) else None
    if not isinstance(name, str) or not isinstance(run_id, int) or not isinstance(head_sha, str):
        return incomplete("MALFORMED_ARTIFACT_METADATA")
    selection = select_artifact(
        [metadata],
        expected_name=name,
        expected_run_id=run_id,
        expected_head_sha=head_sha,
    )
    if selection.decision is not None:
        return selection.decision
    loaded = load_result_from_zip(archive, metadata=metadata, require_digest=True)
    if loaded.decision is not None:
        return loaded.decision
    return validate_result(
        loaded.payload,
        expected_head_sha=head_sha,
        expected_base_sha=expected_base_sha,
        expected_run_id=run_id,
        expected_artifact_name=name,
    )
