# Industrial Water Consumption Monitoring, Trend Analysis and Reporting Dashboard

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](scripts/requirements.txt)
[![Data: Anonymized](https://img.shields.io/badge/Data-Anonymized-1B7D46.svg)](#data-anonymization)
[![Status: Production-ready sample](https://img.shields.io/badge/Status-Production--ready_sample-1B2A4A.svg)](#what-has-and-has-not-been-tested)

A reusable, evidence-based system for recording, validating, analyzing,
and visualizing water consumption in an industrial or commercial facility.
Built around a textile-factory sample dataset with six cumulative water
meters observed daily across one full calendar year.

The repository is transport-agnostic (CSV in, CSV out), tool-agnostic
(Excel, Python, and Power BI dashboards all ship together), and
deliberately conservative in its claims: anomalies are flagged as
potential issues, never auto-classified as leaks.

---

## Table of contents

- [What this repository does](#what-this-repository-does)
- [Repository structure](#repository-structure)
- [Quickstart](#quickstart)
- [Sample dashboard preview](#sample-dashboard-preview)
- [Architecture](#architecture)
- [Validation rules](#validation-rules)
- [Calculation methodology](#calculation-methodology)
- [Data anonymization](#data-anonymization)
- [What has and has not been tested](#what-has-and-has-not-been-tested)
- [How to extend](#how-to-extend)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## What this repository does

1. **Records** raw cumulative water meter readings in a stable CSV schema
   (`data/sample-water-readings.csv`).
2. **Validates** each reading against five rules (schema, missing, duplicate,
   negative delta, rollover) plus a statistical spike test that flags
   consumption above 3× the meter's 14-day rolling median.
3. **Calculates** daily, weekly, and monthly consumption per meter and
   per area, with target-vs-actual variances.
4. **Visualizes** results in three parallel surfaces — Excel workbook,
   Python (matplotlib + Plotly), and a Power BI build guide — so the
   same data is consumable by solo analysts, pipeline operators, and
   enterprise BI teams.
5. **Documents** every formula, validation rule, wiring decision, and
   limitation in plain English so a new contributor can extend the system
   without re-deriving the design.

---

## Repository structure

```
industrial-water-consumption-monitoring/
├── README.md                          ← this file
├── LICENSE                            ← Apache 2.0
├── .gitignore
├── data/
│   └── sample-water-readings.csv       ← anonymized sample (2,219 rows)
├── templates/
│   ├── water-meter-register.csv         ← meter master list template
│   └── water-consumption-log.csv        ← manual entry template
├── scripts/
│   ├── data_validation.py               ← validation + aggregation pipeline
│   ├── generate_dashboard.py            ← matplotlib + Plotly dashboard
│   ├── output/                          ← generated CSVs (validation results)
│   │   ├── validated-readings.csv
│   │   ├── anomalies.csv
│   │   ├── daily-summary.csv
│   │   ├── weekly-summary.csv
│   │   ├── monthly-summary.csv
│   │   └── validation-report.txt
│   └── requirements.txt
├── dashboard/
│   ├── water-dashboard.xlsx             ← Excel dashboard (6 sheets)
│   ├── python_dashboard.png             ← static dashboard image
│   ├── python_dashboard.html            ← interactive Plotly dashboard
│   └── power-bi-build-guide.md          ← Power BI build instructions
├── diagrams/
│   ├── system-architecture.png + .mmd
│   ├── data-flow.png + .mmd
│   └── meter-schema.png + .mmd
└── docs/
    ├── data-dictionary.md               ← every column in every CSV
    ├── calculation-methodology.md        ← formulas + worked examples
    ├── data-validation.md                ← validation rules + how to extend
    ├── dashboard-guide.md               ← using all 3 dashboard surfaces
    ├── system-architecture.md            ← 5-layer system design
    ├── hardware-wiring.md               ← meter + logger wiring
    └── summary-report.md                ← 1-page management summary
```

---

## Quickstart

### Option A — Excel-only (no Python required)

1. Download or clone the repository.
2. Open `dashboard/water-dashboard.xlsx` in Microsoft Excel 2016+ or
   LibreOffice Calc 7+.
3. Start at the `README` sheet, then explore `Dashboard` for KPIs and
   charts, and `Readings` for the raw data.

### Option B — Full Python pipeline

```bash
# 1. Clone or extract the repository
cd industrial-water-consumption-monitoring/

# 2. (Optional) create a virtual environment
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r scripts/requirements.txt

# 4. Run the validation pipeline
python scripts/data_validation.py
# → outputs written to scripts/output/

# 5. Generate the Python dashboard
python scripts/generate_dashboard.py
# → outputs written to dashboard/python_dashboard.png + .html
```

### Option C — Power BI

Open Power BI Desktop and follow `dashboard/power-bi-build-guide.md` to
build a publishable report against the validated CSVs in
`scripts/output/`.

---

## Sample dashboard preview

### Python dashboard (PNG)

![Industrial Water Consumption Dashboard](dashboard/python_dashboard.png)

The Python dashboard shows:
- **KPI strip** — total consumption, meter count, total readings, anomaly count.
- **Daily consumption line chart** — top-3 meters over the year.
- **Monthly consumption by area** — column chart.
- **Total consumption by meter** — horizontal bar chart.
- **Anomalies table** — first 15 flagged rows.

The interactive HTML version (Plotly) adds hover tooltips and zoom.

### Excel dashboard

Open `dashboard/water-dashboard.xlsx` → `Dashboard` sheet for:

- 4-KPI strip with large-font values.
- Native Excel line chart (top 3 meters daily).
- Native Excel bar chart (total consumption by meter).
- Native Excel column chart (monthly consumption by area).

All charts are linked to the underlying sheets via formulas, so editing
the `Readings` sheet automatically refreshes the dashboard.

---

## Architecture

![System Architecture](diagrams/system-architecture.png)

The system follows a 5-layer model:

1. **Physical meters** — electromagnetic, ultrasonic, turbine, or
   mechanical flow meters in the field.
2. **Data acquisition** — local data logger or SCADA historian export
   producing CSV files matching the documented schema.
3. **Storage & validation** — Python pipeline that validates, computes
   deltas, and produces summary CSVs.
4. **Presentation** — Excel, Python (PNG + HTML), and Power BI dashboards.
5. **Stakeholders** — plant engineers, utilities manager, sustainability
   team, auditors.

Each layer has a documented data contract (CSV schema) so layers can be
swapped independently. For details, see
[`docs/system-architecture.md`](docs/system-architecture.md).

### Data flow

![Data Flow](diagrams/data-flow.png)

### Data schema

![Meter Schema](diagrams/meter-schema.png)

---

## Validation rules

The validation pipeline (`scripts/data_validation.py`) applies these
checks in order, per meter, on readings sorted by datetime:

| # | Rule | Flag | Action |
|---|---|---|---|
| 1 | Schema completeness | (hard exit) | Pipeline exits if any required column is missing |
| 2 | Duplicate timestamp | `DUPLICATE_TIMESTAMP` | Reviewer decides which (if any) is correct |
| 3 | Gap > 1 day | `MISSING_READINGS` | Reviewer checks for skipped readings |
| 4 | Current < previous | `NEGATIVE_DELTA` | Investigate meter reset / replacement / typo |
| 5 | Delta > 50% of rollover limit | `ROLLOVER_SUSPECTED` | Verify rollover vs. actual high consumption |
| 6 | Delta > 3× 14-day rolling median | `POTENTIAL_ISSUE` | On-site investigation required |

The pipeline never auto-corrects, never infers a leak, and never deletes
flagged rows. Flags are work-orders for human investigation. For the full
specification, see
[`docs/data-validation.md`](docs/data-validation.md).

---

## Calculation methodology

For cumulative meters:

```
delta_m3 = current_cumulative_reading − previous_cumulative_reading
```

Daily totals = sum of valid deltas per meter per day. Weekly = sum of
valid daily totals per ISO week. Monthly = sum per calendar month.

Variance vs target:

```
variance_m3 = consumption_m3 − target_m3
variance_pct = variance_m3 / target_m3
```

Status classification (used in the Excel `Daily Summary` sheet):

| Status | Condition |
|---|---|
| `NO DATA` | consumption = 0 |
| `OVER` | consumption > 1.5 × target |
| `HIGH` | consumption > 1.1 × target |
| `LOW` | consumption < 0.5 × target |
| `OK` | otherwise |

For worked examples, target validity rules, unit conversions, and what is
NOT computed by the pipeline, see
[`docs/calculation-methodology.md`](docs/calculation-methodology.md).

---

## Data anonymization

Every value in the sample dataset is synthetic:

- No real factory name, address, or contact details.
- No real operator names (only synthetic initials: `AB`, `CD`, `EF`, `GH`, `IJ`, `KL`).
- No real meter serial numbers or manufacturer codes (templates are illustrative).
- Cumulative readings start at plausible but synthetic baselines; do not
  infer historical plant consumption from these numbers.

When extending this repository with your own data, never commit raw
confidential factory readings. Use the `data/` directory only for
anonymized samples and keep real plant data in a private repository or
local-only folder.

---

## What has and has not been tested

### Tested

- The Python validation pipeline runs on the sample dataset and flags
  14 anomalies (1 missing, 1 duplicate, 1 negative, 1 rollover, 10
  potential issues).
- The Python dashboard generates both PNG and interactive HTML
  outputs.
- The Excel workbook opens in Excel 2016+ and LibreOffice Calc 7+;
  formulas evaluate correctly; charts render.
- All three architecture diagrams render as PNGs.
- All documentation cross-references resolve.

### Not tested

- Performance on datasets larger than ~2,200 rows (the sample size).
- Power BI workspace refresh (build guide only, no `.pbix` shipped).
- Live data acquisition from a real data logger.
- Mobile rendering of the Excel dashboard.

For the full self-assessment, see the
[Summary Report](docs/summary-report.md).

---

## How to extend

| Extension | What to change |
|---|---|
| Add a new meter | Add row to `templates/water-meter-register.csv`; add to `METERS` in `scripts/generate_sample_data.py` (sample) or the real source CSV (production) |
| Add a validation rule | Add function in `scripts/data_validation.py` `validate_and_compute()` |
| Add a KPI | Extend KPI strip in both `scripts/generate_dashboard.py` and `scripts/build_excel_dashboard.py` |
| Switch backend to a database | Replace CSV read/write in `data_validation.py` with SQL queries; keep validation rules unchanged |
| Add real-time streaming | Replace CSV step with Kafka/MQTT consumer; keep validation rules in the consumer |
| Add Tamil documentation | Copy each markdown to `*-ta.md` and translate; link from this README |

See [`docs/dashboard-guide.md`](docs/dashboard-guide.md) §5 and
[`docs/system-architecture.md`](docs/system-architecture.md) §6 for more
extension patterns.

---

## Documentation

| Document | Purpose |
|---|---|
| [Data Dictionary](docs/data-dictionary.md) | Every column in every CSV |
| [Calculation Methodology](docs/calculation-methodology.md) | Formulas + worked examples |
| [Data Validation](docs/data-validation.md) | Validation rules + how to extend |
| [Dashboard Guide](docs/dashboard-guide.md) | Using all 3 dashboard surfaces |
| [System Architecture](docs/system-architecture.md) | 5-layer system design |
| [Hardware Wiring](docs/hardware-wiring.md) | Meter + logger wiring guide |
| [Summary Report](docs/summary-report.md) | 1-page management summary |
| [Power BI Build Guide](dashboard/power-bi-build-guide.md) | Power BI step-by-step |

---

## Contributing

Contributions are welcome. Before opening a pull request:

1. Run `python scripts/data_validation.py` and confirm all existing
   flags still fire as documented.
2. Run `python scripts/generate_dashboard.py` and confirm both PNG and
   HTML render without errors.
3. Open `dashboard/water-dashboard.xlsx` and confirm no `#REF!` errors.
4. Do not commit real plant data. Anonymize all sample additions.
5. Preserve existing file paths and column names — many downstream
   consumers depend on them.

For major changes, please open an issue first to discuss the proposed
change of scope.

---

## License

Licensed under the Apache License, Version 2.0. See
[`LICENSE`](LICENSE) for the full text.

You are free to use, modify, distribute, and sublicense this work,
including for commercial purposes, provided you retain the copyright
notice and the license text. No warranty is expressed or implied.

---

## Author

Prepared by **industrial-utilities-analyst** (placeholder GitHub handle —
replace with your real GitHub username before publishing).

Roles assumed: Industrial Utilities Analyst, Water Consumption Monitoring
Specialist, Data Analyst, Excel Developer, Dashboard Designer, GitHub
Portfolio Mentor.

To customize for your own GitHub profile:

1. Find-and-replace `industrial-utilities-analyst` with your real handle
   across all files (or use `git filter-repo --mailmap` after the first
   commit to rewrite history cleanly).
2. Update the `Author` section above.
3. Update the footer of `docs/summary-report.md`.
4. Re-issue the LICENSE copyright line with your name and year.

---

## Acknowledgements

The repository structure, validation philosophy, and documentation
approach draw on standard industrial data-engineering practice. No
specific copyrighted source material was reproduced. The sample
dataset was generated synthetically with a fixed random seed for
reproducibility.
