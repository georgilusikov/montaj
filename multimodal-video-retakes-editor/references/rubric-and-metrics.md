# Рубрика скоринга и метрики

## §3.4 Рубрика pre-rank (веса = 1.00)

| Метрика | Вес |
|---|---|
| completeness | 0.30 |
| diction (оговорки, встроенные паразиты, ASR conf) | 0.25 |
| prosody_match (wpm, f0-range, RMS-dyn к роли блока или reference) | 0.20 |
| eye_bounds (at_camera в первых/последних 500 мс) | 0.15 |
| acoustic_clean (вдохи/smacks внутри, noise floor) | 0.10 |

### Штрафы

| Событие | Штраф |
|---|---|
| smack (причмокивание внутри дубля) | −0.10 |
| встроенный паразит | −0.15 |
| blur / off-pose | −0.20 |
| Last Take prior | +0.05, cap score ≤ 1.0 |

### Prior роли блока

- **hook / punch** → energy+ (выше wpm, шире f0_range, громче RMS)
- **story** → calm (ниже wpm, стабильный f0, ровный RMS)

### Ранний discard

Кандидат отбраковывается до рубрики при:
- `completeness < 0.70`
- голос оператора внахлёст
- `blur > 30%` длительности дубля

### Escape-hatch

Если все кандидаты блока отброшены — блок не остаётся пустым: лучший из отброшенных со статусом `forced`, дефекты в отчёт; при `approval=human` forced-блоки показываются первыми.

---

## §3.5 Prosody-экстракция

`parselmouth` (pyin) + `librosa` RMS → `prosody.json`:

```json
{
  "take_id": "b01_t2",
  "wpm": 178,
  "f0_median_hz": 142,
  "f0_range_hz": 64,
  "rms_db": -18.2
}
```

При `delivery=reference`: prosody_match = дистанция до вектора референса ±15%.

---

## §3.6 Мультимодальный отсмотр — детали

`view_file` вызывается только для **top-2** кандидатов на блок (top-3 при Δscore < 0.05).

### Протокол оценки

1. **Зрительный контакт**: at_camera на первых/последних 500 мс фразы
2. **Мимика/энергия**: уверенная подача, отсутствие зажатости
3. **Дикция**: отсутствие запинок, проглоченных звуков
4. **Акустика**: отсутствие шумных вздохов и резких причмокиваний

### view_log.json (обязательный артефакт)

```json
{
  "entries": [
    {
      "clip": "scratch/takes/b01_t2.mp4",
      "verdict": "chosen",
      "score_override": null,
      "notes": "strong eye contact, clean diction",
      "ts": "2026-08-30T17:15:00Z"
    }
  ]
}
```

Отсутствие view_log = Hard fail (анти-фабрикация).
