# Power BI Build Guide — Industrial Water Consumption Dashboard

This guide walks through building a Power BI Desktop report that consumes
the validated CSV outputs from this repository and reproduces the KPIs and
charts shipped in the Excel and Python dashboards.

Power BI Desktop is a free download from Microsoft. A Power BI Pro license
is required only for publishing to the Power BI Service and sharing with
other users.

---

## 1. Why Power BI (and when to choose it over Excel or Python)

Choose Power BI when:

- You need to share the dashboard with multiple analysts who will slice the
  data interactively (filter by area, meter, date range, flag type).
- You need row-level security (e.g., each plant manager sees only their
  plant's data).
- You want scheduled refresh from a database rather than manual CSV paste.
- You want to embed the dashboard in Microsoft Teams or SharePoint.

Choose Excel instead when:

- Only one or two analysts will use the dashboard.
- The dashboard is reviewed once a month and updated manually.
- You need pixel-perfect control over the layout.
- You don't want a Power BI Pro license.

Choose Python instead when:

- The dashboard is part of a CI/CD pipeline.
- The output needs to be embedded in a README or sent via email.
- You need reproducible, version-controlled dashboards.

---

## 2. Data sources

Power BI will read from these four CSV files in `scripts/output/`:

| File | Role in the model |
|---|---|
| `validated-readings.csv` | Fact table (one row per reading) |
| `daily-summary.csv` | Aggregated fact (one row per meter per day) |
| `monthly-summary.csv` | Aggregated fact (one row per meter per month) |
| `anomalies.csv` | Anomalies fact (subset of readings where flag is non-empty) |

Plus the dimension tables:

| File | Role |
|---|---|
| `templates/water-meter-register.csv` | Meter dimension (one row per meter) |
| `data/sample-water-readings.csv` | Reference / sample (do not import into Power BI; use `validated-readings.csv` instead) |

You will also create a date dimension in Power BI (see §4.3).

---

## 3. Step-by-step build in Power BI Desktop

### Step 1 — Import the CSV files

1. Open Power BI Desktop → **Get Data** → **Text/CSV**.
2. Browse to `scripts/output/daily-summary.csv` and click **Open**.
3. In the preview window, click **Transform Data** (do not click Load
   directly — you want to set types in Power Query first).
4. In Power Query Editor:
   - Set `consumption_m3` and `target_m3` to **Decimal Number** type.
   - Set `variance_m3` to **Decimal Number** type.
   - Set `date` to **Date** type.
   - Rename the query to `DailySummary`.
5. Repeat for `monthly-summary.csv` → query name `MonthlySummary`.
6. Repeat for `validated-readings.csv` → query name `Readings`. Set
   `cumulative_reading` and `delta_m3` (when present) to **Decimal Number**.
7. Repeat for `anomalies.csv` → query name `Anomalies`.
8. Import `templates/water-meter-register.csv` → query name `MeterRegister`.
   Set `install_date` and `calibration_due` to **Date** type. Set
   `rollover_limit` to **Whole Number**.
9. Click **Close & Apply** to load the tables into the model.

### Step 2 — Build the date dimension

1. **Modeling** tab → **New Table**.
2. Paste this DAX:

   ```dax
   DateDim = 
   ADDCOLUMNS(
       CALENDAR(MIN(DailySummary[date]), MAX(DailySummary[date])),
       "Year", YEAR([Date]),
       "Month", FORMAT([Date], "YYYY-MM"),
       "MonthName", FORMAT([Date], "MMM"),
       "ISOWeek", WEEKNUM([Date], 21),
       "DayOfWeek", WEEKDAY([Date], 2),
       "DayName", FORMAT([Date], "ddd")
   )
   ```

3. Mark the table as a Date Table: **Modeling** → **Mark as Date Table** →
   select the `Date` column.

### Step 3 — Set up relationships

In the **Model** view, drag to create these relationships:

| From (column) | To (column) | Cardinality |
|---|---|---|
| `MeterRegister.meter_id` | `DailySummary.meter_id` | 1:Many |
| `MeterRegister.meter_id` | `MonthlySummary.meter_id` | 1:Many |
| `MeterRegister.meter_id` | `Readings.meter_id` | 1:Many |
| `MeterRegister.meter_id` | `Anomalies.meter_id` | 1:Many |
| `DateDim.Date` | `DailySummary.date` | 1:Many |
| `DateDim.Date` | `Readings.reading_datetime` (date part) | 1:Many |

For the `Readings.reading_datetime` relationship, you may need to add a
calculated column `reading_date = DATEVALUE(Readings[reading_datetime])` in
Power Query first, since the source column is text.

Set the relationship direction to **Single** (one-to-many) for all
relationships except the date one, which can be **Single** as well.

### Step 4 — Create DAX measures

In the **Report** view, **Modeling** → **New Measure**:

```dax
Total Consumption (m3) = 
    SUM(DailySummary[consumption_m3])
```

```dax
Daily Target (m3) = 
    SUM(DailySummary[target_m3])
```

```dax
Variance (m3) = 
    [Total Consumption (m3)] - [Daily Target (m3)]
```

```dax
Variance % = 
    DIVIDE([Variance (m3)], [Daily Target (m3)], 0)
```

```dax
Active Meters = 
    CALCULATE(
        DISTINCTCOUNT(MeterRegister[meter_id]),
        MeterRegister[status] = "active"
    )
```

```dax
Total Readings = 
    COUNTROWS(Readings)
```

```dax
Anomalies Count = 
    COUNTROWS(Anomalies)
```

```dax
Top Meter by Consumption = 
    VAR TopMeter = TOPN(1, VALUES(MeterRegister[meter_id]),
                        CALCULATE([Total Consumption (m3)]), DESC)
    RETURN
    CALCULATE([Total Consumption (m3)], MeterRegister[meter_id] = TopMeter)
```

```dax
Peak Day Consumption = 
    MAXX(
        VALUES(DateDim[Date]),
        CALCULATE(SUM(DailySummary[consumption_m3]))
    )
```

```dax
Avg Daily Consumption = 
    AVERAGEX(
        VALUES(DateDim[Date]),
        CALCULATE(SUM(DailySummary[consumption_m3]))
    )
```

### Step 5 — Build the report pages

#### Page 1: Executive Dashboard

Layout:

- **Top row**: 4 KPI cards (use the built-in KPI visual):
  1. Total Water Consumption — Measure: `[Total Consumption (m3)]`
  2. Active Meters — Measure: `[Active Meters]`
  3. Total Readings — Measure: `[Total Readings]`
  4. Anomalies Flagged — Measure: `[Anomalies Count]`
- **Middle row**: Line chart of daily consumption by meter
  - X-axis: `DateDim[Date]`
  - Y-axis: `DailySummary[consumption_m3]`
  - Legend: `MeterRegister[meter_id]`
- **Bottom row (left)**: Bar chart — total consumption by meter
  - X-axis: `MeterRegister[meter_id]`
  - Y-axis: `[Total Consumption (m3)]`
- **Bottom row (right)**: Column chart — monthly consumption by area
  - X-axis: `DateDim[Month]`
  - Y-axis: `[Total Consumption (m3)]`
  - Legend: `MeterRegister[area]`

#### Page 2: Anomaly Investigation

- Table visual:
  - Columns: `Anomalies[reading_id]`, `Anomalies[meter_id]`,
    `Anomalies[reading_datetime]`, `Anomalies[flag]`,
    `Anomalies[delta_m3]`, `Anomalies[notes]`
  - Filter to show all flagged rows.
- Slicers:
  - `Anomalies[flag]` (multi-select dropdown)
  - `Anomalies[meter_id]` (dropdown)
  - `DateDim[Month]` (dropdown)
- Conditional formatting on `Anomalies[flag]`:
  - `NEGATIVE_DELTA` → red background
  - `POTENTIAL_ISSUE` → amber background
  - `MISSING_READINGS` → light blue background
  - `DUPLICATE_TIMESTAMP` → light gray background
  - `ROLLOVER_SUSPECTED` → orange background

#### Page 3: Target vs Actual

- Matrix visual:
  - Rows: `MeterRegister[meter_id]` → `MeterRegister[area]`
  - Columns: `DateDim[Month]`
  - Values: `[Total Consumption (m3)]`, `[Daily Target (m3)]`,
    `[Variance (m3)]`, `[Variance %]`
- Conditional formatting on `Variance %`:
  - Color scale: red (>10%) → white (0%) → green (<-10%)
- A "drill-through" button to navigate from a matrix cell to the
  underlying `Readings` rows for that meter-month.

#### Page 4: Meter Register

- Table visual with all columns from `MeterRegister`.
- Slicer on `MeterRegister[status]` (active / decommissioned /
  out_for_calibration).
- Conditional formatting on `MeterRegister[calibration_due]`:
  - If `calibration_due < TODAY()` → red background, "Overdue" label.
  - If `calibration_due < TODAY() + 30` → amber background.
  - Otherwise → green background.

### Step 6 — Configure refresh

For a CSV-based source, Power BI Desktop handles refresh on file open.
For scheduled refresh in the Power BI Service:

1. Publish the report to a workspace.
2. In the workspace, **Settings** → **Datasets** → **Scheduled Refresh**.
3. Configure a daily refresh time (e.g., 07:30 — after the nightly
   validation pipeline writes new CSVs).
4. For on-premises CSV sources, install the **On-premises data gateway**
   and register the folder containing `scripts/output/`.

### Step 7 — Add a date-range slicer

On each report page, add a **Date** slicer bound to `DateDim[Date]`. Set
the slicer type to **Between** so users can filter the entire page by date
range. Power BI's date hierarchy lets users drill from year → quarter →
month → day.

---

## 4. Visual design tips

- Use a 3-color discipline: a single primary color (deep blue, `#1B2A4A`)
  for headers and key KPIs; accent colors (green `#1B7D46`, amber `#D4820A`,
  red `#C0392B`) for status indicators; warm neutrals for body text.
- Avoid 3D charts. Use 2D bars and lines for accurate reading.
- Add a "Data as of" text box on every page that reads `=MAX(DateDim[Date])`
  so users know the freshness of the data.
- Add a "Source: Anonymized sample data" disclaimer on every page in 9pt
  gray text.
- Reserve red exclusively for negative variance and confirmed anomalies
  requiring action. Never use red for "highlight" or "emphasis".

---

## 5. Row-level security (RLS)

If you deploy this to multiple plants and want each plant manager to see
only their own data:

1. Add a `plant_id` column to `MeterRegister` and to all fact tables.
2. In Power BI Desktop, **Modeling** → **Manage Roles** → **New**:
   ```dax
   PlantManagerRole = 
   MeterRegister[plant_id] = USERNAME()
   ```
   (Replace `USERNAME()` with whatever mapping fits your org — typically
   you'll have a separate `UserPlant` table mapping email to `plant_id`.)
3. Test with **Test as Role** before publishing.
4. In the Power BI Service, **Security** for the dataset → assign
   users/groups to the role.

---

## 6. Calculations Power BI does NOT replicate

These calculations exist only in the Python validation pipeline and
must NOT be re-implemented in DAX without reproducing the same logic
exactly:

- The 14-day rolling median used for spike detection. DAX does not have
  a built-in median-over-window function. Re-implementing requires a
  complex iterator that is brittle and slow. Use the `Anomalies` table
  directly — it already contains the flags.
- The rollover detection (`delta > 50% of rollover_limit`). Use the
  `Anomalies` table; do not recompute from `Readings`.
- The missing-readings gap detection. Same — use the `Anomalies` table.

The principle: **the validation pipeline is the single source of truth
for flag computation**. Power BI is the presentation layer; it consumes
flags, it does not generate them.

---

## 7. Publishing and sharing

1. **Publish**: In Power BI Desktop, **Home** → **Publish** → select the
   workspace.
2. **Share**: In the Power BI Service, open the report → **File** →
   **Share** → enter user emails. Recipients need a Power BI Pro
   license (or a Premium-per-user license).
3. **Embed in Teams**: In Teams, add the **Power BI** tab to any channel,
   select the report. Members of the channel with Pro licenses can
   interact with the dashboard without leaving Teams.
4. **Embed in SharePoint**: Use the Power BI web part in a SharePoint
   modern page. Same Pro license requirement.

---

## 8. Version control

Power BI `.pbix` files are binary and do not diff cleanly in git. Two
practical options:

- **Don't commit `.pbix` files**. Keep them in a SharePoint library or
  OneDrive for Business. Document the build steps in this guide so a
  new contributor can rebuild the report from the CSVs.
- **Use Power BI Desktop's "Template" (.pbit) format**. A `.pbit` is a
  text-based template that prompts for the data source path on open.
  Commit `.pbit` files; treat the `.pbix` as a build artifact.

This repository does NOT ship a `.pbix` or `.pbit` file. The
documentation is sufficient for a Power BI developer to rebuild the
report from the validated CSVs in under an hour.

---

## 9. Performance considerations

With the sample dataset (~2,200 readings, ~2,200 daily summary rows),
Power BI's import mode is fine. For larger datasets:

- Switch `DailySummary` to **DirectQuery** if your source is a database.
- Keep `MeterRegister` and `DateDim` in import mode (small dimensions
  benefit from in-memory caching).
- Avoid the `Readings` table in visuals unless you truly need
  per-reading detail — it's the largest table and slows down rendering.

For datasets over 100,000 rows, consider pushing the validation pipeline
into a SQL stored procedure and using DirectQuery against the result
view rather than importing flat CSVs.

---

## 10. Common pitfalls

| Pitfall | Fix |
|---|---|
| Date column imported as text, breaks time intelligence | In Power Query, set the column to **Date** type before loading. |
| `variance_pct` shows as 12.4 instead of 12.4% | In the Fields pane, select the measure → **Modeling** → set Format to **Percentage** with 1 decimal. |
| KPI card shows "Blank" for Anomaly count | Verify the `Anomalies` query loaded rows; verify the measure references the right table. |
| Date slicer shows future dates | Set the slicer's **Visual** → **Settings** → turn on **Show items with no data = false** and set an upper bound. |
| Cross-filtering between pages doesn't work | Use **Edit interactions** in the Format pane to enable cross-filtering between the slicer and the visual. |
| Refresh fails in the Service | On-premises gateway not running, or the gateway service account doesn't have read access to the CSV folder. |
| Variance calculation diverges from the Python pipeline | Check that the DAX measure's filter context matches the pipeline's `WHERE` clause; the pipeline filters flagged rows out, your DAX may not. |

For any divergence between the Python pipeline output and the Power BI
numbers, the Python pipeline is the source of truth. Adjust the DAX to
match.
