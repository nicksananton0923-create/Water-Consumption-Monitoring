# System Architecture

This document describes the end-to-end architecture of the Industrial Water
Consumption Monitoring system, from physical meters to dashboard
consumers. It is the reference for anyone planning a deployment, extending
the pipeline, or doing capacity planning.

![System Architecture](../diagrams/system-architecture.png)

---

## 1. Five-layer model

The system follows a clean 5-layer separation. Each layer has a single
responsibility and a well-defined contract with the layers above and
below it.

### Layer 1 — Physical meters (field)

The flow-measurement devices installed in the plant. Each meter has a
unique `meter_id` recorded in the meter register and reports a cumulative
volume (`m3`) at a configured polling interval.

Typical meter technologies for a textile factory:

- **Electromagnetic flow meters** for clean water lines (dyeing, process).
- **Ultrasonic flow meters** for non-invasive measurement on existing
  pipework (cooling tower make-up, washing machine feeds).
- **Mechanical turbine meters** for boiler feed water and domestic supply
  (lower accuracy but proven reliability).

The sample dataset uses 6 meters, one per functional area:

| Meter ID | Area | Equipment | Typical range |
|---|---|---|---|
| MTR-DYE-001 | Dyeing Hall | Dyeing Line A | 30–80 m³/day |
| MTR-WSH-002 | Washing Hall | Washing Machine 3 | 20–40 m³/day |
| MTR-BLR-003 | Boiler House | Steam Boiler 1 | 12–25 m³/day |
| MTR-CTW-004 | Cooling Tower | Cooling Tower Cell 2 | 25–50 m³/day |
| MTR-PRC-005 | Process Hall | Process Water Main | 15–35 m³/day |
| MTR-DOM-006 | Utilities | Domestic Supply | 5–15 m³/day |

### Layer 2 — Data acquisition

The field gateway that polls meters and emits a structured CSV stream.
Two common architectures:

- **Local data logger** — A small embedded device (e.g., Advantech EKI,
  Moxa ioLogik) installed in the plant panel. Polls meters over RS-485
  MODBUS RTU or 4-20 mA analog inputs. Writes CSV files to an SD card or
  uploads them via FTP/HTTP at a configured interval. Resilient to
  network outages because it buffers locally.
- **Direct SCADA tag** — The plant's existing SCADA system already reads
  these meters for process control. A historian export (e.g., OSIsoft PI
  DataLink, Wonderware Active Factory) is scheduled nightly to dump the
  day's readings into the CSV format expected by the validation pipeline.

The repository is **transport-agnostic**: as long as the CSV file matches
the schema in `docs/data-dictionary.md`, the downstream layers work.

### Layer 3 — Storage and validation

A Python pipeline (`scripts/data_validation.py`) ingests the raw CSV,
applies schema and statistical checks, computes deltas, and produces
validated outputs in `scripts/output/`:

- `validated-readings.csv` — every reading with delta and flag columns.
- `anomalies.csv` — only flagged rows (the investigation work-list).
- `daily-summary.csv`, `weekly-summary.csv`, `monthly-summary.csv`.
- `validation-report.txt` — human-readable summary.

The pipeline is stateless: it reads the CSV, writes the outputs, exits.
Running it twice on the same input produces identical outputs (modulo the
random seed in the test data generator). It is safe to re-run after every
data refresh.

### Layer 4 — Presentation and reporting

Three presentation layers are supported in parallel:

- **Excel dashboard** (`dashboard/water-dashboard.xlsx`) — for solo
  analysis and offline review. No additional software required beyond
  Excel/LibreOffice.
- **Python dashboard** (`scripts/generate_dashboard.py`) — produces a
  static PNG and interactive Plotly HTML. Best for embedding in
  READMEs, CI pipelines, or scheduled emails.
- **Power BI dashboard** (build guide in
  `dashboard/power-bi-build-guide.md`) — for enterprise sharing with
  row-level security, scheduled refresh, and Teams integration.

All three consume the same validated CSVs and produce the same KPI
definitions (see `docs/dashboard-guide.md`), so results are consistent
across presentation surfaces.

### Layer 5 — Stakeholders

The dashboard is consumed by:

- **Plant engineers** — daily anomaly review, leak investigation
  work-orders.
- **Utilities manager** — weekly target-vs-actual review, variance
  escalation.
- **Sustainability team** — monthly KPI reporting, water intensity
  benchmarking (m³ per unit of production).
- **Auditors** — annual water-use audit, regulator compliance evidence.

---

## 2. Data contracts

Each arrow in the architecture diagram represents a data contract — a
documented schema that the producer and consumer agree on.

| Contract | Producer | Consumer | Schema |
|---|---|---|---|
| Raw readings | Logger / SCADA export | Validation pipeline | `data/sample-water-readings.csv` columns |
| Validated readings | Validation pipeline | Excel / Python / Power BI dashboards | `validated-readings.csv` columns |
| Summaries | Validation pipeline | All dashboards | `daily-summary.csv` etc. |
| Anomaly work-list | Validation pipeline | Plant engineers (investigation) | `anomalies.csv` columns |

The contracts are CSV files with stable column names and types. They are
versioned by the repository git history — any breaking change is a major
version bump documented in `CHANGELOG.md` (when present).

---

## 3. Failure modes and resilience

| Failure | Impact | Mitigation |
|---|---|---|
| Logger offline | No new raw readings arrive | Logger buffers locally; on recovery, back-fills the missing period |
| Network outage between logger and ingest server | Pipeline runs on stale data | Pipeline reports last-read timestamp; engineer reviews gap |
| Validation pipeline crashes | No validated outputs for that day | Cron job logs the error; rerun after fix; previous outputs remain valid |
| Dashboard file corruption | Excel file won't open | Restore from git history; CSVs are the source of truth |
| Meter failure (underreporting) | Daily total drops unexpectedly | `SUSTAINED_LOW` check flags it (see data-validation.md §5) |
| Meter failure (overcounting) | Daily total spikes | `POTENTIAL_ISSUE` spike check flags it |
| Operator miss-records reading | Negative delta or implausible value | `NEGATIVE_DELTA` flag; manual correction |

---

## 4. Security and confidentiality

- The repository holds only **anonymized sample data**. No real plant
  readings should ever be committed.
- The validation pipeline runs locally — no data leaves the host it
  runs on.
- For production deployments, store real readings in a private repository
  (or a private folder within this repository that is git-ignored) and
  keep the public repo for the schema, pipeline, and dashboard code.
- Operator initials in the sample data are synthetic. Replace with the
  plant's actual operator identification scheme in production.
- Meter serial numbers and manufacturer codes in `templates/water-meter-register.csv`
  are illustrative. Replace with real device identifiers only in the
  private copy.

---

## 5. Capacity planning

For a single plant with up to ~50 meters and daily readings:

- Raw CSV growth: ~50 rows/day = ~18,000 rows/year = ~2 MB/year.
- Validated CSVs: similar size plus 3 summary files at ~5x compression.
- Pipeline runtime: < 5 seconds on a laptop.
- Excel file: ~10 MB; opens in < 5 seconds.

For multi-plant or sub-daily polling (hourly readings):

- Use a real database (PostgreSQL, TimescaleDB) instead of CSVs.
- Add a `plant_id` column to every table and group by it in the
  dashboards.
- Move the dashboard to Power BI Service or a BI tool with row-level
  security.

The repository is intentionally scoped to the single-plant case. Extending
to multi-plant is a documented next step, not a hidden coupling — the
schema and pipeline are easy to fork per plant.

---

## 6. Where to extend

| You want to... | Modify... |
|---|---|
| Add a new meter | `templates/water-meter-register.csv` + add to `METERS` in `scripts/generate_sample_data.py` (or to the real source CSV in production) |
| Add a new validation rule | `scripts/data_validation.py` `validate_and_compute()` |
| Add a new KPI | `scripts/generate_dashboard.py` KPI strip + `scripts/build_excel_dashboard.py` `Dashboard` sheet |
| Switch the dashboard to a different tool | All consumers read from `scripts/output/` — write a new consumer (e.g., a Tableau workbook) that reads the same CSVs |
| Add real-time streaming | Replace the CSV step with a message queue (Kafka, MQTT) and a stream consumer that writes to a database; keep the validation rules in the consumer |
