# Контракт с skill-1: takes_report.json

## §4. Структура

```json
{
  "prepared_by": "retakes-editor",
  "version": "1.0",
  "downstream": "jumpcut_zoom",
  "pauses_preserved": true,
  "source": "raw.mov",
  "clean_source": "20260831_maybach_clean_v01.mp4",
  "source_captions": "none",
  "music_bed_present": false,
  "config_echo": {
    "language": "es",
    "fillers": "on",
    "breath_policy": "attenuate",
    "approval": "human"
  },
  "blocks": [
    {
      "id": "b01",
      "role": "hook",
      "text": "…",
      "chosen": {
        "take_id": "b01_t2",
        "src_ms": [33000, 57000],
        "out_ms": [0, 23850],
        "score": 0.87,
        "forced": false,
        "viewed": true,
        "gaze_bounds": ["at_camera", "at_camera"],
        "boundary_blink_ok": true,
        "prosody": {
          "wpm": 178,
          "f0_median_hz": 142,
          "f0_range_hz": 64,
          "rms_db": -18.2
        }
      },
      "discarded": [
        { "take_id": "b01_t1", "reason": "self_correction" },
        { "take_id": "b01_t3", "reason": "false_start" }
      ],
      "removed_events": [
        {
          "type": "filler_tier_b",
          "text": "eh",
          "src_ms": [41200, 41600],
          "out_ms": [8200]
        }
      ],
      "internal_pauses": [
        { "start_ms": 12400, "end_ms": 13050 }
      ],
      "comp": null
    }
  ],
  "assembly": [
    {
      "block": "b01",
      "src_ms": [33000, 57000],
      "out_ms": [0, 23850],
      "gap_ms": 120
    }
  ],
  "meta_segments_removed": [
    {
      "src_ms": [25000, 32000],
      "type": "direction",
      "text": "Vale, otra vez…"
    }
  ]
}
```

---

## Потребление skill-1 (`/talking-head-jumpcut-zoom`)

| Поле takes_report | Как skill-1 его использует |
|---|---|
| `clean_source` | source-файл для монтажа |
| `pauses_preserved` | silence-trimming активен |
| `role` | prior актов (hook→energy, story→calm) |
| `prosody` | semantic-акценты (R-07) |
| `gaze_bounds` | eye-line склеек |
| `internal_pauses` | cut-кандидаты |
| `removed_events` | preferred reframe-точки (reason: `filler_mask`) |
| `source_captions` | форс-off субтитров при burned_keep + caption_bbox-констрейнт кропа |
| `music_bed_present` | амбиенс-кровать on/off |
| `config_echo` | контекст решений |
