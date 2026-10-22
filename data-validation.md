# Data Validation

This document describes the validation rules applied to raw meter readings,
how flagged rows are handled, and how to extend the rules for plant-specific
checks.

Validation is implemented in `scripts/data_validation.py` and the Excel
workbook replicates the same logic with live formulas in the `Readings`
sheet's `Delta (m3)` column.

---

## 1. Schema validation

The first check ensures the input CSV has every required column:

```
reading_id, meter_id, area, equipment, reading_datetime,
cumulative_reading, unit, meter_type, recorded_by, notes
```

If any column is missing, the script exits with a non-zero status and prints
the missing names to stderr. This is a hard failure — the pipeline does not
attempt to run on partial schemas.

### Type coercion

- `cumulative_reading` is cast to `float`. Non-numeric values cause an
  exception with a clear message pointing to the offending row.
- `reading_datetime` must match `YYYY-MM-DD HH:MM` or `YYYY-MM-DD`. Any
  other format raises a `ValueError`.

---

## 2. Ordering

After loading, rows are sorted by `(meter_id, reading_datetime)`. This
ensures deltas are computed against the correct previous reading for each
meter. The script writes the sorted rows back to `validated-readings.csv`
with renumbered `reading_id` values, so the output is stable and
reproducible.

---

## 3. Per-meter validation rules

For each meter, the script tracks the last valid reading and applies these
checks in order:

### 3.1 Duplicate timestamp

```
IF current.reading_datetime == last_seen.reading_datetime
   FOR the same meter_id
THEN flag = "DUPLICATE_TIMESTAMP"
```

The duplicate is recorded but excluded from the delta computation. The
reviewer must decide which (if either) is correct and remove the other from
the source.

### 3.2 Missing readings (gap)

```
IF current.reading_datetime > last_valid.reading_datetime + 1 day
THEN flag = "MISSING_READINGS"
     note = "gap of N day(s) between <prev> and <current>"
```

A single missed day is flagged; a gap of several days is flagged once with
the gap length noted. The flagged row's delta is still computed against the
last valid reading, so the daily aggregation will see a multi-day total
that needs to be apportioned by the analyst.

### 3.3 Negative delta

```
IF current.cumulative_reading < last_valid.cumulative_reading
THEN flag = "NEGATIVE_DELTA"
     note = "reading decreased by N m3 — investigate meter reset/replacement"
```

The script does not assume a rollover. A human must determine whether the
negative is due to a rollover, a meter replacement, or a manual error.

### 3.4 Rollover suspected

```
IF current.cumulative_reading - last_valid.cumulative_reading
   > 0.5 × rollover_limit
THEN flag = "ROLLOVER_SUSPECTED"
     note = "delta exceeds 50% of rollover limit"
```

This catches cases where the previous reading was very low (near zero
after a recent rollover) and the current reading is high — the delta is
mathematically correct but operationally suspicious.

### 3.5 Potential issue (statistical spike)

```
recent_deltas = last 14 valid deltas for this meter
median = median(recent_deltas)
IF median > 0 AND current.delta_m3 > 3 × median
THEN flag = "POTENTIAL_ISSUE"
     note = "consumption is Nx the 14-day median"
```

This is the most conservative check and the only one that produces a
"potential issue" flag rather than a data-quality flag. It does not
classify the spike as a leak; it merely raises the row for investigation.

### 3.6 No flag

If none of the above conditions fire, the reading is valid. Its delta is
recorded and the running median window is updated.

---

## 4. Outputs

The script writes the following files into `scripts/output/`:

| File | Contents |
|---|---|
| `validated-readings.csv` | All input rows plus `delta_m3` and `flag` columns. |
| `anomalies.csv` | Subset of `validated-readings.csv` where `flag` is non-empty. |
| `daily-summary.csv` | Per-meter daily totals (valid deltas only). |
| `weekly-summary.csv` | Per-meter ISO-week totals. |
| `monthly-summary.csv` | Per-meter monthly totals. |
| `validation-report.txt` | Human-readable summary: counts, flag breakdown, output paths. |

---

## 5. Extending the rules

Plant-specific checks you may want to add:

### Maximum daily consumption

```
IF daily_consumption(meter, date) > 5 × meter.daily_target
THEN flag = "ABOVE_MAXIMUM"
```

Useful for meters feeding safety-critical equipment where sudden high
consumption indicates a failure mode.

### Sustained low consumption

```
IF daily_consumption(meter, date) < 0.1 × meter.daily_target
   AND count of consecutive low days >= 3
THEN flag = "SUSTAINED_LOW"
```

Detects dry-running conditions that damage pumps and seals.

### Cross-meter consistency

If two meters should always show similar consumption (e.g., boiler feed
water vs. steam output converted to water equivalent), add a check that
flags days where the ratio falls outside a defined tolerance band.

### Reading-time consistency

If your plant standardizes reading at 08:00 every day, add a check that
flags any reading whose `reading_datetime` falls outside ±30 minutes of
08:00. This catches shift-handover timing drift.

### To implement

Add a new function in `scripts/data_validation.py` after the existing
`validate_and_compute()`:

```python
def custom_check(validated_rows):
    for r in validated_rows:
        if r["meter_id"] == "MTR-DYE-001":
            if r["delta_m3"] and float(r["delta_m3"]) > 250:
                r["flag"] = "ABOVE_MAXIMUM"
                r["notes"] = (r["notes"] + " | "
                              "dyeing daily max 250 m3 exceeded").strip(" |")
    return validated_rows
```

Then call it before writing the output CSVs. Keep the existing rules
untouched so the baseline pipeline remains reproducible.

---

## 6. What the validation does NOT do

- It does not call any external API to fetch meter data — the input CSV is
  the sole source of truth.
- It does not auto-correct any reading. Flagged rows are reported, not
  silently patched.
- It does not infer leak locations. The `anomaly_log` table exists for
  investigation records; the validation script does not write to it.
- It does not email or alert anyone. Alerts must be wired separately
  (cron + mail, Power BI data alerts, or an external watchdog).

---

## 7. Re-running validation

After editing the source CSV (adding new readings, correcting typos,
removing duplicates), re-run:

```bash
python scripts/data_validation.py
```

All output files are overwritten. The script is idempotent — running it on
already-validated input produces the same flags plus a "duplicate-free
status" since the duplicate has been removed.

---

## 8. Validation in Excel

The `Readings` sheet of `water-dashboard.xlsx` includes a `Delta (m3)`
column with the formula:

```
=IFERROR(
  IF(F{row} < F{prev_row},
     "NEGATIVE",
     ROUND(F{row} - F{prev_row}, 2)),
  "")
```

where `F` is the cumulative reading column and `prev_row` is the row index
of the previous reading for the same meter. The conditional formatting
rule:

```
FormulaRule(formula=['L5="NEGATIVE"'], fill=red, font=red bold)
```

visually highlights negative deltas. Other flags (missing, duplicate,
rollover, spike) are not replicated in Excel — use the Python pipeline
for the full validation suite, then import the `validated-readings.csv`
back into Excel for presentation if needed.
