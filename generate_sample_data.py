"""
Generate an anonymized sample water-readings dataset for a textile factory.

- 6 cumulative water meters across dyeing, washing, boiler, cooling tower,
  process water, and domestic utilities
- 1 year of daily cumulative readings (2024-01-01 .. 2024-12-31)
- ~2,190 base rows; plus a handful of intra-day hourly rows for the dyeing
  meter to demonstrate intra-day patterns and push the dataset toward ~3,000 rows
- Injects intentional anomalies (a spike, a missed reading, a meter rollover,
  a duplicate timestamp, a negative delta) so the validation + dashboard scripts
  have something meaningful to flag
- All meter IDs, location codes, and operator initials are anonymized
"""

import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "build",
                       "industrial-water-consumption-monitoring", "data")
OUT_DIR = os.path.abspath(OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)
OUT_CSV = os.path.join(OUT_DIR, "sample-water-readings.csv")

# --- Meter register (textile factory) ----------------------------------------
METERS = [
    # meter_id, area, equipment, unit, meter_type, install_date, rollover_limit
    ("MTR-DYE-001", "Dyeing Hall",   "Dyeing Line A",        "m3", "cumulative", "2022-03-15", 999999),
    ("MTR-WSH-002", "Washing Hall",  "Washing Machine 3",    "m3", "cumulative", "2022-04-10", 999999),
    ("MTR-BLR-003", "Boiler House",  "Steam Boiler 1",      "m3", "cumulative", "2021-11-20", 999999),
    ("MTR-CTW-004", "Cooling Tower",  "Cooling Tower Cell 2","m3", "cumulative", "2022-06-01", 999999),
    ("MTR-PRC-005", "Process Hall",  "Process Water Main",  "m3", "cumulative", "2022-01-08", 999999),
    ("MTR-DOM-006", "Utilities",     "Domestic Supply",    "m3", "cumulative", "2022-02-14", 999999),
]

# Daily base consumption per meter (m3/day) — realistic textile factory values
BASE_DAILY = {
    "MTR-DYE-001": 45.0,   # dyeing line, heavy consumer
    "MTR-WSH-002": 28.0,
    "MTR-BLR-003": 18.0,
    "MTR-CTW-004": 35.0,
    "MTR-PRC-005": 22.0,
    "MTR-DOM-006": 9.0,
}

# Seasonal multipliers (textile: high in summer due to cooling + processing)
def seasonal_factor(date):
    month = date.month
    # Sinusoidal: peak in July, trough in January
    return 1.0 + 0.18 * (1 - abs(month - 7) / 6.0)

# Weekly pattern: lighter on Sundays
def weekly_factor(date):
    return 0.55 if date.weekday() == 6 else (1.05 if date.weekday() < 5 else 0.85)

START = datetime(2024, 1, 1)
END   = datetime(2024, 12, 31)

rows = []
reading_id = 1

# Cumulative counter per meter — starts at a realistic "already-on-meter" value
cumulative = {
    "MTR-DYE-001": 124_350.0,
    "MTR-WSH-002":  88_120.0,
    "MTR-BLR-003":  55_640.0,
    "MTR-CTW-004":  72_980.0,
    "MTR-PRC-005":  41_500.0,
    "MTR-DOM-006":  18_260.0,
}

# Operators (anonymized initials)
OPERATORS = ["AB", "CD", "EF", "GH", "IJ", "KL"]

# --- Generate daily readings for every meter ---------------------------------
cur = START
while cur <= END:
    for meter_id, area, equipment, unit, mtype, install, rollover in METERS:
        # Inject a missed reading: skip MTR-BLR-003 on 2024-03-15
        if meter_id == "MTR-BLR-003" and cur == datetime(2024, 3, 15):
            continue

        daily = BASE_DAILY[meter_id]
        # Stochastic daily variation ±15%
        noise = random.uniform(0.85, 1.15)
        consumption = daily * seasonal_factor(cur) * weekly_factor(cur) * noise

        # Inject a spike on 2024-06-22 for dyeing (potential issue, not confirmed leak)
        if meter_id == "MTR-DYE-001" and cur == datetime(2024, 6, 22):
            consumption *= 2.6

        # Inject a meter rollover on 2024-08-10 for cooling tower
        if meter_id == "MTR-CTW-004" and cur == datetime(2024, 8, 10):
            cumulative[meter_id] = 5.0  # rollover to near-zero, then add day's use
        else:
            cumulative[meter_id] += round(consumption, 2)
            # Force rollover if exceeded limit
            if cumulative[meter_id] > rollover:
                cumulative[meter_id] = cumulative[meter_id] - rollover

        rows.append({
            "reading_id": f"R{reading_id:05d}",
            "meter_id": meter_id,
            "area": area,
            "equipment": equipment,
            "reading_datetime": cur.strftime("%Y-%m-%d 08:00"),
            "cumulative_reading": round(cumulative[meter_id], 2),
            "unit": unit,
            "meter_type": mtype,
            "recorded_by": random.choice(OPERATORS),
            "notes": "",
        })
        reading_id += 1
    cur = cur + timedelta(days=1)

# --- Inject a duplicate timestamp (same meter, same datetime) ----------------
# Find the row index of MTR-WSH-002 on 2024-05-10 and duplicate it
dup_target = None
for i, r in enumerate(rows):
    if r["meter_id"] == "MTR-WSH-002" and r["reading_datetime"] == "2024-05-10 08:00":
        dup_target = i
        break
if dup_target is not None:
    dup = dict(rows[dup_target])
    dup["reading_id"] = f"R{reading_id:05d}"
    dup["cumulative_reading"] = round(dup["cumulative_reading"] + 1.5, 2)  # off by 1.5 m3
    rows.insert(dup_target + 1, dup)
    reading_id += 1

# --- Inject an intra-day hourly block for the dyeing meter --------------------
# 2024-09-15 — 24 hourly readings to demonstrate intra-day granularity
hourly_base = datetime(2024, 9, 15)
day_start_cum = cumulative["MTR-DYE-001"]
# Remove the daily 08:00 row for that meter on that date (we already wrote it)
rows = [r for r in rows if not (r["meter_id"] == "MTR-DYE-001"
        and r["reading_datetime"] == "2024-09-15 08:00")]
for h in range(0, 24):
    dt = hourly_base + timedelta(hours=h)
    hourly_consumption = BASE_DAILY["MTR-DYE-001"] / 24.0 * random.uniform(0.8, 1.25)
    day_start_cum += round(hourly_consumption, 2)
    rows.append({
        "reading_id": f"R{reading_id:05d}",
        "meter_id": "MTR-DYE-001",
        "area": "Dyeing Hall",
        "equipment": "Dyeing Line A",
        "reading_datetime": dt.strftime("%Y-%m-%d %H:00"),
        "cumulative_reading": round(day_start_cum, 2),
        "unit": "m3",
        "meter_type": "cumulative",
        "recorded_by": random.choice(OPERATORS),
        "notes": "hourly batch" if h % 6 == 0 else "",
    })
    reading_id += 1
cumulative["MTR-DYE-001"] = day_start_cum

# --- Inject one negative-delta case (current < previous) for boiler ----------
# On 2024-11-05 manually set a reading lower than the previous day
for r in rows:
    if r["meter_id"] == "MTR-BLR-003" and r["reading_datetime"] == "2024-11-05 08:00":
        r["cumulative_reading"] = round(r["cumulative_reading"] - 50.0, 2)
        r["notes"] = "operator reports meter replaced - investigate"
        break

# --- Sort by meter_id then datetime so deltas are computable in order --------
rows.sort(key=lambda r: (r["meter_id"], r["reading_datetime"]))

# --- Re-assign reading_id sequentially after sort -----------------------------
for i, r in enumerate(rows, start=1):
    r["reading_id"] = f"R{i:05d}"

# --- Write CSV ----------------------------------------------------------------
fields = ["reading_id", "meter_id", "area", "equipment",
          "reading_datetime", "cumulative_reading", "unit",
          "meter_type", "recorded_by", "notes"]

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"OK: wrote {len(rows)} rows to {OUT_CSV}")
print(f"Meters: {len(METERS)} | Date range: {START.date()} to {END.date()}")
print("Injected anomalies: 1 missed reading, 1 duplicate timestamp, "
      "1 meter rollover, 1 negative delta, 1 consumption spike, "
      "24 hourly intra-day readings.")
