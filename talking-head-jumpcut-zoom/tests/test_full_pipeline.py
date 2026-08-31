#!/usr/bin/env python3
import json
import tempfile
import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from speech_cleanup import plan_cleanup, export_srt
from zoom_planner import plan
from simple_qc import check
from render_zoom import _commands


def test_full_pipeline_flow():
    speech_input = {
        "source": {"duration_ms": 15000},
        "config": {
            "mode": "strict",
            "cut_threshold_ms": 500,
            "target_gap_ms": 180,
            "head_pad_ms": 120,
            "tail_pad_ms": 300,
            "word_pre_pad_ms": 40,
            "word_post_pad_ms": 60,
        },
        "words": [
            {"text": "Во-первых", "start_ms": 500, "end_ms": 1100},
            {"text": "мы", "start_ms": 1150, "end_ms": 1400},
            {"text": "строим", "start_ms": 1450, "end_ms": 1900},
            {"text": "Во-вторых", "start_ms": 3200, "end_ms": 3900},
            {"text": "держим", "start_ms": 3950, "end_ms": 4300},
            {"text": "фокус", "start_ms": 4350, "end_ms": 4800},
            {"text": "И", "start_ms": 6500, "end_ms": 6700},
            {"text": "главное", "start_ms": 6750, "end_ms": 7200},
            {"text": "побеждаем", "start_ms": 7250, "end_ms": 8000},
        ],
    }

    cleanup_res = plan_cleanup(speech_input)
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp_srt:
        srt_path = Path(tmp_srt.name)
    export_srt(cleanup_res["output_words"], srt_path, max_words_per_card=3)

    planner_input = {
        "source": {
            "width": 1080,
            "height": 1920,
            "duration_ms": cleanup_res["output_duration_ms"],
            "quality_cap": 1.25,
        },
        "config": {
            "intensity": "dynamic",
            "absolute_zoom_cap": 1.20,
        },
        "observations": [
            {
                "t_ms": t,
                "face_cx": 0.50,
                "face_cy": 0.35,
                "eye_line_y": 0.30,
                "face_ratio": 0.28,
                "ear": 0.32,
                "mar": 0.18,
                "laplacian_var": 110.0,
                "flow_speed_px": 0.5,
            }
            for t in range(0, cleanup_res["output_duration_ms"] + 500, 200)
        ],
        "content_cuts_ms": cleanup_res["content_cuts_ms"],
        "semantic_events": [
            {
                "id": "item1",
                "t_ms": 400,
                "end_ms": 2000,
                "importance": 0.60,
                "direction": "ratchet_1",
                "boundary_candidates": [{"ms": 400, "word_boundary": True, "ear": 0.32, "mar": 0.18}],
            },
            {
                "id": "item2",
                "t_ms": 2200,
                "end_ms": 4000,
                "importance": 0.75,
                "direction": "ratchet_2",
                "boundary_candidates": [{"ms": 2200, "word_boundary": True, "ear": 0.32, "mar": 0.18}],
            },
            {
                "id": "item3",
                "t_ms": 4300,
                "end_ms": 6200,
                "importance": 0.95,
                "direction": "ratchet_3",
                "boundary_candidates": [{"ms": 4300, "word_boundary": True, "ear": 0.32, "mar": 0.18}],
            },
        ],
    }

    zoom_res = plan(planner_input)
    qc_report = check(zoom_res)
    assert qc_report["status"] == "PASS", f"QC failed: {qc_report['errors']}"

    commands = _commands(zoom_res, hz=60)
    assert len(commands.splitlines()) > 0, "No sendcmd lines generated"


if __name__ == "__main__":
    test_full_pipeline_flow()
