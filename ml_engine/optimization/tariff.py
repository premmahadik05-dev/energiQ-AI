"""Editable electricity tariff and cost calculation.

A tariff is an hourly price schedule (24 weekday values, 24 weekend values) plus an optional
daily fixed charge. The built-in ``DEMO_TARIFF`` is a made-up two-period schedule used so the
platform works out of the box; it is NOT any utility's real price list. Users must replace it
with their own rates before reading any cost figure.

Energy for an hour is the hourly mean power in kW times 1 h = kWh.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class TariffError(ValueError):
    pass


@dataclass
class Tariff:
    name: str
    currency: str
    weekday_rates: list[float]  # price per kWh for hour 0..23
    weekend_rates: list[float]
    daily_fixed_charge: float = 0.0
    is_demo: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        for label, r in (("weekday_rates", self.weekday_rates), ("weekend_rates", self.weekend_rates)):
            if len(r) != 24:
                raise TariffError(f"{label} must have exactly 24 values (one per hour)")
            if any((not np.isfinite(x)) or x < 0 for x in r):
                raise TariffError(f"{label} must be finite and non-negative")
        if self.daily_fixed_charge < 0 or not np.isfinite(self.daily_fixed_charge):
            raise TariffError("daily_fixed_charge must be finite and non-negative")
        if not self.currency or len(self.currency) > 8:
            raise TariffError("currency must be a short code or symbol")

    def rates_for(self, index: pd.DatetimeIndex) -> np.ndarray:
        wk = np.asarray(self.weekday_rates)
        we = np.asarray(self.weekend_rates)
        weekend = index.day_of_week >= 5
        return np.where(weekend, we[index.hour], wk[index.hour])

    def to_dict(self) -> dict:
        return {"name": self.name, "currency": self.currency, "weekday_rates": list(self.weekday_rates),
                "weekend_rates": list(self.weekend_rates), "daily_fixed_charge": self.daily_fixed_charge,
                "is_demo": self.is_demo, "note": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> Tariff:
        try:
            return cls(name=str(d["name"]), currency=str(d["currency"]), weekday_rates=[float(x) for x in d["weekday_rates"]],
                       weekend_rates=[float(x) for x in d["weekend_rates"]],
                       daily_fixed_charge=float(d.get("daily_fixed_charge", 0.0)), is_demo=bool(d.get("is_demo", False)),
                       note=str(d.get("note", "")))
        except (KeyError, TypeError) as exc:
            raise TariffError(f"invalid tariff: {exc}") from exc

    def cheapest_and_dearest(self) -> tuple[float, float]:
        allr = list(self.weekday_rates) + list(self.weekend_rates)
        return min(allr), max(allr)


def _demo() -> Tariff:
    wk = [0.12] * 6 + [0.20] * 11 + [0.30] * 4 + [0.20] * 2 + [0.12]  # 00-05 off-peak, 17-20 peak, 23 off-peak
    we = [0.12] * 8 + [0.20] * 14 + [0.12] * 2
    return Tariff(name="DEMO tariff (not a real utility price)", currency="EUR", weekday_rates=wk, weekend_rates=we,
                  daily_fixed_charge=0.0, is_demo=True,
                  note="Illustrative numbers only. Replace with your own rates before using any cost figure.")


DEMO_TARIFF = _demo()


def energy_kwh(series_kw: pd.Series) -> pd.Series:
    """Hourly energy in kWh (hourly mean kW x 1 h); missing hours stay NaN."""
    return series_kw.astype("float64")


def cost_of_series(series_kw: pd.Series, tariff: Tariff) -> dict:
    """Energy and cost over the *valid* hours of the series. Missing hours are not costed."""
    e = energy_kwh(series_kw).dropna()
    if e.empty:
        return {"valid_hours": 0, "energy_kwh": 0.0, "energy_cost": 0.0, "fixed_cost": 0.0, "total_cost": 0.0,
                "currency": tariff.currency, "is_demo_tariff": tariff.is_demo}
    rates = tariff.rates_for(e.index)
    energy_cost = float((e.to_numpy() * rates).sum())
    days = len(e) / 24.0
    fixed = tariff.daily_fixed_charge * days
    return {"valid_hours": int(len(e)), "energy_kwh": float(e.sum()), "energy_cost": energy_cost,
            "fixed_cost": float(fixed), "total_cost": energy_cost + float(fixed), "currency": tariff.currency,
            "is_demo_tariff": tariff.is_demo, "avg_cost_per_kwh": energy_cost / float(e.sum()) if e.sum() > 0 else None}
