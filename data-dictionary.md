# Data Dictionary

This document describes every column in every data file shipped with the
Industrial Water Consumption Monitoring repository. Use it as the authoritative
reference when extending the schema, building new dashboards, or writing
validation rules.

---

## 1. `data/sample-water-readings.csv`

The primary input file. Contains anonymized cumulative meter readings for a
textile factory across one calendar year (2024).

| Column | Type | Required | Description |
|---|---|---|---|
| `reading_id` | string (PK) | yes | Unique reading identifier, format `R00001`. Sequential after sort. |
| `meter_id` | string (FK) | yes | Foreign key to `meter_register.meter_id`. Example: `MTR-DYE-001`. |
| `area` | string | yes | Functional area of the facility. Example: `Dyeing Hall`. |
| `equipment` | string | yes | Specific equipment served by the meter. Example: `Dyeing Line A`. |
| `reading_datetime` | string | yes | Reading timestamp, format `YYYY-MM-DD HH:MM`. Daily readings use `08:00`. |
| `cumulative_reading` | decimal(12,2) | yes | Totalized meter value at the reading time. |
| `unit` | string | yes | Measurement unit. Always `m3` (cubic metres) in this dataset. |
| `meter_type` | enum | yes | Meter behavior: `cumulative` (rolling total) or `flow` (instantaneous rate). |
| `recorded_by` | string | yes | Operator initials (anonymized). Example: `AB`. |
| `notes` | string | no | Free-text annotation. Used for injected anomalies (e.g., "meter replaced"). |

### Sample dataset characteristics

- **Rows:** 2,219
- **Meters:** 6
- **Date range:** 2024-01-01 to 2024-12-31
- **Cadence:** Daily at 08:00 for most meters; 24 hourly readings on
  2024-09-15 for `MTR-DYE-001` to demonstrate intra-day granularity.
- **Anomalies injected:** 1 missed reading, 1 duplicate timestamp, 1 meter
  rollover, 1 negative delta, 1 consumption spike, 24 hourly rows.

---

## 2. `templates/water-meter-register.csv`

Master list of meters. One row per physical meter.

| Column | Type | Description |
|---|---|---|
| `meter_id` | string (PK) | Unique meter identifier. Naming convention: `MTR-<AREA>-<NNN>`. |
| `area` | string | Functional area (e.g., `Dyeing Hall`, `Boiler House`). |
| `equipment` | string | Equipment tag (e.g., `Steam Boiler 1`). |
| `meter_type` | enum | `cumulative` or `flow`. |
| `unit` | string | Typically `m3`, sometimes `L` or `gal`. |
| `install_date` | date | Commissioning date. |
| `manufacturer` | string | Meter OEM. |
| `model` | string | Meter model number. |
| `serial_number` | string | Unique device serial. |
| `location_code` | string | Physical location tag in the plant. |
| `rollover_limit` | int | Maximum value before the meter resets to zero. Used by validation. |
| `calibration_due` | date | Next calibration due date. |
| `status` | enum | `active`, `decommissioned`, `out_for_calibration`. |
| `notes` | string | Free text. |

---

## 3. `templates/water-consumption-log.csv`

Manual data-entry template. Identical columns to `sample-water-readings.csv`.
Use this when adding new readings by hand — do not modify the schema.

---

## 4. `scripts/output/validated-readings.csv`

Output of `scripts/data_validation.py`. Same columns as the input, plus:

| Added Column | Type | Description |
|---|---|---|
| `delta_m3` | decimal | Current cumulative reading minus previous valid cumulative reading for the same meter. Blank for the first reading or for flagged rows. |
| `flag` | string | One of: `MISSING_READINGS`, `DUPLICATE_TIMESTAMP`, `NEGATIVE_DELTA`, `ROLLOVER_SUSPECTED`, `POTENTIAL_ISSUE`. Blank when the reading passes all checks. |

---

## 5. `scripts/output/anomalies.csv`

Subset of `validated-readings.csv` containing only rows where `flag` is non-empty.
Use this file as the work-list for on-site investigation.

---

## 6. `scripts/output/daily-summary.csv`

Per-meter daily totals.

| Column | Type | Description |
|---|---|---|
| `meter_id` | string | Meter identifier. |
| `area` | string | Functional area. |
| `date` | date | Day of the reading, `YYYY-MM-DD`. |
| `consumption_m3` | decimal | Sum of valid `delta_m3` values for that meter on that date. |
| `target_m3` | decimal | Daily target for that meter (from `DAILY_TARGETS` in the script). |
| `variance_m3` | decimal | `consumption_m3 - target_m3`. Negative = under target. |

---

## 7. `scripts/output/weekly-summary.csv`

Per-meter ISO-week totals. Columns mirror the daily summary, with `iso_week`
(e.g., `(2024, 7)`) replacing `date`.

---

## 8. `scripts/output/monthly-summary.csv`

Per-meter monthly totals. `month` is `YYYY-MM` (e.g., `2024-07`).

---

## 9. Enumerations

### `flag` values

| Flag | Meaning | Action |
|---|---|---|
| `MISSING_READINGS` | Gap > 1 day between consecutive readings. | Verify whether readings were skipped, lost, or meter was offline. |
| `DUPLICATE_TIMESTAMP` | Two rows for the same meter at the same timestamp. | Determine which is correct; remove the duplicate from the source. |
| `NEGATIVE_DELTA` | Current reading is lower than the previous. | Investigate meter replacement, reset, or manual entry error. |
| `ROLLOVER_SUSPECTED` | Delta exceeds 50% of the rollover limit. | Verify rollover vs. actual high consumption. |
| `POTENTIAL_ISSUE` | Delta > 3x the 14-day rolling median. | Investigate on site. Do NOT classify as a leak without evidence. |

### `meter_type` values

- `cumulative` — The meter shows totalized volume. Consumption = current − previous.
- `flow` — The meter shows instantaneous flow rate. Consumption = reading × time interval. Not used in the sample dataset but supported by the schema.

---

## 10. Naming conventions

- **Meter IDs**: `MTR-<AREA-CODE>-<NNN>` (e.g., `MTR-DYE-001`).
- **Area codes**: 3-letter uppercase abbreviations (`DYE`, `WSH`, `BLR`, `CTW`, `PRC`, `DOM`).
- **Reading IDs**: `R<NNNNN>` (zero-padded, sequential after sort).
- **Date format**: ISO 8601 (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM`).

---

## 11. Anonymization rules

The dataset is fully anonymized:

- No real factory names, addresses, or contact details.
- No real operator names — only initials drawn from a synthetic pool (`AB`, `CD`, `EF`, `GH`, `IJ`, `KL`).
- No real meter serial numbers or manufacturer codes — the manufacturer/model columns in the templates are illustrative.
- Cumulative readings start at plausible but synthetic baseline values; do not infer historical plant consumption from these numbers.

When extending this repository with your own data, never commit raw
confidential factory readings. Use the `data/` directory only for anonymized
samples and keep real plant data in a private repository or local-only folder.
