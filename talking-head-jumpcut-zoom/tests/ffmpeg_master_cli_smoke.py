from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from thz_planner.schema import (
    CanonicalCrop,
    FramingDecision,
    MotionIntent,
    RenderPrimitive,
    ShotState,
    canonical_json,
)
from thz_planner.timeline import ContentEdit, build_timeline_manifest
from thz_render.master_cli import main as master_cli_main


def _run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _hold(segment_id: str, start_ms: int, end_ms: int) -> FramingDecision:
    crop = CanonicalCrop(0, 0, 320, 568)
    return FramingDecision(
        segment_id=segment_id,
        start_ms=start_ms,
        end_ms=end_ms,
        state=ShotState.CONTEXT,
        motion_intent=MotionIntent.STATIC,
        primitive=RenderPrimitive.HOLD,
        crop_start=crop,
        crop_end=crop,
        anchor_policy="master_cli_smoke",
        time_basis="output",
        derived={"motion_duration_ms": 0},
    )


def _rgb(path: Path, at_seconds: float) -> tuple[int, int, int]:
    completed = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=1:1:flags=area,format=rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture=True,
    )
    return tuple(completed.stdout[:3])  # type: ignore[return-value]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="thz_master_cli_") as tmp:
        root = Path(tmp)
        source = root / "source.mp4"
        planner_json = root / "planner.json"
        master = root / "master.mp4"
        program = root / "renderer_program.json"

        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=320x568:d=1:r=10",
                "-f",
                "lavfi",
                "-i",
                "color=c=green:s=320x568:d=1:r=10",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x568:d=1:r=10",
                "-filter_complex",
                "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "18",
                str(source),
            ]
        )

        manifest = build_timeline_manifest(
            analysis_hash="a" * 64,
            config_hash="b" * 64,
            content_edits=[
                ContentEdit("keep_red", 0, 1000, 0, 1000),
                ContentEdit("keep_blue", 2000, 3000, 1000, 2000),
            ],
            framing_decisions=[
                _hold("red", 0, 1000),
                _hold("blue", 1000, 2000),
            ],
            source_type="live",
        )
        planner_json.write_text(canonical_json({"manifest": manifest}) + "\n", encoding="utf-8")

        if master_cli_main(
            [
                str(planner_json),
                str(source),
                str(master),
                "--program-output",
                str(program),
            ]
        ) != 0:
            raise AssertionError("master CLI returned non-zero")
        if not master.is_file() or master.stat().st_size <= 0:
            raise AssertionError("master CLI did not render output")
        if not program.is_file():
            raise AssertionError("master CLI did not emit renderer program")

        first = _rgb(master, 0.5)
        second = _rgb(master, 1.5)
        if first[0] <= first[2] + 60:
            raise AssertionError(f"master first interval is not red-dominant: {first}")
        if second[2] <= second[0] + 60:
            raise AssertionError(f"master second interval is not blue-dominant: {second}")

        print("master cli smoke ok", first, second, program.stat().st_size)


if __name__ == "__main__":
    main()
