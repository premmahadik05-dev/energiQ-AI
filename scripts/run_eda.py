"""Phase 2 exploratory data analysis for EnergiQ AI.

Reads the raw 1-minute file (chunked), builds the hourly series with the
45-valid-minutes rule, and writes figures plus a machine-readable stats file.
Every number comes from the real data; nothing is estimated or invented.

Usage (Windows or Linux), from the repository root:
    python scripts/run_eda.py --input data/raw/uci_household_power/household_power_consumption.txt --outdir artifacts/reports/eda
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml_engine.data.loading import read_minute_data, to_hourly  # noqa: E402

# ---- design tokens (validated palette, light mode; see docs/04_eda_report.md) ----
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
NEUTRAL = "#b9b8b0"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQ)

MIN_DAY_MINUTES = 1368  # 95% of 1440
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

SPLITS = {  # proposal from docs/01_dataset_suitability.md section 9
    "train": ("2006-12-16 00:00", "2009-06-30 23:00"),
    "validation": ("2009-07-01 00:00", "2009-12-31 23:00"),
    "test": ("2010-01-01 00:00", "2010-11-26 23:00"),
}


def setup_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
            "font.size": 10,
            "text.color": INK2,
            "axes.labelcolor": INK2,
            "xtick.color": INK2,
            "ytick.color": INK2,
            "axes.edgecolor": AXIS,
            "axes.titlecolor": INK,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "lines.solid_capstyle": "round",
            "figure.dpi": 100,
            "savefig.dpi": 150,
        }
    )


def y_grid_only(ax) -> None:
    ax.grid(axis="x", visible=False)


def save(fig, outdir: Path, name: str) -> str:
    path = outdir / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return name


def run_lengths(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if mask.size == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    padded = np.concatenate(([0], mask.astype(np.int8), [0]))
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return starts, ends - starts


def acf_with_gaps(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Autocorrelation using only index pairs where both values exist."""
    mean = np.nanmean(x)
    d = x - mean
    out = np.full(max_lag + 1, np.nan)
    var = np.nanmean(d * d)
    for lag in range(max_lag + 1):
        a, b = d[: len(d) - lag], d[lag:]
        ok = ~np.isnan(a) & ~np.isnan(b)
        out[lag] = np.mean(a[ok] * b[ok]) / var if ok.sum() > 0 else np.nan
    return out


def last_sunday(year: int, month: int) -> pd.Timestamp:
    d = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
    while d.day_of_week != 6:
        d -= pd.Timedelta(days=1)
    return d.normalize()


def best_shift(pre: np.ndarray, post: np.ndarray, max_bins: int = 18) -> tuple[int, float, float]:
    """Shift (minutes, + = later) s.t. post(t) ~ pre(t - shift); also corr at shift 0."""
    best_k, best_r = 0, -2.0
    for k in range(-max_bins, max_bins + 1):
        r = np.corrcoef(np.roll(pre, k), post)[0, 1]
        if r > best_r:
            best_k, best_r = k, r
    r0 = np.corrcoef(pre, post)[0, 1]
    return best_k * 10, float(best_r), float(r0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    setup_style()

    df = read_minute_data(args.input)
    gap = df["Global_active_power"].astype("float64")
    hourly = to_hourly(df)
    hv = hourly["value"]
    stats: dict = {}
    figs: dict[str, str] = {}

    # ------------------------------------------------------------------ daily
    d = gap.resample("1D").agg(["mean", "count"])
    d["missing_min"] = gap.isna().resample("1D").sum()
    d["ok"] = d["count"] >= MIN_DAY_MINUTES
    d["kwh"] = d["mean"] * 24
    ok_days = d[d["ok"]]

    # long missing blocks (> 1 day), for shading
    miss_mask = gap.isna().to_numpy()
    s_idx, s_len = run_lengths(miss_mask)
    long_blocks = [
        (gap.index[s], gap.index[s + n - 1]) for s, n in zip(s_idx, s_len) if n > 1440
    ]

    # ---- fig 1: daily overview + missing minutes per day
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1.3], "hspace": 0.12})
    for s_, e_ in long_blocks:
        a1.axvspan(s_, e_, color=NEUTRAL, alpha=0.35, lw=0)
    a1.plot(d.index, d["mean"], color=BLUE, lw=0.9)
    a1.set_ylabel("Mean load (kW)")
    a1.set_title("Daily mean household load, Dec 2006 – Nov 2010")
    y_grid_only(a1)
    a1.text(0.99, 0.96, "Grey bands: missing blocks longer than 1 day", transform=a1.transAxes, ha="right", va="top", fontsize=8.5, color=INK2)
    a2.bar(d.index, d["missing_min"], width=1.0, color=ORANGE, lw=0)
    a2.set_ylabel("Missing\nminutes / day")
    a2.set_ylim(0, 1440)
    y_grid_only(a2)
    figs["fig01"] = save(fig, args.outdir, "fig01_daily_overview.png")

    # ---------------------------------------------------- hourly profile
    hh = pd.DataFrame({"v": hv})
    hh["hour"] = hh.index.hour
    hh["dow"] = hh.index.day_of_week
    hh["weekend"] = hh["dow"] >= 5
    hh["month"] = hh.index.month
    hh["year"] = hh.index.year

    prof = hh.groupby(["weekend", "hour"])["v"].mean().unstack(0)  # columns False/True
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(prof.index, prof[False], color=BLUE, lw=2, marker="o", ms=4, mfc=SURFACE, mew=1.5)
    ax.plot(prof.index, prof[True], color=ORANGE, lw=2, marker="o", ms=4, mfc=SURFACE, mew=1.5)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlabel("Hour of day (logger clock)")
    ax.set_ylabel("Mean hourly load (kW)")
    ax.set_title("Average daily load profile: weekdays vs weekends")
    ax.text(6.7, prof[False].iloc[7] + 0.07, "Weekdays", color=INK2, fontsize=9, ha="right", va="center")
    ax.text(19.5, prof[True].max() + 0.09, "Weekends", color=INK2, fontsize=9, ha="center", va="center")
    ax.set_ylim(0.3, 2.3)
    ax.legend(handles=[plt.Line2D([], [], color=BLUE, lw=2, label="Weekdays (Mon–Fri)"), plt.Line2D([], [], color=ORANGE, lw=2, label="Weekends (Sat–Sun)")], loc="upper left")
    y_grid_only(ax)
    figs["fig02"] = save(fig, args.outdir, "fig02_daily_profile.png")

    # ---------------------------------------------------- weekly heatmap
    heat = hh.pivot_table(index="dow", columns="hour", values="v", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(10, 3.6))
    im = ax.pcolormesh(np.arange(25), np.arange(8), heat.to_numpy(), cmap=SEQ_CMAP, shading="flat")
    ax.set_yticks(np.arange(7) + 0.5, DAY_NAMES)
    ax.set_xticks(np.arange(0, 24, 3) + 0.5, [str(h) for h in range(0, 24, 3)])
    ax.invert_yaxis()
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("Hour of day (logger clock)")
    ax.set_title("Mean hourly load by weekday and hour")
    cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.03)
    cb.set_label("kW")
    cb.outline.set_visible(False)
    figs["fig03"] = save(fig, args.outdir, "fig03_weekly_heatmap.png")

    # ---------------------------------------------------- monthly seasonality
    ok_days = ok_days.copy()
    ok_days["year"] = ok_days.index.year
    ok_days["month"] = ok_days.index.month
    mon = ok_days.groupby(["year", "month"])["kwh"].agg(["mean", "count"])
    mon.loc[mon["count"] < 15, "mean"] = np.nan  # too few valid days to trust
    month_tbl = mon["mean"].unstack(0)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    year_colors = {2007: BLUE, 2008: ORANGE, 2009: AQUA, 2010: YELLOW}
    for yr, col in year_colors.items():
        s = month_tbl[yr]
        ax.plot(s.index, s.values, color=col, lw=2, marker="o", ms=4, mfc=SURFACE, mew=1.5)
        last = s.dropna()
        ax.text(last.index[-1] + 0.15, last.iloc[-1], str(yr), color=INK2, fontsize=9, va="center")
    ax.set_xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_xlim(0.7, 12.9)
    ax.set_ylabel("Mean daily energy (kWh/day)")
    ax.set_title("Monthly seasonality by year (days with at least 95% valid minutes)")
    aug08 = month_tbl.loc[8, 2008]
    ax.text(8.15, aug08, "Aug 2008: unusually low use", color=INK2, fontsize=8.5, va="center", ha="left")
    ax.legend(handles=[plt.Line2D([], [], color=c, lw=2, label=str(y)) for y, c in year_colors.items()], loc="upper center", ncol=4)
    y_grid_only(ax)
    figs["fig04"] = save(fig, args.outdir, "fig04_monthly_seasonality.png")

    # ---------------------------------------------------- autocorrelation
    max_lag = 8 * 24
    acf = acf_with_gaps(hv.to_numpy(), max_lag)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.vlines(np.arange(1, max_lag + 1), 0, acf[1:], color=BLUE, lw=1.4)
    ax.axhline(0, color=AXIS, lw=1)
    for lag in (24, 48, 72, 96, 120, 144, 168):
        ax.axvline(lag, color=GRID, lw=0.8, zorder=0)
    for lag, dx, dy in ((1, 4, -0.02), (24, 4, 0.03), (168, 4, 0.03)):
        ax.annotate(f"lag {lag}: {acf[lag]:.2f}", (lag, acf[lag]), xytext=(lag + dx, acf[lag] + dy), fontsize=9, color=INK2)
    ax.set_ylim(-0.1, 0.8)
    ax.set_xticks(range(0, max_lag + 1, 24))
    ax.set_xlabel("Lag (hours)")
    ax.set_ylabel("Autocorrelation")
    ax.set_title("Autocorrelation of hourly load (vertical guides every 24 h)")
    y_grid_only(ax)
    figs["fig05"] = save(fig, args.outdir, "fig05_autocorrelation.png")

    # ---------------------------------------------------- distribution
    vals = hv.dropna().to_numpy()
    fig, ax = plt.subplots(figsize=(10, 4))
    upper = float(np.percentile(vals, 99.9))
    ax.hist(vals, bins=70, range=(0, upper), color=BLUE, edgecolor=SURFACE, lw=0.6)
    med, p95 = float(np.median(vals)), float(np.percentile(vals, 95))
    for x, lab in ((med, f"median {med:.2f} kW"), (p95, f"95th pct {p95:.2f} kW")):
        ax.axvline(x, color=INK2, lw=1, ls=(0, (4, 3)))
        ax.text(x + 0.05, ax.get_ylim()[1] * 0.92, lab, fontsize=9, color=INK2, va="top")
    ax.set_xlabel("Hourly mean load (kW)")
    ax.set_ylabel("Number of hours")
    ax.set_title("Distribution of hourly load (right-skewed)")
    y_grid_only(ax)
    figs["fig06"] = save(fig, args.outdir, "fig06_distribution.png")

    # ---------------------------------------------------- sub-meter mix
    comp = pd.DataFrame(
        {
            "Kitchen (sub-meter 1)": df["Sub_metering_1"].astype("float64") * 0.06,
            "Laundry (sub-meter 2)": df["Sub_metering_2"].astype("float64") * 0.06,
            "Water heater / AC (sub-meter 3)": df["Sub_metering_3"].astype("float64") * 0.06,
        }
    )
    comp["Not sub-metered"] = gap - comp.sum(axis=1, min_count=3)
    comp = comp.dropna()
    cm = comp.resample("MS").mean()
    share = float(comp["Not sub-metered"].sum() / gap.dropna().sum())
    stats["unmetered_share_of_active_energy"] = round(share, 4)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    bottom = np.zeros(len(cm))
    colors = [BLUE, ORANGE, AQUA, NEUTRAL]
    x = np.arange(len(cm))
    for (name, col), c in zip(cm.items(), colors):
        ax.bar(x, col.to_numpy(), bottom=bottom, width=0.85, color=c, edgecolor=SURFACE, lw=0.6, label=name)
        bottom += col.to_numpy()
    ticks = [i for i, ts_ in enumerate(cm.index) if ts_.month in (1, 7)]
    ax.set_xticks(ticks, [cm.index[i].strftime("%b %Y") for i in ticks])
    ax.set_ylabel("Mean load (kW)")
    ax.set_title("Where measured energy goes: sub-metered vs not sub-metered, by month")
    ax.legend(loc="upper center", ncol=4, bbox_to_anchor=(0.5, -0.1))
    y_grid_only(ax)
    figs["fig07"] = save(fig, args.outdir, "fig07_submeter_mix.png")

    # ---------------------------------------------------- DST / clock check
    per_bin = gap.groupby([gap.index.normalize(), (gap.index.hour * 60 + gap.index.minute) // 10]).mean().unstack()
    per_bin = per_bin.reindex(columns=range(144))
    day_ok = d["ok"].reindex(per_bin.index).fillna(False)

    def window_profile(a: pd.Timestamp, b: pd.Timestamp):
        days = [x for x in per_bin.index if a <= x <= b and x.day_of_week < 5 and day_ok.get(x, False)]
        if len(days) < 5:
            return None, len(days)
        return np.nanmean(per_bin.loc[days].to_numpy(), axis=0), len(days)

    dst_rows = []
    example_profiles = None
    for year in (2007, 2008, 2009, 2010):
        for month, label in ((3, "March"), (10, "October")):
            T = last_sunday(year, month)
            D = pd.Timedelta(days=1)
            wins = {
                "pre2": (T - 28 * D, T - 15 * D),
                "pre": (T - 14 * D, T - 1 * D),
                "post": (T + 1 * D, T + 14 * D),
                "post2": (T + 15 * D, T + 28 * D),
            }
            prof_w = {k: window_profile(*v) for k, v in wins.items()}
            row = {"transition": f"{label} {year}", "date": str(T.date()), "weekdays_used": {k: v[1] for k, v in prof_w.items()}}

            def shift(a_key: str, b_key: str, prof_w=prof_w):
                pa, pb = prof_w[a_key][0], prof_w[b_key][0]
                if pa is None or pb is None:
                    return None
                s, r, r0 = best_shift(pa, pb)
                return {"shift_minutes": s, "corr_best": round(r, 4), "corr_at_zero": round(r0, 4)}

            row["across_change_pre_to_post"] = shift("pre", "post")
            row["control_before_pre2_to_pre"] = shift("pre2", "pre")
            row["control_after_post_to_post2"] = shift("post", "post2")
            dst_rows.append(row)
            if year == 2009 and month == 3:
                example_profiles = (prof_w["pre"][0], prof_w["post"][0], T)
    stats["dst_check"] = dst_rows

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.1], "wspace": 0.28})
    pre_p, post_p, T9 = example_profiles
    hrs = np.arange(144) / 6
    a1.plot(hrs, pre_p, color=BLUE, lw=2)
    a1.plot(hrs, post_p, color=ORANGE, lw=2)
    a1.set_xticks(range(0, 25, 3))
    a1.set_xlabel("Time of day on the logger clock (hours)")
    a1.set_ylabel("Mean weekday load (kW)")
    a1.set_title(f"Weekday profile around {T9.strftime('%d %b %Y')}")
    a1.legend(handles=[plt.Line2D([], [], color=BLUE, lw=2, label="2 weeks before"), plt.Line2D([], [], color=ORANGE, lw=2, label="2 weeks after")], loc="upper left")
    y_grid_only(a1)
    xs = np.arange(len(dst_rows))
    for i, r in enumerate(dst_rows):
        # controls are offset left/right of the main marker so no point is hidden
        for key, dx in (("control_before_pre2_to_pre", -0.2), ("control_after_post_to_post2", 0.2)):
            if r[key] is not None:
                a2.scatter(i + dx, r[key]["shift_minutes"], s=46, marker="D", color=ORANGE, edgecolor=SURFACE, linewidth=1.2, zorder=3)
        if r["across_change_pre_to_post"] is not None:
            a2.scatter(i, r["across_change_pre_to_post"]["shift_minutes"], s=80, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=4)
    a2.axhline(0, color=AXIS, lw=1)
    for yv in (-60, 60):
        a2.axhline(yv, color=GRID, lw=0.8, ls=(0, (4, 3)))
    a2.set_xticks(xs, [r["transition"].replace("March", "Mar").replace("October", "Oct").replace(" ", "\n") for r in dst_rows], fontsize=8)
    a2.set_ylabel("Profile shift (minutes, + = later)")
    a2.set_title("Estimated shift across each EU clock change")
    a2.legend(
        handles=[
            plt.Line2D([], [], color=BLUE, marker="o", ls="", ms=8, label="Across the clock change"),
            plt.Line2D([], [], color=ORANGE, marker="D", ls="", ms=6, label="Adjacent windows, no change"),
        ],
        loc="lower left",
        fontsize=8,
    )
    y_grid_only(a2)
    figs["fig08"] = save(fig, args.outdir, "fig08_clock_check.png")

    # ------------------------------------------------------------ flatlines
    v = gap.to_numpy()
    same = (v[1:] == v[:-1]) & ~np.isnan(v[1:]) & ~np.isnan(v[:-1])
    st, ln = run_lengths(same)
    ln = ln + 1  # number of identical readings in the run
    order = np.argsort(ln)[::-1][:5]
    stats["flat_runs"] = {
        "runs_of_identical_readings_ge_30_min": int((ln >= 30).sum()),
        "runs_ge_60_min": int((ln >= 60).sum()),
        "longest": [
            {"start": str(gap.index[st[i]]), "minutes": int(ln[i]), "value_kw": float(v[st[i]])} for i in order
        ],
    }

    # ----------------------------------------------------- summary statistics
    hs = hv.dropna()
    wk = hh.dropna(subset=["v"])
    wk_mean = wk.groupby("weekend")["v"].mean()
    peak_hour = prof.idxmax()
    stats["hourly_series"] = {
        "hours_with_value": int(hs.size),
        "mean_kw": round(float(hs.mean()), 4),
        "median_kw": round(float(hs.median()), 4),
        "std_kw": round(float(hs.std()), 4),
        "p5_kw": round(float(hs.quantile(0.05)), 4),
        "p95_kw": round(float(hs.quantile(0.95)), 4),
        "p99_kw": round(float(hs.quantile(0.99)), 4),
        "max_kw": round(float(hs.max()), 4),
        "weekday_mean_kw": round(float(wk_mean[False]), 4),
        "weekend_mean_kw": round(float(wk_mean[True]), 4),
        "weekday_peak_hour": int(peak_hour[False]),
        "weekend_peak_hour": int(peak_hour[True]),
        "weekday_peak_hour_mean_kw": round(float(prof[False].max()), 4),
        "weekend_peak_hour_mean_kw": round(float(prof[True].max()), 4),
        "overnight_3am_mean_kw_weekday": round(float(prof[False].loc[3]), 4),
        "top10_hours": [{"hour": str(t), "kw": round(float(x), 3)} for t, x in hs.nlargest(10).items()],
    }
    stats["acf_hourly"] = {f"lag_{k}": round(float(acf[k]), 4) for k in (1, 2, 3, 6, 12, 24, 48, 72, 96, 120, 144, 168)}

    yr_full = ok_days.groupby("year")["kwh"].agg(["mean", "count"])
    same_window = {}
    for yr in (2007, 2008, 2009, 2010):
        sub = ok_days[(ok_days.index >= f"{yr}-01-01") & (ok_days.index <= f"{yr}-11-25")]
        same_window[str(yr)] = {"mean_kwh_per_day": round(float(sub["kwh"].mean()), 3), "valid_days": int(len(sub))}
    stats["daily_energy"] = {
        "valid_days": int(len(ok_days)),
        "by_year_all_valid_days": {str(y): {"mean_kwh_per_day": round(float(r["mean"]), 3), "valid_days": int(r["count"])} for y, r in yr_full.iterrows()},
        "jan1_to_nov25_same_window_each_year": same_window,
        "lowest_10_days": [{"date": str(t.date()), "kwh": round(float(x), 2)} for t, x in ok_days["kwh"].nsmallest(10).items()],
        "highest_5_days": [{"date": str(t.date()), "kwh": round(float(x), 2)} for t, x in ok_days["kwh"].nlargest(5).items()],
    }
    stats["monthly_mean_kwh_per_day"] = {
        str(y): {int(m): (None if pd.isna(val) else round(float(val), 2)) for m, val in month_tbl[y].items()} for y in month_tbl.columns
    }

    split_stats = {}
    for name, (a, b) in SPLITS.items():
        seg = hv[a:b]
        hours = int(len(seg))
        valid = int(seg.notna().sum())
        sd = ok_days[a:b[:10]]
        split_stats[name] = {
            "from": a,
            "to": b,
            "hours_in_split": hours,
            "valid_hours": valid,
            "valid_pct": round(100 * valid / hours, 2),
            "excluded_hours": hours - valid,
            "mean_kw": round(float(seg.mean()), 4),
            "median_kw": round(float(seg.median()), 4),
            "p95_kw": round(float(seg.quantile(0.95)), 4),
            "max_kw": round(float(seg.max()), 4),
            "valid_days": int(len(sd)),
            "mean_kwh_per_day": round(float(sd["kwh"].mean()), 3),
        }
    stats["proposed_split"] = split_stats
    stats["figures"] = figs

    (args.outdir / "eda_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("hourly_series", "acf_hourly", "daily_energy", "proposed_split", "flat_runs", "unmetered_share_of_active_energy")}, indent=2))
    print("\nDST CHECK")
    for r in dst_rows:
        print(
            r["transition"],
            "| across:", r["across_change_pre_to_post"],
            "| ctrl-before:", r["control_before_pre2_to_pre"],
            "| ctrl-after:", r["control_after_post_to_post2"],
            "| days:", r["weekdays_used"],
        )


if __name__ == "__main__":
    main()
