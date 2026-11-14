"""CSV and PDF reports for a society, generated from the stored data (no figure is typed in by hand).

PDF charts are drawn with ReportLab's own graphics so the API image needs no plotting library.
CSV cells that could be read as spreadsheet formulas are neutralised.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

KINDS = ("monthly", "consumption", "forecast", "anomalies", "cost", "buildings")
INK, MUTED, ACCENT = colors.HexColor("#1f2933"), colors.HexColor("#52606d"), colors.HexColor("#0b6e4f")


def csv_safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def to_csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(x) for x in r])
    return buf.getvalue().encode("utf-8")


def _f(v, nd=2):
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else round(float(v), nd)


# ----------------------------------------------------------------------------- csv builders
def csv_consumption(df: pd.DataFrame) -> bytes:
    return to_csv(["period_start", "energy_kwh", "avg_kw", "peak_kw", "valid_hours", "expected_hours", "complete"],
                  [[str(t), _f(r.energy_kwh), _f(r.avg_kw), _f(r.peak_kw), int(r.valid_hours), int(r.expected_hours), bool(r.complete)] for t, r in df.iterrows()])


def csv_forecast(points: list[dict], origin: str, kind: str) -> bytes:
    if kind == "live":
        return to_csv(["origin", "target_time", "horizon_h", "forecast_kw", "lower_kw", "upper_kw", "model_family"],
                      [[origin, p["ts"], p["horizon"], _f(p["kw"]), _f(p["lower_kw"]), _f(p["upper_kw"]), p.get("family", "")] for p in points])
    return to_csv(["origin", "target_time", "horizon_h", "actual_kw", "predicted_kw", "lower_kw", "upper_kw", "baseline_kw"],
                  [[p["origin"], p["ts"], p["horizon"], _f(p["actual_kw"]), _f(p["predicted_kw"]), _f(p["lower_kw"]), _f(p["upper_kw"]), _f(p["baseline_kw"])] for p in points])


def csv_anomalies(events: list[dict]) -> bytes:
    return to_csv(["scope", "building", "severity", "start", "end", "hours", "types", "peak_time", "peak_kw", "expected_kw", "explanation"],
                  [[e["scope"], e.get("building") or "", e["severity"], e["start_ts"], e["end_ts"], e["hours"], "|".join(e["types"]), e["peak_ts"],
                    _f(e["peak_kw"]), _f(e["expected_kw"]), e["explanation"]] for e in events])


def csv_cost(report: dict) -> bytes:
    cur = report["tariff"]["currency"]
    return to_csv(["date", "energy_kwh", f"energy_cost_{cur}", f"total_cost_{cur}", "valid_hours", "estimate_not_a_bill"],
                  [[d["ts"][:10], d["energy_kwh"], d["energy_cost"], d["total_cost"], d["valid_hours"], "yes"] for d in report["daily"]])


def csv_buildings(rows: list[dict]) -> bytes:
    return to_csv(["building", "use", "floor_area_sqm", "energy_kwh", "share_pct", "kwh_per_sqm", "avg_kw", "peak_kw", "valid_hours", "expected_hours"],
                  [[b["code"], b["sub_use"], _f(b["floor_area_sqm"], 1), _f(b["energy_kwh"], 1), _f(b["share_pct"], 2), _f(b["kwh_per_sqm"], 2),
                    _f(b["avg_kw"], 1), _f(b["peak_kw"], 1), b["valid_hours"], b["expected_hours"]] for b in rows])


# ----------------------------------------------------------------------------- pdf
def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=20, textColor=INK, alignment=0, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=9.5, textColor=MUTED, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, textColor=ACCENT, spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontSize=9.5, leading=13, textColor=INK),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=8, leading=10.5, textColor=MUTED),
    }


def _table(data: list[list], widths: list[float], header: bool = True) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd2d9")), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4f1ec")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(st))
    return t


def _bar_chart(labels: list[str], values: list[float], title: str, width=170 * mm, height=55 * mm) -> Drawing:
    d = Drawing(width, height + 12)
    d.add(String(0, height + 2, title, fontSize=9, fillColor=INK))
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 38, 18, width - 46, height - 22
    bc.data = [values]
    bc.bars[0].fillColor = ACCENT
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.angle = 0
    n = len(labels)
    if n > 16:
        bc.categoryAxis.labels.fontSize = 0.1  # too many labels to read; the table below carries the dates
    d.add(bc)
    return d


def _line_chart(xs: list[float], series: list[tuple[str, list[float], colors.Color]], title: str, width=170 * mm, height=55 * mm) -> Drawing:
    d = Drawing(width, height + 12)
    d.add(String(0, height + 2, title, fontSize=9, fillColor=INK))
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 38, 18, width - 46, height - 22
    lp.data = [list(zip(xs, ys, strict=True)) for _, ys, _ in series]
    for i, (_, _, c) in enumerate(series):
        lp.lines[i].strokeColor = c
        lp.lines[i].strokeWidth = 1.4
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax, lp.xValueAxis.valueStep = 0, 23, 3
    lp.xValueAxis.labels.fontSize = lp.yValueAxis.labels.fontSize = 7
    d.add(lp)
    return d


def pdf_monthly(soc, period: tuple[pd.Timestamp, pd.Timestamp], series: pd.Series, buildings: list[dict], events: list[dict], cost: dict | None,
                peak: dict | None, accuracy: dict | None, generated_by: str) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{soc.name} report", author="EnergiQ AI")
    v = series.dropna()
    story = [Paragraph(f"{soc.name}", st["title"]),
             Paragraph(f"Electricity report for {period[0]:%d %b %Y} to {period[1]:%d %b %Y} &middot; generated {datetime.now():%Y-%m-%d %H:%M} by {generated_by}", st["sub"])]
    expected = len(series)
    peak_t = v.idxmax() if len(v) else None
    k = [["Energy used", f"{v.sum():,.0f} kWh"], ["Average demand", f"{v.mean():,.0f} kW"],
         ["Peak hourly demand", f"{v.max():,.0f} kW on {peak_t:%d %b %H:%M}" if peak_t is not None else "n/a"],
         ["Load factor (average / peak)", f"{v.mean() / v.max():.2f}" if len(v) else "n/a"],
         ["Hours with a valid society total", f"{len(v):,} of {expected:,} ({100 * len(v) / max(expected, 1):.1f}%)"]]
    if cost:
        k.append([f"Estimated energy cost ({cost['tariff']['currency']})", f"{cost['total']['total_cost']:,.0f}  (tariff: {cost['tariff']['name']}; an estimate, not a bill)"])
    story += [_table(k, [62 * mm, 108 * mm], header=False), Spacer(1, 6)]

    daily = v.resample("D").sum()
    if len(daily):
        labels = [f"{d:%d}" for d in daily.index]
        story.append(_bar_chart(labels, [float(x) for x in daily.values], "Daily energy (kWh)"))
    if peak:
        prof = peak["profile"]
        story.append(_line_chart([p["hour"] for p in prof], [("Weekday", [p["weekday_mean_kw"] for p in prof], ACCENT),
                                                              ("Weekend", [p["weekend_mean_kw"] for p in prof], colors.HexColor("#b45309"))],
                                 "Average demand by hour of day (kW): green weekday, orange weekend"))
    story.append(Paragraph("Buildings", st["h2"]))
    rows = [["Building", "Use", "Energy kWh", "Share %", "kWh / m2", "Peak kW"]]
    for b in sorted(buildings, key=lambda x: -(x["energy_kwh"] or 0))[:12]:
        rows.append([b["code"], b["sub_use"] or "", f"{b['energy_kwh']:,.0f}" if b["energy_kwh"] is not None else "n/a",
                     f"{b['share_pct']:.1f}" if b["share_pct"] is not None else "", f"{b['kwh_per_sqm']:.1f}" if b["kwh_per_sqm"] is not None else "",
                     f"{b['peak_kw']:,.0f}" if b["peak_kw"] is not None else ""])
    story.append(_table(rows, [24 * mm, 36 * mm, 30 * mm, 24 * mm, 26 * mm, 30 * mm]))
    story.append(Paragraph("Anomaly alerts (society level, medium and high severity)", st["h2"]))
    top = [e for e in events if e["scope"] == "society" and e["severity_level"] >= 2][:8]
    if top:
        rows = [["Start", "Severity", "Hours", "Peak kW", "Expected kW"]]
        for e in top:
            rows.append([str(e["start_ts"])[:16], e["severity"], e["hours"], f"{e['peak_kw']:,.0f}" if e["peak_kw"] else "", f"{e['expected_kw']:,.0f}" if e["expected_kw"] else ""])
        story.append(_table(rows, [42 * mm, 28 * mm, 22 * mm, 36 * mm, 42 * mm]))
    else:
        story.append(Paragraph("No medium or high severity society-level alerts in this period.", st["p"]))
    if accuracy:
        story.append(Paragraph("Forecast accuracy (held-out test period)", st["h2"]))
        rows = [["Horizon", "Model", "MAE kW", "MAPE %", "R2", "Baseline MAE kW"]]
        for h, r in accuracy.items():
            rows.append([f"{h} h", r["model"], f"{r['mae']:.1f}", f"{r['mape_pct']:.2f}", f"{r['r2']:.3f}", f"{r['baseline_mae']:.1f}"])
        story.append(_table(rows, [22 * mm, 40 * mm, 28 * mm, 26 * mm, 24 * mm, 30 * mm]))
    story += [Spacer(1, 8), Paragraph(
        "Data: measured hourly electricity meters from the Building Data Genome Project 2 (CC BY-SA 4.0), summed per hour over the retained residential buildings "
        f"of one site ({soc.name}). This is a research-based representative community, not a registered housing society. Missing or invalid meter hours are never "
        "filled: sums cover valid hours only. Cost figures use the tariff shown and are estimates, not utility bills.", st["small"])]
    doc.build(story)
    return buf.getvalue()
