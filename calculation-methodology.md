# Calculation Methodology

This document defines how water consumption is computed from raw meter
readings, how summaries are aggregated, and how variances against targets are
calculated. It is the authoritative reference for any analyst re-implementing
the calculations in a different tool (Power BI, Tableau, SQL, etc.).

---

## 1. Core formula — consumption from cumulative meters

For a **cumulative** water meter (the only meter type in the sample dataset),
consumption between two consecutive valid readings is:

```
delta_m3 = current_cumulative_reading − previous_cumulative_reading
```

Where:

- **current** and **previous** refer to consecutive readings **for the same
  meter**, sorted ascending by `reading_datetime`.
- **valid** means the reading passes all validation checks (see
  `docs/data-validation.md`). Flagged readings are excluded from delta
  calculation but still recorded for investigation.

### Worked example

| reading_id | meter_id | reading_datetime | cumulative_reading | delta_m3 |
|---|---|---|---|---|
| R00012 | MTR-DYE-001 | 2024-01-12 08:00 | 124_914.30 | — (first valid for meter) |
| R00018 | MTR-DYE-001 | 2024-01-13 08:00 | 124_961.45 | 47.15 |
| R00024 | MTR-DYE-001 | 2024-01-14 08:00 | 125_007.80 | 46.35 |

For `R00018`: `124_961.45 − 124_914.30 = 47.15 m³`.

For `R00012`: there is no previous valid reading for `MTR-DYE-001`, so
`delta_m3` is left blank.

---

## 2. Meter resets, replacements, and rollovers

A delta can be negative for legitimate reasons:

- **Meter rollover** — The cumulative counter wraps past its maximum
  (`rollover_limit`) and resets to near-zero. The actual consumption equals
  `rollover_limit − previous_reading + current_reading`.
- **Meter replacement** — A new meter is installed; its starting reading
  (often zero) is unrelated to the previous meter's reading. The reading is
  valid as a new baseline but no delta should be computed across the
  replacement boundary.
- **Manual entry error** — A typo. Must be corrected in the source system.

### How the pipeline handles these

The validation script flags every negative delta as `NEGATIVE_DELTA` and
appends an investigation note. It does **not** silently assume a rollover. A
human reviewer must:

1. Inspect the operator `notes` column.
2. Check whether the `meter_register` shows a recent replacement.
3. Compare against the rollover limit for that meter.
4. Confirm the explanation before back-filling the delta.

Until the reviewer acts, the flagged row's `delta_m3` is left blank — that
day's consumption is reported as `NO DATA` in the dashboard rather than
inferred.

---

## 3. Daily aggregation

```
daily_consumption(meter, date) = Σ delta_m3
                                  for all readings r where
                                    r.meter_id = meter
                                    AND date(r.reading_datetime) = date
                                    AND r.flag is empty (valid)
```

### Properties

- If a meter has **no valid readings** on a given day, `daily_consumption` is
  `NULL`, **not** zero. Zero would falsely imply the meter was read and
  recorded no consumption.
- If a meter has multiple readings on the same day (e.g., hourly), they are
  summed.
- Flagged readings are excluded so anomalies do not distort the daily total.

### Excel formula equivalent

In the `Daily Summary` sheet of `water-dashboard.xlsx`:

```
= SUMIFS(Readings!L:L, Readings!C:C, <meter_id>,
         Readings!F:F, "<date>")
```

where `Readings!L:L` is the `Delta (m3)` column (which itself uses an
`IFERROR(IF(... < 0, "NEGATIVE", ROUND(...))` formula — see `Readings` sheet
construction in `scripts/build_excel_dashboard.py`).

---

## 4. Weekly aggregation (ISO week)

```
weekly_consumption(meter, iso_year, iso_week) = Σ daily_consumption(meter, date)
                                                   for date in the ISO week
```

The sample script uses Python's `datetime.isocalendar()` to identify the week
boundary. Weekly targets, when present, equal `daily_target × 7`. Days with
`NULL` consumption are treated as missing; the weekly total is reported with a
coverage note.

---

## 5. Monthly aggregation

```
monthly_consumption(meter, year_month) = Σ daily_consumption(meter, date)
                                          for date in the month
```

Monthly target = `daily_target × number_of_days_in_month`.

For example, with `daily_target = 50 m³/day` for `MTR-DYE-001` in July 2024
(31 days):

```
monthly_target = 50 × 31 = 1_550 m³
```

---

## 6. Variance calculations

### Absolute variance

```
variance_m3 = consumption_m3 − target_m3
```

Negative variance = under target (good).
Positive variance = over target (investigate).

### Percentage variance

```
variance_pct = (consumption_m3 − target_m3) / target_m3
```

Reported to 2 decimal places (e.g., `+12.4%`, `-5.0%`).

### Status classification (Excel dashboard)

The Excel `Daily Summary` sheet classifies each day with a status:

| Condition | Status | Color |
|---|---|---|
| `consumption = 0` | `NO DATA` | neutral |
| `consumption > 1.5 × target` | `OVER` | red |
| `consumption > 1.1 × target` | `HIGH` | amber |
| `consumption < 0.5 × target` | `LOW` | neutral (informational) |
| otherwise | `OK` | green |

This classification is for **screening** — it is not an audit-grade leak
detection. Use it to prioritize investigation, not to declare savings or
losses.

---

## 7. Anomaly detection — what is and is not a leak

The Python validation script flags a `POTENTIAL_ISSUE` when:

```
delta_m3 > 3 × median(last 14 valid deltas for the same meter)
```

This statistical test is intentionally conservative:

- A 3× spike can have many causes: production surge, batch operation, CIP
  cycle, meter fault, calibration drift, or genuine leak.
- The script does not have access to production schedule, run-time logs, or
  maintenance history, so it cannot disambiguate.
- The flag is a **work order** for on-site investigation, not a conclusion.

### What you must NOT do

- Do NOT report a flagged row as a confirmed leak in any management report.
- Do NOT calculate "water saved" by subtracting the flagged delta from a
  baseline — that is fabrication.
- Do NOT remove a flag without documenting the investigation outcome in the
  `anomaly_log.investigator_notes` column.

### What you SHOULD do

1. Visit the meter and verify the reading.
2. Check the production log for unusual activity in that area on that date.
3. Inspect visible pipework and fittings near the meter.
4. If the cause is operational, log it and clear the flag.
5. If the cause is a leak, document the leak (location, repair date,
   estimated volume) in a separate maintenance record — the dashboard does
   not double as a leak ledger.

---

## 8. Targets — when are they valid?

A target is only meaningful when:

- It comes from an authorized source — plant manager, sustainability team,
  equipment OEM baseline, or regulatory limit. **Never invented by the analyst.**
- It is time-bounded — daily targets for a steady-state operation, monthly
  targets for seasonal operations.
- It accounts for production volume. A textile factory's dyeing-line water
  consumption scales with production throughput; a static m³/day target
  becomes meaningless if production doubles.

The `DAILY_TARGETS` dictionary in `scripts/data_validation.py` and the
`Target (m3)` column in the Excel `Daily Summary` sheet are **placeholders**
showing how the variance calculation works. Replace them with
plant-authorized values before using the dashboard for management reporting.

---

## 9. Units and conversions

All data in this repository is in **cubic metres (m³)**. When ingesting data
from a source that uses litres (L) or US gallons (gal), convert before
appending to the log:

| From | To m³ | Multiplier |
|---|---|---|
| L | m³ | ÷ 1000 |
| US gal | m³ | × 0.00378541 |
| Imperial gal | m³ | × 0.00454609 |
| ft³ | m³ | × 0.0283168 |

Always store the original unit in the `unit` column of the log and keep the
`rollover_limit` in the same unit as the readings.

---

## 10. What has and has not been verified

### Verified

- All formulas in this document are implemented and tested in both the
  Python pipeline (`scripts/data_validation.py`) and the Excel workbook
  (`dashboard/water-dashboard.xlsx`).
- The Python pipeline correctly flags all 6 injected anomalies in the
  sample dataset (14 total flags counting the rolling-median spike detection).
- The Excel workbook computes deltas via live formulas and updates
  summaries when readings are edited.
- All numbers in the sample dataset are synthetic — no real plant data is
  used.

### Not verified

- Targets in `DAILY_TARGETS` are illustrative placeholders.
- Anomaly flags are statistical indicators, not on-site findings.
- The hardware wiring guide (`docs/hardware-wiring.md`) describes typical
  industrial practice but does not certify any specific installation.
- The Power BI build guide describes a recommended layout but does not ship
  a `.pbix` file (Power BI Desktop is required to open one).

If you adapt this repository to a real plant, the verification
responsibility passes to you.
