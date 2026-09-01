---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head видео (9:16, Shorts, Reels, TikTok) по архитектуре v1.7.1 Lite: normalize → speech_cleanup → agent semantic WHY → semantic_events.py → frame defects/perception → zoom_planner.py → fail-closed simple_qc.py → render_zoom.py → post_render_qc.py. Triggers: "смонтируй говорящую голову", "talking head zoom", "сделай зумы как в рилс", "подрежь паузы и расставь зумы", "автомонтаж shorts", "v1.7 lite", "zoom_planner", "ratchet zoom".'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.1 Lite

Компактный production-ready пайплайн для talking-head. Главный принцип:

```text
CONTENT/PACING ≠ SEMANTIC FRAMING
```

Паузы и jumpcut-ритм принадлежат Phase 1. Зум/крупность появляются только из смысла.

## 1. Обязательный пайплайн

```text
1. normalize_source.py
        ↓ normalized.mp4

2. Whisper word timings
        ↓ raw words

3. speech_cleanup.py
        ↓ dense.mp4 + output_words + content_cuts_ms

4. Agent semantic pass — WHY ONLY
        ↓ semantic_marks.json

5. semantic_events.py
        ↓ semantic_events.json
        (word indices → exact dense-timeline ms + boundary candidates)

6. frame_defects.py / perception
        ↓ observations / defect gates

7. assemble analysis.json
        ↓ semantic_events + observations + content_cuts_ms

8. zoom_planner.py
        ↓ zoom_plan.json

9. simple_qc.py                 ← MUST PASS BEFORE RENDER
        ↓

10. render_zoom.py
        ↓ final.mp4

11. post_render_qc.py           ← MUST PASS ON ACTUAL PIXELS
        ↓ accepted final
```

**Запрещено:**
- вызывать `zoom_planner.py` до semantic pass;
- создавать ad-hoc `build_analysis.py`, новый planner или подменять scripts своей реализацией;
- считать `0` зумов успешным результатом длинного talking-head без явного override;
- принимать PASS только потому, что JSON валиден;
- использовать gaze/head-return как WHY.

Если обязательный шаг не выполнен — остановиться с FAIL, а не молча деградировать до same-scale edit.

## 2. Semantic Director contract — агент отвечает только за WHY

Агент читает `output_words` на dense timeline и создаёт `semantic_marks.json`.

```json
{
  "words": [
    {"text": "Nunca", "start_ms": 0, "end_ms": 280}
  ],
  "semantic_marks": [
    {
      "id": "hook",
      "start_word": 0,
      "end_word": 6,
      "importance": 0.78,
      "direction": "build",
      "motion_hint": "step",
      "zoom_duration_type": "beat",
      "why": "contrarian opening thesis"
    }
  ]
}
```

Обязательные поля mark:
- `start_word`, `end_word` — индексы слов, не придуманные миллисекунды;
- `importance` 0..1;
- `why` — конкретная смысловая причина.

Опционально:
- `direction`: `build|peak|release|neutral|ratchet_1|ratchet_2|ratchet_3`;
- `motion_hint`: `auto|step|slow_push`;
- `zoom_duration_type`: `micro_punch|beat|argument_hold`.

`semantic_events.py` детерминированно переводит word spans в реальные `t_ms/end_ms` и создаёт nearby word-boundary candidates. Агент **не назначает финальный таймкод склейки**.

Для spoken span ≥8 s пустой `semantic_marks` = FAIL по умолчанию. Намеренный no-zoom требует явного `allow_no_semantic_events=true`.

### Что считается WHY

Полезные причины:
- hook / contrarian thesis;
- антитеза;
- важное правило или число;
- предупреждение / consequence;
- смена аргумента;
- пример → вывод;
- punchline / conclusion;
- escalation в перечислении.

Не являются WHY сами по себе:
- прошло N секунд;
- взгляд вернулся в камеру;
- произошёл jumpcut;
- «давно не было зума».

## 3. Visual vocabulary

Default moderate:

```text
CONTEXT     1.00x       exact source frame / home
ARGUMENT    ~1.10–1.12  normal semantic punch
EMPHASIS    ~1.16       rare peak
dynamic EMPHASIS cap    1.20
```

Фактическая крупность вычисляется из реального размера лица и безопасной геометрии. 4K повышает quality headroom, но не художественный zoom cap.

## 4. Motion

- `step` — основной язык Reels/Shorts;
- `slow_push` — редкий, только по explicit semantic `motion_hint`;
- `hold` — если смысл не требует изменения.

`ARGUMENT/EMPHASIS` — временные semantic episodes:
- `micro_punch`: 0.8–1.4 s;
- `beat`: 1.5–2.4 s;
- `argument_hold`: 2.5–3.5 s.

После эпизода обычно возврат в exact CONTEXT 1.00x.

## 5. WHEN и геометрия

Hard reject boundary:
- blink / long eye closure;
- MAR mouth distortion;
- blur;
- unsafe head pose / strong turn;
- hard gesture/prop conflict;
- unsafe crop / face travel / headroom.

Soft bonuses:
- близость к semantic event;
- word boundary;
- pause;
- head return;
- cadence fit.

Gaze/head pose влияет только на **WHEN**, никогда не создаёт WHY.

### Tripod Lock

Внутри `hold` crop `(X,Y)` фиксирован. Покадровый face tracking запрещён. Камера меняется только через `step` или детерминированный `slow_push`.

### Eye anchor

Для slow push:

```text
Delta_Y = (Y_eyes - Y_center) * (1 - 1/scale)
```

Линия глаз не должна плавать при изменении крупности.

## 6. Visual rhythm

```text
visual refresh every ~2–5 s ≠ zoom every ~2–5 s
```

`content_cuts_ms` принадлежат pacing layer. Если образовался длинный visual gap, planner может вернуть `cadence_request=jumpcut_same_scale`; это не semantic zoom.

## 7. Fail-closed QC

### Pre-render: `simple_qc.py`

Помимо geometry/caps/no-op проверок:

- spoken edit ≥8 s + `decisions=[]` → `missing_semantic_events` → FAIL;
- long edit + `visible_change_count=0` → `no_visible_framing_changes` → FAIL;
- есть ARGUMENT/EMPHASIS intent, но ни одного видимого crop change → `semantic_accent_became_noop` → FAIL.

Только намеренный editorial no-zoom:

```json
{"config": {"allow_no_visible_framing": true}}
```

### Post-render: `post_render_qc.py`

Для каждого видимого semantic decision:
1. берёт frame из `dense.mp4`;
2. применяет ожидаемый `crop_end`;
3. сравнивает его с реальным frame из `final.mp4`;
4. если пиксели не соответствуют плану → FAIL `render_does_not_match_planned_crop`.

Так JSON PASS больше не является доказательством, что зум реально попал в видео.

## 8. Canonical commands

```bash
# pacing
python scripts/speech_cleanup.py speech_input.json cleanup_plan.json \
  --input-video normalized.mp4 \
  --output-video dense.mp4 \
  --export-srt captions.srt

# WHY → deterministic timing
python scripts/semantic_events.py semantic_input.json semantic_events.json

# assemble analysis.json from:
# source + observations + semantic_events.json#semantic_events + cleanup_plan.json#content_cuts_ms

python scripts/zoom_planner.py analysis.json zoom_plan.json

# mandatory pre-render gate
python scripts/simple_qc.py zoom_plan.json

# render only after PASS
python scripts/render_zoom.py dense.mp4 zoom_plan.json final.mp4

# mandatory artifact verification
python scripts/post_render_qc.py dense.mp4 final.mp4 zoom_plan.json
```

Acceptance = **pre-render PASS + post-render PASS**.
