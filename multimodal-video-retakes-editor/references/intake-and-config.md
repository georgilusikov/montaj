# Intake и конфигурация

## §2. Intake (Enter = дефолт; сохраняется в `project_config_retakes.json`, далее молча)

| # | Вопрос | Дефолт |
|---|---|---|
| 1 | Язык ASR | `auto` |
| 2 | Сценарий: none / текст / файл | `none` |
| 3 | `downstream`: jumpcut_zoom / none | `jumpcut_zoom` |
| 4 | `pauses`: preserve / cap / trim_light | auto: `preserve` при jumpcut_zoom, `trim_light` при none |
| 5 | Fillers: on / off + `fillers_keep`-whitelist | `on`, RU+ES словари по умолчанию |
| 6 | `breath_policy`: attenuate / trim / keep | `attenuate` |
| 7 | `approval.takes`: human / auto | `human` (минимальная таблица, §3.7) |
| 8 | `delivery`: auto / reference (таймкод эталонного дубля) | `auto` |

---

## §7. Артефакты и retention

**Остаются после GO:**
- `clean_source.mp4`
- `takes_report.json`
- `transcript_words.json`
- `blocks.json`
- `prosody.json`
- `view_log.json`
- `critic_report.json`
- `captions.srt` + word-JSON (если не burned_keep)
- `project_config_retakes.json`

**Удаляются после GO:**
- `normalized.mp4`
- `source_audio.wav`
- `scratch/takes/*`

---

## §8. Фазировка

- **v1.0 (ядро):** §0 P-01, §3.1–3.11, §4, §5, §7.
- **v1.1:** расширенный human-UX (preview-клипы), multi-file merge одной сессии, детект burned-captions с инпейнт-опцией.
- **v2:** re-edit mode («удали фразу / замени дубль» инкрементально по takes_report), A/B-экспорт двух подач хука, operator-notes отчёт из chatter, breath-gate hard (не ставить рез внутрь вдоха ±120 мс).
