# EXP003 Archive

- Purpose: calibrate FlashFuzz validity statistics after duplicated/appended
  libFuzzer logs produced inconsistent counts, then validate clean 60-second
  trials across 10 APIs.
- Why it is not on the formal paper line: this was a measurement-correction and
  short-run calibration experiment, not the final coverage baseline.
- Replacement: EXP004 extended the baseline duration, and EXP005 supersedes it
  as the formal baseline reference for later experiments.
- Original path: `/home/nathan/FlashFuzz/experiment/EXP003_clean_60s_trials/`
- Lightweight summary included: yes; the calibration note, per-API summary,
  and per-run summary are included.
