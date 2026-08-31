---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head видео (9:16, Shorts, Reels, TikTok) по архитектуре v1.7 Lite: normalizer → speech_cleanup.py (Phase 1 jumpcuts & SRT) → zoom_planner.py (Phase 2 semantic WHY, eye-anchor, ratchet pattern, tripod lock) → render_zoom.py (FFmpeg 60Hz cubic easing) → simple_qc.py. Triggers: "смонтируй говорящую голову", "talking head zoom", "сделай зумы как в рилс", "подрежь паузы и расставь зумы", "автомонтаж shorts", "v1.7 lite", "zoom_planner", "ratchet zoom".'
---

# Talking-Head Jumpcut & Zoom Editor v1.7 Lite

Компактный, production-ready стандарт и пайплайн автомонтажа вертикальных экспертных роликов (9:16) для социальных сетей (Shorts, Reels, TikTok).

## 1. Архитектура ядра (2-Phase Pipeline)

```text
1. [Ingest Normalization] normalize_source.py (CFR 30fps, Rec.709 tonemap, rotation, Apple ColorSync tags)
        ↓
2. [Phase 1: Pacing]      speech_cleanup.py (вырезание пауз >500ms с паддингами +40/+60ms, dense.mp4, chunked SRT)
        ↓ dense.mp4 + output_words + content_cuts_ms
3. [Perception & CV]      frame_defects.py (EAR < 0.20 blink, MAR > 0.45 mouth, Laplacian blur, Farneback flow)
        ↓ analysis.json
4. [Phase 2: Semantics]   zoom_planner.py (WHY, Ratchet ladder, Eye-anchor slow_push, Tripod lock)
        ↓ zoom_plan.json
5. [Render & Master]      render_zoom.py (60Hz cubic easing sendcmd, -14 LUFS / TP -1.5 dBTP)
        ↓ final.mp4
6. [Deterministic QC]     simple_qc.py (проверка геометрии кропов, капов, no-op зумов)
```

---

## 2. Ключевые принципы и формулы

### 1. Формулы отсева бракованных кадров (`frame_defects.py` / `sceneflow`)
- **EAR (Eye Aspect Ratio) — детекция моргания:**
  $$EAR = \frac{\|p_2 - p_6\| + \|p_3 - p_5\|}{2 \cdot \|p_1 - p_4\|}$$
  *Правило:* Если $EAR < 0.20$, глаз закрыт или полуприкрыт. Склейка сдвигается на ближайший кадр с $EAR \ge 0.25$.
- **MAR (Mouth Aspect Ratio) — нейтральность рта:**
  $$MAR = \frac{\|m_2 - m_6\| + \|m_3 - m_5\|}{2 \cdot \|m_1 - m_4\|}$$
  *Правило:* Если $MAR > 0.45$, рот неестественно перекошен или открыт посреди слога — склейка блокируется.
- **Laplacian Variance — отсев смазанных кадров (Motion Blur):**
  $$\text{Var}(\nabla^2 I) < \text{threshold (60.0)}$$
  *Правило:* При резком повороте головы или смазе склейка блокируется.
- **Farneback Optical Flow — стабильность позы:**
  Замеряет вектор движения пикселей лица $\|v_{\text{face}}\| \le 2.0$ px/кадр. Склейка разрешается только в момент покоя головы.

---

### 2. Паттерн «Лесенка» (Ratchet) для перечислений (`add-zooms`)
Когда спикер говорит: *«Во-первых... Во-вторых... И самое главное...»*:
Масштаб не скачет хаотично, а плавно повышает ставки:
- **Пункт 1 (`ratchet_1`):** `1.08x` (ARGUMENT light)
- **Пункт 2 (`ratchet_2`):** `1.16x` (ARGUMENT deep)
- **Пункт 3 (`ratchet_3` / кульминация):** `1.20x` (EMPHASIS)
- **Выдох / итог:** резкий сброс обратно в «дом» `1.00x` (`CONTEXT`).

---

### 3. Формула удержания «якоря» глаз при `slow_push` (`add-zooms`)
При медленном наплыве (slow_push на 2–4%) лицо не сползает вниз/вверх благодаря формуле смещения центра кропа:
$$\Delta Y = (Y_{\text{eyes}} - Y_{\text{center}}) \cdot \left(1 - \frac{1}{\text{scale}}\right)$$
*Результат:* Линия глаз спикера остаётся зафиксированной на оптической линии (верхняя треть, $\approx 30\%$ от верха), пока границы кадра мягко сужаются.

---

### 4. Принцип «Tripod Lock» (`clippyme`)
Защита от «морской болезни» и плавания камеры:
- Внутри одного сегмента (`hold`) координаты кропа $(X, Y)$ фиксируются намертво по медиане ключевых точек за весь сегмент.
- Покадровый трекинг лица (Face Tracking) во время речи **запрещён**. Камера двигается только в момент дискретной `step`-склейки или детерминированного `slow_push`.

---

### 5. Акустическая безопасность и экспорт субтитров (Phase 1)
- **Acoustic Padding:** $+40$ мс до слова (защита предвзрывных интервалов П, Б, Т, Д, К) и $+60$ мс после слова (защита формантных хвостов).
- **Микро-кроссфейды:** 15 мс на аудио-стыках.
- **Chunked SRT:** экспорт субтитров блоками по 1–3 слова по таймкодам `out_ms` с учётом Safe-Zone (нижние 350-420 px).

---

## 3. Схема вызова инструментов

```bash
# 1. Нормализация исходника в CFR Rec.709
python scripts/normalize_source.py raw_input.mov normalized.mp4 --fps 30

# 2. Фаза 1: Очистка пауз, джампкаты и экспорт субтитров
python scripts/speech_cleanup.py speech_input.json cleanup_plan.json \
  --input-video normalized.mp4 \
  --output-video dense.mp4 \
  --export-srt captions.srt

# 3. Фаза 2: Семантический расчет зумов
python scripts/zoom_planner.py analysis_input.json zoom_plan.json

# 4. Проверка качества
python scripts/simple_qc.py zoom_plan.json

# 5. Финальный рендер
python scripts/render_zoom.py dense.mp4 zoom_plan.json final_master.mp4
```
