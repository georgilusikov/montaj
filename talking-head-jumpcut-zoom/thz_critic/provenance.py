from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CriticProvenance:
    critic_version: str
    script_sha256: str
    master_sha256: str
    inputs_sha256: str
    pass1_independent: bool
    manifest_sha256: str | None = None
    analysis_sha256: str | None = None
    renderer_program_sha256: str | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value.lower()):
        raise ValueError(f"invalid {name}")


def combine_hashes(*hashes: str) -> str:
    """Legacy order-independent hash combiner retained for compatibility."""
    for index, value in enumerate(hashes):
        _validate_sha256(f"hash[{index}]", value)
    payload = "\n".join(sorted(hashes)).encode("ascii")
    return sha256_bytes(payload)


def hash_named_inputs(values: Mapping[str, str | None]) -> str:
    """Bind input hashes to semantic names so values cannot be silently swapped."""
    rows: list[str] = []
    for name, value in sorted(values.items()):
        if value is None:
            continue
        if not name or "=" in name or "\n" in name:
            raise ValueError("invalid provenance input name")
        _validate_sha256(name, value)
        rows.append(f"{name}={value.lower()}")
    if not rows:
        raise ValueError("at least one provenance input hash is required")
    return sha256_bytes("\n".join(rows).encode("ascii"))


def expected_inputs_sha256(provenance: CriticProvenance) -> str:
    if provenance.manifest_sha256 is None:
        raise ValueError("critic provenance requires manifest_sha256")
    return hash_named_inputs(
        {
            "analysis_sha256": provenance.analysis_sha256,
            "manifest_sha256": provenance.manifest_sha256,
            "renderer_program_sha256": provenance.renderer_program_sha256,
        }
    )


def validate_provenance(
    provenance: CriticProvenance,
    *,
    require_bound_inputs: bool = False,
) -> None:
    if not provenance.critic_version:
        raise ValueError("critic_version required")
    for name in ("script_sha256", "master_sha256", "inputs_sha256"):
        _validate_sha256(name, getattr(provenance, name))
    for name in ("manifest_sha256", "analysis_sha256", "renderer_program_sha256"):
        value = getattr(provenance, name)
        if value is not None:
            _validate_sha256(name, value)
    if not provenance.pass1_independent:
        raise ValueError("critic Pass 1 must be independent of timeline truth")
    if require_bound_inputs:
        expected = expected_inputs_sha256(provenance)
        if provenance.inputs_sha256.lower() != expected:
            raise ValueError("inputs_sha256 does not match bound critic inputs")
