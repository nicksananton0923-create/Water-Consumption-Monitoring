"""
Industrial Water Consumption — Python dashboard generator.

Reads the validated readings + summaries produced by data_validation.py
and renders a multi-panel PNG dashboard using matplotlib.

Outputs (in the same dir as this script, /output subfolder):
  - dashboard.png      : static dashboard image (great for GitHub README)
  - dashboard.html      : optional interactive Plotly dashboard (if plotly installed)

Usage:
  python generate_dashboard.py [--input-dir output] [--output dashboard.png]
"""

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime

# --- Matplotlib setup with font fallback (per project rules) -----------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
for p in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
]:
    if os.path.exists(p):
        fm.fontManager.addfont(p)

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Noto Sans SC"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 10

# Color palette (aligned with xlsx design system)
PRIMARY     = "#1B2A4A"
POSITIVE    = "#1B7D46"
WARNING     = "#D4820A"
NEGATIVE    = "#C0392B"
NEUTRAL_600 = "#8C8A84"
NEUTRAL_200 = "#E9E9E8"
NEUTRAL_100 = "#F7F7F5"

CHART_COLORS = [PRIMARY, POSITIVE, WARNING, NEGATIVE, NEUTRAL_600]


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def build_dashboard(input_dir, out_png, out_html=None):
    val_path = os.path.join(input_dir, "validated-readings.csv")
    daily_path = os.path.join(input_dir, "daily-summary.csv")
    monthly_path = os.path.join(input_dir, "monthly-summary.csv")
    anomalies_path = os.path.join(input_dir, "anomalies.csv")

    validated = load_csv(val_path)
    daily = load_csv(daily_path)
    monthly = load_csv(monthly_path)
    anomalies = load_csv(anomalies_path)

    # --- KPIs -----------------------------------------------------------------
    total_consumption = sum(float(r["consumption_m3"]) for r in daily)
    meter_count = len(set(r["meter_id"] for r in validated))
    anomaly_count = len(anomalies)

    # --- Daily consumption by meter (line chart) ------------------------------
    by_meter = defaultdict(list)
    for r in daily:
        by_meter[r["meter_id"]].append((parse_date(r["date"]),
                                         float(r["consumption_m3"])))
    fig, axes = plt.subplots(3, 2, figsize=(15, 11),
                             constrained_layout=True)
    # Title bar
    fig.suptitle("Industrial Water Consumption Monitoring Dashboard",
                 fontsize=16, fontweight="bold", color=PRIMARY)

    # KPI strip (top row, span both cols)
    kpi_ax = axes[0, 0]
    kpi_ax.axis("off")
    kpi_ax.text(0.0, 0.7, f"{total_consumption:,.0f}",
                fontsize=30, fontweight="bold", color=PRIMARY)
    kpi_ax.text(0.0, 0.35, "Total Water Consumption (m³)",
                fontsize=10, color=NEUTRAL_600)
    kpi_ax.text(0.0, 0.10, f"Across {meter_count} meters, "
                f"{len(set(r['area'] for r in validated))} areas",
                fontsize=9, color=NEUTRAL_600)

    kpi_ax2 = axes[0, 1]
    kpi_ax2.axis("off")
    kpi_ax2.text(0.0, 0.7, f"{anomaly_count}",
                 fontsize=30, fontweight="bold", color=WARNING)
    kpi_ax2.text(0.0, 0.35, "Anomalies Flagged (potential issues)",
                 fontsize=10, color=NEUTRAL_600)
    kpi_ax2.text(0.0, 0.10, "Requires on-site investigation before "
                 "classification. NOT confirmed leaks.",
                 fontsize=9, color=NEUTRAL_600)

    # Line chart: daily consumption per meter (axes[1, 0])
    ax1 = axes[1, 0]
    for i, (meter_id, pts) in enumerate(sorted(by_meter.items())):
        pts.sort()
        dates = [p[0] for p in pts]
        vals = [p[1] for p in pts]
        ax1.plot(dates, vals, color=CHART_COLORS[i % len(CHART_COLORS)],
                 linewidth=1.5, label=meter_id, alpha=0.85)
    ax1.set_title("Daily Water Consumption by Meter",
                  fontsize=12, fontweight="bold", color=PRIMARY, loc="left")
    ax1.set_ylabel("Consumption (m³)")
    ax1.set_xlabel("")
    ax1.grid(True, color=NEUTRAL_200, linewidth=0.5)
    ax1.legend(loc="upper left", fontsize=8, ncol=2, frameon=False)
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    # Bar chart: monthly consumption by area (axes[1, 1])
    ax2 = axes[1, 1]
    by_area_month = defaultdict(lambda: defaultdict(float))
    months_order = sorted(set(r["month"] for r in monthly))
    areas_order = sorted(set(r["area"] for r in monthly))
    for r in monthly:
        by_area_month[r["area"]][r["month"]] += float(r["consumption_m3"])
    width = 0.18
    x = list(range(len(months_order)))
    for i, area in enumerate(areas_order):
        vals = [by_area_month[area][m] for m in months_order]
        ax2.bar([xi + i*width for xi in x], vals, width,
                color=CHART_COLORS[i % len(CHART_COLORS)], label=area)
    ax2.set_xticks([xi + width*1.5 for xi in x])
    ax2.set_xticklabels(months_order, rotation=45, fontsize=8)
    ax2.set_title("Monthly Consumption by Area",
                  fontsize=12, fontweight="bold", color=PRIMARY, loc="left")
    ax2.set_ylabel("Consumption (m³)")
    ax2.legend(loc="upper left", fontsize=8, frameon=False)
    ax2.grid(True, axis="y", color=NEUTRAL_200, linewidth=0.5)

    # Top meters by total consumption (axes[2, 0])
    ax3 = axes[2, 0]
    totals_by_meter = defaultdict(float)
    for r in daily:
        totals_by_meter[r["meter_id"]] += float(r["consumption_m3"])
    sorted_totals = sorted(totals_by_meter.items(), key=lambda x: -x[1])
    meters = [m for m, _ in sorted_totals]
    vals = [v for _, v in sorted_totals]
    bars = ax3.barh(meters, vals, color=PRIMARY)
    ax3.set_title("Total Water Consumption by Meter",
                  fontsize=12, fontweight="bold", color=PRIMARY, loc="left")
    ax3.set_xlabel("Consumption (m³)")
    ax3.grid(True, axis="x", color=NEUTRAL_200, linewidth=0.5)
    ax3.invert_yaxis()
    # Add value labels
    for bar, v in zip(bars, vals):
        ax3.text(v + max(vals)*0.01, bar.get_y() + bar.get_height()/2,
                 f"{v:,.0f}", va="center", fontsize=8, color=NEUTRAL_600)

    # Anomalies table (axes[2, 1])
    ax4 = axes[2, 1]
    ax4.axis("off")
    ax4.set_title("Anomalies Flagged",
                  fontsize=12, fontweight="bold", color=PRIMARY, loc="left")
    if not anomalies:
        ax4.text(0.5, 0.5, "No anomalies flagged",
                 ha="center", va="center", fontsize=12, color=NEUTRAL_600)
    else:
        rows_to_show = anomalies[:10]
        table_data = [[a["meter_id"], a["reading_datetime"][:10],
                       a["flag"], a["delta_m3"]] for a in rows_to_show]
        col_labels = ["Meter ID", "Date", "Flag", "Delta (m³)"]
        tbl = ax4.table(cellText=table_data, colLabels=col_labels,
                        loc="upper center", cellLoc="left")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1.0, 1.4)
        # Color the flag column
        for i, row in enumerate(rows_to_show, start=1):
            color = (NEGATIVE if row["flag"] == "NEGATIVE_DELTA"
                     else WARNING if row["flag"] == "POTENTIAL_ISSUE"
                     else NEUTRAL_600)
            tbl[(i, 2)].set_text_props(color=color, fontweight="bold")

    # Footer
    fig.text(0.5, 0.005,
             "Sample anonymized dataset — textile factory. Anomalies are "
             "potential issues requiring on-site investigation, not "
             "confirmed leaks.",
             ha="center", fontsize=8, color=NEUTRAL_600)

    fig.savefig(out_png, dpi=140)
    print(f"Dashboard PNG written to {out_png}")

    # --- Optional interactive HTML dashboard (Plotly) -------------------------
    if out_html:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            print("Plotly not installed — skipping HTML dashboard.")
            return
        fig_p = make_subplots(rows=2, cols=2,
                              subplot_titles=("Daily Consumption by Meter",
                                              "Monthly Consumption by Area",
                                              "Top Meters by Total Consumption",
                                              "Anomalies"),
                              specs=[[{"type": "scatter"}, {"type": "bar"}],
                                     [{"type": "bar"}, {"type": "table"}]])
        for i, (meter_id, pts) in enumerate(sorted(by_meter.items())):
            pts.sort()
            fig_p.add_trace(go.Scatter(x=[p[0] for p in pts],
                                        y=[p[1] for p in pts],
                                        name=meter_id,
                                        line=dict(color=CHART_COLORS[i % 5])),
                            row=1, col=1)
        for i, area in enumerate(areas_order):
            fig_p.add_trace(go.Bar(x=months_order,
                                    y=[by_area_month[area][m] for m in months_order],
                                    name=area,
                                    marker_color=CHART_COLORS[i % 5]),
                            row=1, col=2)
        fig_p.add_trace(go.Bar(x=meters, y=vals, name="Total",
                                marker_color=PRIMARY), row=2, col=1)
        if anomalies:
            fig_p.add_trace(go.Table(
                header=dict(values=["Meter", "Date", "Flag", "Delta"],
                            fill_color=PRIMARY, font=dict(color="white")),
                cells=dict(values=[
                    [a["meter_id"] for a in anomalies[:15]],
                    [a["reading_datetime"][:10] for a in anomalies[:15]],
                    [a["flag"] for a in anomalies[:15]],
                    [a["delta_m3"] for a in anomalies[:15]],
                ])), row=2, col=2)
        fig_p.update_layout(title="Industrial Water Consumption Dashboard",
                            height=800, showlegend=True)
        fig_p.write_html(out_html)
        print(f"Dashboard HTML written to {out_html}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir",
                    default=os.path.join(os.path.dirname(__file__), "output"))
    ap.add_argument("--output",
                    default=os.path.join(os.path.dirname(__file__),
                                         "..", "dashboard",
                                         "python_dashboard.png"))
    ap.add_argument("--output-html",
                    default=os.path.join(os.path.dirname(__file__),
                                         "..", "dashboard",
                                         "python_dashboard.html"))
    args = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)

    build_dashboard(args.input_dir,
                    os.path.abspath(args.output),
                    os.path.abspath(args.output_html))


if __name__ == "__main__":
    main()
