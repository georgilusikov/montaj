from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class CriticProvenance:
    critic_version: str
    script_sha256: str
    master_sha256: str
    inputs_sha256: str
    pass1_independent: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combine_hashes(*hashes: str) -> str:
    payload = "\n".join(sorted(hashes)).encode("ascii")
    return sha256_bytes(payload)


def validate_provenance(provenance: CriticProvenance) -> None:
    for name in ("script_sha256", "master_sha256", "inputs_sha256"):
        value = getattr(provenance, name)
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value.lower()):
            raise ValueError(f"invalid {name}")
    if not provenance.pass1_independent:
        raise ValueError("critic Pass 1 must be independent of timeline truth")
