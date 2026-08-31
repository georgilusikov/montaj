from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from thz_planner.schema import CanonicalCrop, RenderPrimitive
from thz_render import (
    RenderKeyframe,
    RenderSegmentPlan,
    bind_sendcmd_file,
    compile_ffmpeg_segment,
)


def _frame_hashes(framemd5: str) -> list[str]:
    hashes: list[str] = []
    for line in framemd5.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 6:
            hashes.append(parts[-1])
    return hashes


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is required for renderer smoke test")

    plan = RenderSegmentPlan(
        segment_id="smoke",
        start_ms=0,
        end_ms=1000,
        primitive=RenderPrimitive.LINEAR_RAMP,
        keyframes=(
            RenderKeyframe(0, CanonicalCrop(0, 0, 320, 568)),
            RenderKeyframe(500, CanonicalCrop(40, 70, 240, 426)),
        ),
    )
    program = compile_ffmpeg_segment(
        plan,
        source_w=320,
        source_h=568,
        output_w=320,
        output_h=568,
    )
    if program.sendcmd_text is None:
        raise AssertionError("dynamic crop must produce sendcmd program")

    with tempfile.TemporaryDirectory(prefix="thz_ffmpeg_") as temp_dir:
        command_path = Path(temp_dir) / "crop_commands.txt"
        command_path.write_text(program.sendcmd_text, encoding="utf-8")
        filtergraph = bind_sendcmd_file(program, str(command_path))

        source = (
            "color=size=320x568:rate=30:color=black,"
            "drawbox=x=0:y=0:w=160:h=284:color=red:t=fill,"
            "drawbox=x=160:y=0:w=160:h=284:color=green:t=fill,"
            "drawbox=x=0:y=284:w=160:h=284:color=blue:t=fill,"
            "drawbox=x=160:y=284:w=160:h=284:color=white:t=fill"
        )
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                source,
                "-t",
                "1",
                "-vf",
                filtergraph,
                "-f",
                "framemd5",
                "pipe:1",
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    hashes = _frame_hashes(proc.stdout)
    if len(hashes) != 30:
        raise AssertionError(f"expected 30 frames, got {len(hashes)}")
    if len(set(hashes)) != 2:
        raise AssertionError(
            "static source should yield exactly two rendered compositions; "
            f"got {len(set(hashes))} unique frames"
        )
    if len(set(hashes[:10])) != 1 or len(set(hashes[-10:])) != 1:
        raise AssertionError("crop states must be stable before and after the command")
    if hashes[0] == hashes[-1]:
        raise AssertionError("runtime crop command did not change rendered composition")

    print("ffmpeg canonical crop smoke: OK")


if __name__ == "__main__":
    main()
