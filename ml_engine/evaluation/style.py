"""Shared matplotlib style and fixed entity colours for evaluation figures.

Colour follows the entity (a model keeps its colour in every figure). Hues are
the validated categorical set from docs/04_eda_report.md; baselines are neutral.
"""
from __future__ import annotations

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"

MODEL_COLORS = {
    "naive": "#8e8d85",
    "seasonal_naive_24": "#b4b3aa",
    "seasonal_naive_168": "#d0cfc7",
    "random_forest": AQUA,
    "xgboost": BLUE,
    "lstm": ORANGE,
    "actual": INK,
}
MODEL_LABELS = {
    "naive": "Naive (last hour)",
    "seasonal_naive_24": "Seasonal naive (24 h)",
    "seasonal_naive_168": "Seasonal naive (168 h)",
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
    "lstm": "LSTM",
    "actual": "Actual",
}
MODEL_ORDER = ["naive", "seasonal_naive_24", "seasonal_naive_168", "random_forest", "xgboost", "lstm"]


def setup_style() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "text.color": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.edgecolor": AXIS, "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "legend.frameon": False, "legend.fontsize": 9, "lines.solid_capstyle": "round",
        "figure.dpi": 100, "savefig.dpi": 150,
    })
