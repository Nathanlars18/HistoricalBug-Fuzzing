# Experiment Dependencies

The formal experiment line starts with EXP005. EXP001-EXP004 are retained only
as early exploration and reproduction notes.

```mermaid
flowchart LR
    Raw[dataset/raw] --> EXP006[EXP006 Historical Bug Information Database]

    EXP005[EXP005 coverage baseline] --> EXP007[EXP007 single-pattern]
    EXP005 --> EXP008[EXP008 multi-pattern]
    EXP005 --> EXP009[EXP009 reasoning]
    EXP005 --> EXP010[EXP010 analysis]

    EXP006 --> EXP007
    EXP006 --> EXP008
    EXP006 --> EXP009

    EXP007 --> EXP008
    EXP007 --> EXP010
    EXP008 --> EXP009
    EXP008 --> EXP010
    EXP009 --> EXP010
```

At the data-flow level:

```text
dataset/raw
  -> EXP006
  -> EXP007 / EXP008 / EXP009
  -> EXP010

EXP005 baseline
  -> EXP007 / EXP008 / EXP009 / EXP010
```

EXP006 transforms raw historical issue material into structured reports,
patterns, and knowledge. EXP007-EXP009 consume those assets using progressively
richer prompting strategies. EXP010 compares their migrated results against the
EXP005 baseline.
