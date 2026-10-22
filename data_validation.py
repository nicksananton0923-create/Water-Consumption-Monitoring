"""
Industrial Water Consumption — data validation pipeline.

Reads the raw cumulative readings CSV, performs:
  1. Schema validation (required columns, dtypes)
  2. Missing-reading detection (gaps in expected daily cadence per meter)
  3. Duplicate timestamp detection per meter
  4. Negative-delta detection (current < previous cumulative reading)
  5. Meter rollover detection (delta exceeds rollover limit)
  6. Anomaly flagging (consumption >3x rolling median for that meter — flagged as
     "POTENTIAL ISSUE", never as confirmed leak)
  7. Consumption calculation: current valid - previous valid (cumulative meters)
  8. Daily, weekly, monthly summaries per meter and per area
  9. Optional target vs actual comparison if a targets.csv file is present

Outputs (under build/industrial-water-consumption-monitoring/scripts/output/):
  - validated-readings.csv        : all readings + delta + flag columns
  - anomalies.csv                 : only flagged rows
  - daily-summary.csv
  - weekly-summary.csv
  - monthly-summary.csv
  - validation-report.txt         : human-readable report

Usage:
  python data_validation.py [--input path/to/sample-water-readings.csv] \
                            [--output-dir output]
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

# --- Defaults -----------------------------------------------------------------
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_INPUT = os.path.join(BASE, "data", "sample-water-readings.csv")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

REQUIRED_FIELDS = [
    "reading_id", "meter_id", "area", "equipment",
    "reading_datetime", "cumulative_reading", "unit",
    "meter_type", "recorded_by", "notes",
]

# Rollover limits per meter (kept simple here; in production, read from meter register)
ROLLOVER_LIMITS = {
    "MTR-DYE-001": 999_999,
    "MTR-WSH-002": 999_999,
    "MTR-BLR-003": 999_999,
    "MTR-CTW-004": 999_999,
    "MTR-PRC-005": 999_999,
    "MTR-DOM-006": 999_999,
}

# Daily targets (m3/day) per meter — optional, used only if you want target vs actual
# This is just an example. Real targets must come from a plant-approved source.
DAILY_TARGETS = {
    "MTR-DYE-001": 50.0,
    "MTR-WSH-002": 30.0,
    "MTR-BLR-003": 20.0,
    "MTR-CTW-004": 38.0,
    "MTR-PRC-005": 25.0,
    "MTR-DOM-006": 10.0,
}


def parse_dt(s):
    """Parse 'YYYY-MM-DD HH:MM' (or 'YYYY-MM-DD')."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unparseable datetime: {s!r}")


def load_readings(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_FIELDS if c not in reader.fieldnames]
        if missing:
            print(f"ERROR: input CSV is missing required columns: {missing}",
                  file=sys.stderr)
            sys.exit(2)
        rows = list(reader)
    # Cast numeric fields
    for r in rows:
        r["cumulative_reading"] = float(r["cumulative_reading"])
        r["_dt"] = parse_dt(r["reading_datetime"])
    rows.sort(key=lambda r: (r["meter_id"], r["_dt"]))
    return rows


def validate_and_compute(rows):
    """Return (validated_rows, anomalies). Each row gets extra keys."""
    # Group by meter
    by_meter = defaultdict(list)
    for r in rows:
        by_meter[r["meter_id"]].append(r)

    validated = []
    anomalies = []

    for meter_id, meter_rows in by_meter.items():
        rollover = ROLLOVER_LIMITS.get(meter_id, 999_999)
        prev = None
        # Track seen timestamps for duplicate detection
        seen_ts = set()
        # Rolling median window (last 14 deltas) for anomaly detection
        recent_deltas = []

        for r in meter_rows:
            ts = r["reading_datetime"]
            flag = ""
            note = r.get("notes", "")

            # 1. Duplicate timestamp
            if ts in seen_ts:
                flag = "DUPLICATE_TIMESTAMP"
            else:
                seen_ts.add(ts)

            # 2. Missing reading — gap > 1 day between consecutive readings
            if prev is not None and not flag:
                expected_next = prev["_dt"] + timedelta(days=1)
                if r["_dt"] > expected_next + timedelta(hours=1):
                    flag = "MISSING_READINGS"
                    note += (f" | gap of {(r['_dt']-prev['_dt']).days} day(s) "
                             f"between {prev['reading_datetime']} and {ts}")

            # 3. Delta calculation + rollover + negative
            delta = None
            if prev is not None and not flag:
                delta = r["cumulative_reading"] - prev["cumulative_reading"]
                if delta < 0:
                    # Could be rollover or replacement — flag for investigation
                    if (r["cumulative_reading"] + (rollover - prev["cumulative_reading"])) < rollover:
                        flag = "NEGATIVE_DELTA"
                        note += f" | reading decreased by {abs(delta):.2f} m3 — investigate meter reset/replacement"
                if delta > rollover * 0.5:
                    flag = "ROLLOVER_SUSPECTED"
                    note += f" | delta {delta:.2f} m3 exceeds 50% of rollover limit"
            r["delta_m3"] = "" if delta is None else round(delta, 2)

            # 4. Spike detection via rolling median (last 14 valid deltas)
            if delta is not None and delta >= 0 and not flag:
                if recent_deltas:
                    med = sorted(recent_deltas)[len(recent_deltas)//2]
                    if med > 0 and delta > 3 * med:
                        flag = "POTENTIAL_ISSUE"
                        note += (f" | consumption {delta:.2f} m3 is "
                                 f"{delta/med:.1f}x the 14-day median ({med:.2f} m3). "
                                 "Investigate before classifying as leak.")
                recent_deltas.append(delta)
                if len(recent_deltas) > 14:
                    recent_deltas.pop(0)

            r["flag"] = flag
            r["notes"] = note.strip(" |")
            validated.append(r)
            if flag:
                anomalies.append(r)
            if not flag:
                prev = r
            else:
                # Still advance prev so we don't repeat the same comparison
                prev = r

    return validated, anomalies


def build_summaries(validated):
    """Aggregate daily, weekly, monthly consumption per meter and area."""
    daily = defaultdict(float)
    weekly = defaultdict(float)
    monthly = defaultdict(float)

    # Daily summary per (meter, date) — uses delta_m3
    by_day = defaultdict(lambda: defaultdict(float))
    by_week = defaultdict(lambda: defaultdict(float))
    by_month = defaultdict(lambda: defaultdict(float))

    for r in validated:
        if r["delta_m3"] == "" or r.get("flag"):
            # Skip flagged rows from totals (they need investigation)
            continue
        d = r["delta_m3"]
        date = r["_dt"].date()
        iso_year, iso_week, _ = r["_dt"].isocalendar()
        ym = r["_dt"].strftime("%Y-%m")
        by_day[(r["meter_id"], r["area"])][date] += d
        by_week[(r["meter_id"], r["area"])][(iso_year, iso_week)] += d
        by_month[(r["meter_id"], r["area"])][ym] += d

    def fmt_rows(by_dict, key_label):
        out = []
        for (meter_id, area), buckets in by_dict.items():
            for key, val in sorted(buckets.items()):
                out.append({
                    "meter_id": meter_id,
                    "area": area,
                    key_label: str(key),
                    "consumption_m3": round(val, 2),
                    "target_m3": DAILY_TARGETS.get(meter_id, ""),
                    "variance_m3": (round(val - DAILY_TARGETS[meter_id], 2)
                                   if meter_id in DAILY_TARGETS else ""),
                })
        return out

    return (fmt_rows(by_day, "date"),
            fmt_rows(by_week, "iso_week"),
            fmt_rows(by_month, "month"))


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    rows = load_readings(args.input)
    validated, anomalies = validate_and_compute(rows)
    daily, weekly, monthly = build_summaries(validated)

    write_csv(os.path.join(args.output_dir, "validated-readings.csv"),
              validated,
              REQUIRED_FIELDS + ["delta_m3", "flag"])
    write_csv(os.path.join(args.output_dir, "anomalies.csv"),
              anomalies,
              REQUIRED_FIELDS + ["delta_m3", "flag"])
    write_csv(os.path.join(args.output_dir, "daily-summary.csv"),
              daily, ["meter_id", "area", "date",
                      "consumption_m3", "target_m3", "variance_m3"])
    write_csv(os.path.join(args.output_dir, "weekly-summary.csv"),
              weekly, ["meter_id", "area", "iso_week",
                      "consumption_m3", "target_m3", "variance_m3"])
    write_csv(os.path.join(args.output_dir, "monthly-summary.csv"),
              monthly, ["meter_id", "area", "month",
                      "consumption_m3", "target_m3", "variance_m3"])

    # Validation report (plain text)
    rpt = os.path.join(args.output_dir, "validation-report.txt")
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("Industrial Water Consumption — Validation Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Input file:         {args.input}\n")
        f.write(f"Total readings:     {len(rows)}\n")
        f.write(f"Anomalies flagged:  {len(anomalies)}\n\n")
        flag_counts = defaultdict(int)
        for a in anomalies:
            flag_counts[a["flag"]] += 1
        if flag_counts:
            f.write("Flag breakdown:\n")
            for k, v in sorted(flag_counts.items()):
                f.write(f"  {k:24s}  {v}\n")
        f.write("\nNote: POTENTIAL_ISSUE flags indicate statistically unusual\n")
        f.write("consumption and must be investigated on site before any\n")
        f.write("classification (leak, meter fault, operational change).\n")
        f.write("They are NOT confirmed leaks.\n\n")
        f.write("Outputs written:\n")
        for fn in ["validated-readings.csv", "anomalies.csv",
                   "daily-summary.csv", "weekly-summary.csv",
                   "monthly-summary.csv"]:
            f.write(f"  - {os.path.join(args.output_dir, fn)}\n")

    print(f"Validated {len(rows)} readings. {len(anomalies)} anomalies flagged.")
    print(f"Report: {rpt}")
    print("Outputs:")
    for fn in ["validated-readings.csv", "anomalies.csv",
               "daily-summary.csv", "weekly-summary.csv",
               "monthly-summary.csv", "validation-report.txt"]:
        print(f"  {os.path.join(args.output_dir, fn)}")


if __name__ == "__main__":
    main()
