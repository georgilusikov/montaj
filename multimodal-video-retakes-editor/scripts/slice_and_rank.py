#!/usr/bin/env python3
"""
Helper script for multimodal-video-retakes-editor skill.
Extracts word-level transcription with Whisper, clusters takes by semantic blocks,
and generates preview video clips for multimodal model inspection.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Extract and prepare video takes for multimodal inspection.")
    parser.add_argument("--input", required=True, help="Path to raw input video")
    parser.add_argument("--outdir", default="scratch/video_takes", help="Output directory for clips")
    parser.add_argument("--language", default="ru", help="ASR language hint")
    parser.add_argument("--model", default="base", help="Whisper model size (base, small, medium, large)")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] Transcribing {input_path.name} with Whisper ({args.model})...")
    import whisper
    model = whisper.load_model(args.model)
    result = model.transcribe(str(input_path), language=args.language, word_timestamps=True)

    words_json_path = out_dir / "transcript_words.json"
    with open(words_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved word timestamps to {words_json_path}")

    print(f"[2/3] Analyzing {len(result['segments'])} speech segments...")
    for i, seg in enumerate(result['segments']):
        print(f"  Segment {i:02d} [{seg['start']:6.2f}s - {seg['end']:6.2f}s]: {seg['text']}")

    print(f"[3/3] Ready for candidate slicing and multimodal inspection via view_file.")


if __name__ == "__main__":
    main()
