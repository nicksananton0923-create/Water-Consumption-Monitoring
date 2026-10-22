# Dashboard Guide

This guide explains the three dashboard options shipped with the repository,
when to use each, and how to extend them.

| Option | File | Best for |
|---|---|---|
| **Excel dashboard** | `dashboard/water-dashboard.xlsx` | Single-user analysis, no install needed, works offline. |
| **Python dashboard** | `scripts/generate_dashboard.py` → `dashboard/python_dashboard.png` + `.html` | Reproducible pipelines, scheduled refresh, embedding in CI. |
| **Power BI dashboard** | See `dashboard/power-bi-build-guide.md` | Enterprise sharing, row-level security, scheduled refresh from SQL. |

---

## 1. Excel dashboard (`water-dashboard.xlsx`)

### Opening

Open the file in Microsoft Excel 2016+ or LibreOffice Calc 7+. The workbook
has 6 sheets:

1. **README** — quick start, sheet inventory, data source notes.
2. **Meter Register** — table of all 6 meters with metadata.
3. **Readings** — raw cumulative readings + live delta formula.
4. **Daily Summary** — per-meter daily consumption, target, variance, status.
5. **Monthly Summary** — per-meter monthly totals vs monthly target.
6. **Dashboard** — KPI strip + 3 native Excel charts.

### Adding new readings

1. Open the `Readings` sheet.
2. Scroll to the first empty row (after the last reading).
3. Paste your new rows preserving the column order: `reading_id, meter_id,
   area, equipment, reading_datetime, cumulative_reading, unit, meter_type,
   recorded_by, notes, Delta (m3)`.
4. For each new row, fill the `Delta (m3)` column with the formula:

   ```
   =IFERROR(IF(F{row}<F{prev_row},"NEGATIVE",ROUND(F{row}-F{prev_row},2)),"")
   ```

   where `prev_row` is the row number of the previous reading for the same
   meter. (You can copy the formula from the last existing row and Excel
   will adjust the cell references — but verify `prev_row` points to the
   right meter.)

5. The `Daily Summary` and `Monthly Summary` sheets use `SUMIFS` against
   the `Readings` sheet. They will update automatically when you add rows,
   provided your new rows fall inside the existing conditional-formatting
   range. If you add more than ~50 rows, extend the ranges via:
   `Formulas → Name Manager → extend each named range`.

6. The `Dashboard` sheet pulls from `Daily Summary`. The 3 native charts
   (`LineChart`, `BarChart`, `BarChart` col) will refresh when you save and
   reopen, or press `F9` to force recalculation.

### Refreshing from CSV

If you maintain raw data in CSV and want to refresh the Excel workbook:

1. Replace the contents of the `Readings` sheet (cells `B4:L{last_row}`)
   with a paste of your CSV contents.
2. The `Delta (m3)` formulas will rewrite to the new rows — re-copy the
   formula into each new row.
3. Save as `water-dashboard.xlsx`. Do not overwrite the original template
   shipped with the repository; save a copy under a different name (e.g.,
   `water-dashboard-2024-10.xlsx`).

### Limitations

- The workbook uses **static charts**. Adding new meters requires
  rebuilding the chart series via `Right-click → Select Data`.
- The dashboard does not auto-filter by date range. For date-range
  filtering, use the `Daily Summary` sheet's `AutoFilter` (Data → Filter).
- Excel for the web does not render the conditional-formatting data bars in
  the `Readings` sheet; use the desktop client for full fidelity.

---

## 2. Python dashboard (`python_dashboard.png` + `python_dashboard.html`)

### Prerequisites

```bash
pip install -r scripts/requirements.txt
```

`requirements.txt` pins `matplotlib` (for the PNG) and `plotly` (for the
interactive HTML).

### Pipeline

```bash
# 1. Validate raw data
python scripts/data_validation.py

# 2. Generate dashboards
python scripts/generate_dashboard.py
```

Outputs:

- `dashboard/python_dashboard.png` — 6-panel static dashboard image
  (KPIs + line + bar + column + anomalies table).
- `dashboard/python_dashboard.html` — interactive Plotly version with
  hover tooltips and zoom.

### Customizing the dashboard

Open `scripts/generate_dashboard.py` and edit:

- `CHART_COLORS` — palette (5 colors, hex strings).
- The `build_dashboard()` function — add new subplots, change chart types,
  add filters.
- The `DAILY_TARGETS` dictionary in `scripts/data_validation.py` —
  authorized per-meter targets.

### Scheduling the refresh

If your data is exported nightly to a CSV, schedule the pipeline with
cron (Linux) or Task Scheduler (Windows):

```cron
# /etc/cron.d/water-dashboard
0 7 * * * analyst cd /path/to/industrial-water-consumption-monitoring \
                && python scripts/data_validation.py \
                && python scripts/generate_dashboard.py \
                >> /var/log/water-dashboard.log 2>&1
```

This regenerates all outputs at 07:00 daily, after the night-shift meter
readings are uploaded.

### Embedding in GitHub README

The PNG is suitable for direct embedding:

```markdown
![Python Dashboard](dashboard/python_dashboard.png)
```

GitHub renders the image inline. The HTML file is interactive when
downloaded and opened locally, but GitHub does not render HTML inline —
link to it as a downloadable artifact.

---

## 3. Power BI dashboard (build guide)

See `dashboard/power-bi-build-guide.md` for the full step-by-step Power BI
Desktop build instructions. Key points:

- Source the validated CSVs (`scripts/output/*.csv`) as Power BI queries.
- Build a Star schema: `daily_summary` as the fact table; `meter_register`
  as a dimension.
- Use a date dimension (Power BI auto-generates one) for time intelligence.
- Apply the same KPI definitions as the Excel/Python dashboards.
- Publish to a Power BI workspace for team access; configure a daily refresh
  schedule pointing to the `scripts/output/` folder.

Power BI is recommended when you have multiple analysts who need to slice
the data interactively, when you want row-level security by area, or when
you want to embed the dashboard in Microsoft Teams.

---

## 4. Comparing the three options

| Dimension | Excel | Python | Power BI |
|---|---|---|---|
| Setup cost | None | `pip install` | Power BI Desktop + workspace |
| Refresh effort | Manual paste | Cron job | Scheduled refresh |
| Customization | Cell-level | Code-level | DAX + visuals |
| Interactivity | Filter + sort | Hover (HTML) | Full cross-filtering |
| Distribution | Email file | PNG/HTML embed | Power BI Service |
| Cost | Free | Free | Pro license per user |
| Best fit | Solo analyst | Pipeline / CI | Enterprise team |

---

## 5. KPI definitions (consistent across all 3 dashboards)

| KPI | Formula | Notes |
|---|---|---|
| Total Water Consumption | `Σ valid delta_m3` across all meters and dates | Includes all valid readings, regardless of target status. |
| Active Meters | `COUNT DISTINCT meter_id` in meter register with `status = 'active'` | Excludes decommissioned meters. |
| Anomalies Flagged | `COUNT rows WHERE flag != ''` | Count of investigation work-orders, not confirmed leaks. |
| Variance vs Target | `Σ (consumption − target) / Σ target` | Negative = under target (good). |
| Top-Consuming Meter | `argmax Σ delta_m3 by meter_id` | Reported in the bar chart. |
| Peak Day | `argmax daily_consumption across all meters and dates` | Reported in the line chart tooltip. |

---

## 6. Don't do this

- **Don't** hide flagged rows to make the dashboard "look clean". Anomalies
  are the most important information on the dashboard.
- **Don't** apply color scales to flagged deltas — the color encoding should
  be reserved for the Status column.
- **Don't** display "Confirmed Leaks" as a KPI. The pipeline does not
  confirm leaks; that classification requires on-site investigation.
- **Don't** publish a dashboard built from real plant data without
  anonymizing or removing confidential meter IDs.
