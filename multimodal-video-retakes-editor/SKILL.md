---
name: multimodal-video-retakes-editor
description: |
  Use when raw footage has multiple retakes/false-starts per line and the best takes must be selected via multimodal inspection (view_file on video).
  Triggers: "смонтируй видео с дублями", "выбери лучшие дубли", "вырежи повторы и склей", "retakes editor", "отсмотри видео и смонтируй".
  FOR: ASR-driven retake selection + multimodal quality grading + clean_source assembly for downstream jumpcut-zoom.
  NOT for: zoom/grading/subtitles on already-clean footage (/talking-head-jumpcut-zoom), multicam sync (Premiere/DaVinci).
---

# Multimodal Video Retakes Editor v1.0

Сквозной монтаж сырых talking-head записей со множеством дублей: нормализация → пословная ASR → сегментация на дубли → мультимодальный отбор лучших → удаление оговорок/фальстартов/мета-реплик (**через выбор дубля**, а не резку) → сборка `clean_source` для downstream.

**НЕ делает (делегирует `/talking-head-jumpcut-zoom`):** внутренние паузы, ритм, зумы, грейд, субтитры-рендер, амбиенс-кровать.

Детали: [intake и конфиг](references/intake-and-config.md) · [рубрика и метрики](references/rubric-and-metrics.md) · [контракт с skill-1](references/takes-report-contract.md).

---

## Назначение

Этот skill нужен когда у пользователя:
- `исходник содержит 3–10 дублей каждой реплики`
- `нужно найти и оставить только идеальные дубли`
- `нужно собрать единый связный ролик без щелчков и фазовых искажений`

## When to Use

- `смонтируй видео с дублями`
- `выбери лучшие дубли`
- `вырежи повторы и склей`
- `retakes editor`
- `отсмотри видео и смонтируй`

## When NOT to Use

- Один дубль без повторов → сразу `/talking-head-jumpcut-zoom`
- Multicam → Premiere/DaVinci
- Чистая конвертация → ffmpeg напрямую

## Input checklist

- [ ] Видеофайл доступен локально (MOV/MP4/MKV)
- [ ] `ffmpeg`, `ffprobe`, python `whisper` установлены
- [ ] Определён downstream: `jumpcut_zoom` (дефолт) или `none`

---

## P-01. Политика пауз и границ (несущее правило)

| Что | Действие | Режим |
|---|---|---|
| Пре-речевой заход (вдох/причмок до первого слова) | подрезка к lead **40–150 мс** | всегда |
| Пост-речевой хвост | стоп через **50–120 мс** после последнего звука | всегда |
| **Внутренняя пауза внутри дубля** | **НЕ резать** | default при `downstream=jumpcut_zoom` |
| Катастрофический dead-air (> 3 с) | укоротить до residual 600 мс | только `pauses=cap` |
| Паразит с паузами ≥ 180 мс с обеих сторон | micro-cut + 25 мс фейды (tier B) | `fillers=on` |
| Встроенный паразит / оговорка / фальстарт | не резать — отбраковать дубль | всегда |
| Встроенный вдох | attenuate −8 дБ | `breath_policy=attenuate` |
| Зазор между блоками | вставка **100–120 мс** room-tone | всегда |
| Граница дубля и моргание | предпочитать ≥ 150 мс от блинка | soft, лог `boundary_blink_ok` |

**Обоснование:** внутренний рез паузы = jump-cut без eye-line/blink/blur-гейтов; downstream тримает паузы ≥ 300 мс своими гейтами; двойной трим делает подачу тараторящей. Сохранённые паузы пробрасываются в `takes_report.internal_pauses`.

---

## §3. Пайплайн

### §3.1 Probe + Normalization + Checkpoint
ffprobe (rotation/VFR/HDR) → normalize (rotation физически, VFR→CFR, Rec.709, yuv420p). Кэш: ключ = `hash(source) + hash(asr-params + config)`; повторный запуск не пересчитывает.

### §3.2 ASR
Whisper `large-v3-turbo` + Silero VAD, `word_timestamps=True` → `transcript_words.json`. (`base` — только scratch-превью.)

### §3.3 Блоки, дубли, мета-сегменты
- Со сценарием: блоки = строки сценария, alignment fuzzy ≥ 0.75; роли блоков из сценария.
- Без сценария: кластеризация по сходству транскриптов; блоки — на подтверждение при `approval=human`.
- Дубль через два блока разрешается делить по границе блока.
- Meta-segments: «стоп/ещё раз/подожди/vale/otra vez/espera», смех → `false_start|direction|chatter`; исключаются из кандидатов.

### §3.4 Метрики + pre-rank
Ранний discard: completeness < 0.70; голос оператора внахлест; blur > 30% длительности. Детальная рубрика (веса = 1.00) — см. [rubric-and-metrics](references/rubric-and-metrics.md). **Escape-hatch:** если все кандидаты блока отброшены — лучший из отброшенных со статусом `forced`.

### §3.5 Prosody-экстракция
parselmouth (pyin) + librosa RMS → `prosody.json` (wpm, f0_median, f0_range, rms_db). `delivery=reference` → prosody_match = дистанция до вектора референса ±15%.

### §3.6 Мультимодальный отсмотр
`view_file` только **top-2** на блок (top-3 при Δscore < 0.05). Оценка: взгляд на границах, мимика/энергия, дикция, акустика. Обязательный `view_log.json` (clip, verdict, score, ts) — анти-фабрикация.

### §3.7 Финальный выбор
- `approval=human`: markdown-таблица (блок / chosen ★ / score / альтернативы / forced-флаг / ссылка на клип). Команды: `Enter` — подтвердить; `b01:t1` — свап; `del <фраза>` — micro-cut; `ref <take>` — delivery-референс.
- `approval=auto`: выбор по рубрике, таблица в отчёт.

### §3.8 Comp (композитный дубль)
Только если нет цельного чистого take: рез по клаузе с паузой ≥ 200 мс; шов |Δf0 median| ≤ 15%, |ΔRMS| ≤ 2 дБ; ≤ 1 на блок; label `comp`. **Comp на уровне слов запрещён.**

### §3.9 Гигиена границ и аудио
Тримы по P-01; 25 мс фейды на стыках; `highpass=f=70`; опциональный `pregain_match` (RMS-выбросы > 6 дБ); `loudnorm=I=-14:TP=-1:LRA=7` **на сборке целиком**; room-tone guard: Δnoise floor > 3 дБ → matched room-tone. Амбиенс запрещён при `downstream=jumpcut_zoom`. **Спектральный шумодав запрещён.**

### §3.10 Burned-captions детект
Статичные текстовые боксы в нижних 40% кадра ≥ 1 с → `source_captions=burned_keep`: SRT не экспортируется, флаг в skill-1.

### §3.11 Сборка
ffmpeg filter_complex → `clean_source`; **passthrough fps/разрешения** из normalized-источника; H.264 crf 17; `captions.srt` + word-JSON в out_ms (кроме burned_keep); naming `{date}_{slug}_clean_v{ver}_{res}.mp4`.

---

## §5. Critic (GO / NO_GO, ≤ 2 итераций, далее эскалация)

| Проверка | Порог | Severity |
|---|---|---|
| ASR_DIFF | 0 удалений/замен/вставок vs конкат chosen − removed | NO_GO |
| INTERNAL_CUTS | при preserve: 0 резов внутренних пауз (кроме filler_tier_b, dead_air_cap) | NO_GO |
| NO_DUPLICATES | один take на блок | NO_GO |
| COMPLETENESS | покрытие сценария 100% (при наличии) | NO_GO |
| CLICKS | 0 кликов на стыках | NO_GO |
| LOUDNESS | −14 ± 0.5 LUFS, TP ≤ −1 | NO_GO |
| COMP_SEAM | \|Δf0\| ≤ 15%, \|ΔRMS\| ≤ 2 дБ | NO_GO |
| SRT_SYNC | карточки 700–2200 мс, дрейф ≤ 80 мс | NO_GO |
| VIEW_LOG | у каждого chosen есть запись отсмотра | NO_GO |
| CONTAINER | passthrough res/fps, SAR 1:1, чётные размеры | NO_GO |
| BOUNDARY_LEAD | pre 40–150 / post 50–120 мс | WARN |
| BOUNDARY_EYES | at_camera на первом/последнем кадре блока | WARN |
| NOISE_PUMPING | ≤ 3 дБ | WARN |

---

## Flowchart

```
Raw → §3.1 normalize → §3.2 ASR → §3.3 blocks/meta
 → §3.4 pre-rank → §3.5 prosody → §3.6 view_file top-2/3
 → §3.7 human-таблица / auto → §3.8 comp (если нужен)
 → §3.9 гигиена границ+аудио → §3.10 captions-детект
 → §3.11 сборка clean_source + SRT
 → §5 critic ≤2 итер. → GO → takes_report.json → skill-1
```

---

## FORBIDDEN

- Рез внутренних пауз при `preserve`
- Comp на уровне слов
- Отбор дубля без `view_log` (фабрикация отсмотра)
- Спектральный шумодав (FFT gating / spectral subtraction)
- `loudnorm` по отдельным дублям (только на сборке целиком)
- Амбиенс-кровать при `downstream=jumpcut_zoom` (её добавит skill-1)
- Смена res/fps/кропа (работа skill-1)
- Два дубля одного блока в мастере

## Hard fail

- Повтор мысли (два дубля одного блока) в итоговом видео
- Слово обрезано на стыке
- «Робот»-тембр (фазовые искажения от спектрального шумодава)
- Internal-cut без документированного reason
- Нет `view_log` для chosen take
- Слышимый шов comp'а

## Известные грабли

- **whisper base на не-RU:** hallucinations → `large-v3-turbo` для прода
- **Отсмотр всех кандидатов:** O(n) view_file дорого → pre-rank + top-K
- **Двойная амбиенс-кровать:** при музыке в сырье и амбиенс от skill-1 → детект `music_bed_present`
- **Форс 30 fps/1080p при другом источнике:** → passthrough res/fps
- **Агрессивный FFT шумодав:** металлический голос → подрезка границ вместо спектральной фильтрации

## Связанные скиллы

- **ДО:** сырая запись видео с камеры/смартфона
- **ПОСЛЕ:** `/talking-head-jumpcut-zoom` — зумы, ритм, субтитры, амбиенс по `takes_report.json`

## Definition of Done

- [ ] Все дубли сгруппированы и кандидаты pre-ranked
- [ ] Каждый chosen отсмотрен через `view_file` (view_log.json)
- [ ] В мастере один take на блок, 0 повторов
- [ ] Пре/пост-тримы по P-01, 25 мс фейды, 0 кликов
- [ ] Внутренние паузы сохранены (при downstream=jumpcut_zoom)
- [ ] Звук: −14 LUFS, TP ≤ −1, без фазовых искажений
- [ ] `takes_report.json` сформирован и валиден
- [ ] Critic: все NO_GO = PASS
- [ ] `grep "^## FORBIDDEN$" SKILL.md | wc -l` ≥ 1
