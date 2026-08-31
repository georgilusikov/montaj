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
)
from thz_planner.timeline import ContentEdit, build_timeline_manifest
from thz_render import (
    compile_ffmpeg_timeline,
    concat_list_text,
    ffmpeg_concat_command,
    ffmpeg_segment_command,
)


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
        anchor_policy="smoke",
        time_basis="output",
        derived={"motion_duration_ms": 0},
    )


def _average_rgb(path: Path, at_seconds: float) -> tuple[int, int, int]:
    result = _run(
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
    if len(result.stdout) < 3:
        raise AssertionError("failed to sample rendered frame")
    return tuple(result.stdout[:3])  # type: ignore[return-value]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="thz_timeline_smoke_") as tmp:
        root = Path(tmp)
        source = root / "source.mp4"
        master = root / "master.mp4"

        # Source is RED (0-1s), GREEN (1-2s), BLUE (2-3s).
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

        # Remove the green second: output must be RED -> BLUE.
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
        timeline = compile_ffmpeg_timeline(
            manifest,
            fps=10.0,
            source_w=320,
            source_h=568,
            output_w=320,
            output_h=568,
        )
        if [
            (segment.source_start_ms, segment.source_end_ms)
            for segment in timeline.segments
        ] != [(0, 1000), (2000, 3000)]:
            raise AssertionError("compiled source mapping does not match jumpcut manifest")

        rendered: list[Path] = []
        for index, segment in enumerate(timeline.segments):
            output = root / f"segment_{index:02d}.mp4"
            _run(
                ffmpeg_segment_command(
                    segment,
                    input_path=source,
                    output_path=output,
                )
            )
            rendered.append(output)

        concat_file = root / "concat.txt"
        concat_file.write_text(concat_list_text(rendered), encoding="utf-8")
        _run(ffmpeg_concat_command(concat_list_path=concat_file, output_path=master))

        first = _average_rgb(master, 0.5)
        second = _average_rgb(master, 1.5)
        if first[0] <= first[2] + 60:
            raise AssertionError(f"first kept interval is not red-dominant: {first}")
        if second[2] <= second[0] + 60:
            raise AssertionError(f"second kept interval is not blue-dominant: {second}")

        print(
            "timeline smoke ok",
            timeline.renderer_program_sha256,
            first,
            second,
        )


if __name__ == "__main__":
    main()
