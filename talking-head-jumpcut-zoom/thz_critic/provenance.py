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


def critic_package_sha256(package_dir: str | Path | None = None) -> str:
    """Hash the complete Python critic package with filenames bound to contents."""
    root = Path(package_dir) if package_dir is not None else Path(__file__).resolve().parent
    files = sorted(path for path in root.glob("*.py") if path.is_file())
    if not files:
        raise ValueError("critic package contains no Python files")
    rows = [f"{path.name}={sha256_file(path)}" for path in files]
    return sha256_bytes("\n".join(rows).encode("utf-8"))


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


def build_bound_provenance(
    *,
    critic_version: str,
    script_sha256: str,
    master_sha256: str,
    manifest_sha256: str,
    analysis_sha256: str | None,
    renderer_program_sha256: str | None,
    pass1_independent: bool = True,
) -> CriticProvenance:
    """Construct provenance with inputs_sha256 derived from named bound inputs.

    Callers do not provide inputs_sha256 directly; this prevents a valid-looking but
    semantically misbound critic report from being assembled by accident.
    """
    values = {
        "analysis_sha256": analysis_sha256,
        "manifest_sha256": manifest_sha256,
        "renderer_program_sha256": renderer_program_sha256,
    }
    provenance = CriticProvenance(
        critic_version=critic_version,
        script_sha256=script_sha256,
        master_sha256=master_sha256,
        inputs_sha256=hash_named_inputs(values),
        pass1_independent=pass1_independent,
        manifest_sha256=manifest_sha256,
        analysis_sha256=analysis_sha256,
        renderer_program_sha256=renderer_program_sha256,
    )
    validate_provenance(provenance, require_bound_inputs=True)
    return provenance


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
