#!/usr/bin/env python3
"""Canonical video -> visual observations pass for talking-head edits.

This is the missing machine-perception stage. It samples the dense timeline,
measures face geometry, blur and motion, and emits planner-ready observations.
MediaPipe FaceMesh is used when available; OpenCV Haar is the fallback.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from frame_defects import calculate_ear, calculate_mar, evaluate_frame_quality

VERSION = "1.7.2-lite"
DEFAULT_SAMPLE_HZ = 6.0
DEFAULT_ANALYSIS_WIDTH = 540
DEFAULT_MIN_FACE_COVERAGE = 0.70


def _load_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("visual_scan.py requires OpenCV (cv2)") from exc
    return cv2


def _largest_box(boxes: Any) -> tuple[int, int, int, int] | None:
    if boxes is None or len(boxes) == 0:
        return None
    x, y, w, h = max(boxes, key=lambda b: int(b[2]) * int(b[3]))
    return int(x), int(y), int(w), int(h)


class FaceBackend:
    def __init__(self, cv2: Any) -> None:
        self.cv2 = cv2
        self.kind = "opencv_haar"
        self.mesh = None
        try:  # optional, stronger backend
            import mediapipe as mp  # type: ignore
            solutions = getattr(mp, "solutions", None)
            face_mesh = getattr(solutions, "face_mesh", None) if solutions else None
            if face_mesh is not None:
                self.mesh = face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.kind = "mediapipe_facemesh"
        except Exception:
            self.mesh = None

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.haar = cv2.CascadeClassifier(cascade_path)

    @staticmethod
    def _pt(landmarks: Any, index: int) -> tuple[float, float]:
        p = landmarks[index]
        return float(p.x), float(p.y)

    def detect(self, frame_bgr: Any) -> dict[str, Any] | None:
        h, w = frame_bgr.shape[:2]
        if self.mesh is not None:
            rgb = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2RGB)
            result = self.mesh.process(rgb)
            faces = getattr(result, "multi_face_landmarks", None)
            if faces:
                lm = faces[0].landmark
                xs = [float(p.x) for p in lm]
                ys = [float(p.y) for p in lm]
                left, right = max(0.0, min(xs)), min(1.0, max(xs))
                top, bottom = max(0.0, min(ys)), min(1.0, max(ys))

                left_eye = [self._pt(lm, i) for i in (33, 160, 158, 133, 153, 144)]
                right_eye = [self._pt(lm, i) for i in (362, 385, 387, 263, 373, 380)]
                mouth = [self._pt(lm, i) for i in (61, 81, 13, 291, 14, 178)]
                left_ear = calculate_ear(left_eye)
                right_ear = calculate_ear(right_eye)
                mar = calculate_mar(mouth)
                eye_line_y = sum(self._pt(lm, i)[1] for i in (33, 133, 362, 263)) / 4.0
                return {
                    "face_bbox": [left, top, right, bottom],
                    "face_cx": (left + right) / 2.0,
                    "face_cy": (top + bottom) / 2.0,
                    "face_ratio": bottom - top,
                    "eye_line_y": eye_line_y,
                    "left_ear": left_ear,
                    "right_ear": right_ear,
                    "ear": (left_ear + right_ear) / 2.0,
                    "mar": mar,
                }

        gray = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2GRAY)
        boxes = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
        box = _largest_box(boxes)
        if box is None:
            return None
        x, y, bw, bh = box
        left, top, right, bottom = x / w, y / h, (x + bw) / w, (y + bh) / h
        return {
            "face_bbox": [left, top, right, bottom],
            "face_cx": (left + right) / 2.0,
            "face_cy": (top + bottom) / 2.0,
            "face_ratio": bottom - top,
            "eye_line_y": top + 0.36 * (bottom - top),
        }

    def close(self) -> None:
        if self.mesh is not None:
            try:
                self.mesh.close()
            except Exception:
                pass


def _flow_speed(cv2: Any, previous_gray: Any | None, gray: Any) -> float:
    if previous_gray is None:
        return 0.0
    flow = cv2.calcOpticalFlowFarneback(previous_gray, gray, None, 0.5, 2, 15, 2, 5, 1.1, 0)
    mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    return float(mag.mean())


def scan_video(
    video_path: str | Path,
    *,
    sample_hz: float = DEFAULT_SAMPLE_HZ,
    analysis_width: int = DEFAULT_ANALYSIS_WIDTH,
    min_face_coverage: float = DEFAULT_MIN_FACE_COVERAGE,
) -> dict[str, Any]:
    if sample_hz <= 0:
        raise ValueError("sample_hz must be > 0")
    cv2 = _load_cv2()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if fps <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("invalid video metadata for visual scan")
    duration_ms = int(round(frame_count / fps * 1000)) if frame_count > 0 else 0
    step = max(1, int(round(fps / sample_hz)))
    scale = min(1.0, analysis_width / max(width, 1))
    scan_w = max(64, int(round(width * scale)))
    scan_h = max(64, int(round(height * scale)))

    backend = FaceBackend(cv2)
    observations: list[dict[str, Any]] = []
    previous_gray = None
    detected = 0
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step != 0:
                index += 1
                continue
            t_ms = int(round(index / fps * 1000))
            small = cv2.resize(frame, (scan_w, scan_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            flow_speed = _flow_speed(cv2, previous_gray, gray)
            previous_gray = gray
            face = backend.detect(small)

            obs: dict[str, Any] = {
                "t_ms": t_ms,
                "laplacian_var": round(laplacian_var, 3),
                "flow_speed_px": round(flow_speed, 4),
                "face_detected": face is not None,
            }
            if face is None:
                obs.update({
                    "face_cx": 0.5,
                    "face_cy": 0.34,
                    "face_ratio": 0.0,
                    "eye_line_y": 0.29,
                    "hard_block": True,
                    "visual_reject_reason": "face_not_detected",
                })
            else:
                detected += 1
                obs.update(face)
                clean, reasons = evaluate_frame_quality(obs)
                obs["hard_block"] = not clean
                if reasons:
                    obs["visual_reject_reason"] = ",".join(reasons)
            observations.append(obs)
            index += 1
    finally:
        backend.close()
        cap.release()

    if not observations:
        raise RuntimeError("visual scan produced zero observations")
    coverage = detected / len(observations)
    result = {
        "version": VERSION,
        "source": {
            "video": str(video_path),
            "width": width,
            "height": height,
            "fps": round(fps, 6),
            "duration_ms": duration_ms,
        },
        "backend": backend.kind,
        "sample_hz": sample_hz,
        "analysis_size": [scan_w, scan_h],
        "observation_count": len(observations),
        "face_detected_count": detected,
        "face_coverage": round(coverage, 4),
        "observations": observations,
    }
    if coverage < min_face_coverage:
        raise RuntimeError(
            f"visual face coverage {coverage:.1%} below required {min_face_coverage:.1%}; "
            "do not silently continue without visual evidence"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical visual perception scan for Montaj")
    parser.add_argument("video")
    parser.add_argument("output_json")
    parser.add_argument("--sample-hz", type=float, default=DEFAULT_SAMPLE_HZ)
    parser.add_argument("--analysis-width", type=int, default=DEFAULT_ANALYSIS_WIDTH)
    parser.add_argument("--min-face-coverage", type=float, default=DEFAULT_MIN_FACE_COVERAGE)
    args = parser.parse_args(argv)
    result = scan_video(
        args.video,
        sample_hz=args.sample_hz,
        analysis_width=args.analysis_width,
        min_face_coverage=args.min_face_coverage,
    )
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("version", "backend", "observation_count", "face_coverage")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
