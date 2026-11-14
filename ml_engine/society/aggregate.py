"""Society aggregation: from real per-building meters to one community demand series.

Definition used everywhere in this project
------------------------------------------
* A *society* is the set of residential-use buildings of one BDG2 site that pass the meter-validity
  rule below. It is a research-based representative community, not a registered housing society.
* ``society_kwh[t]`` = sum over retained buildings of the cleaned hourly energy (kWh) at hour ``t``.
  The sum exists only when *every* retained meter has a valid reading at ``t``; otherwise it is NaN.
  (Summing the available meters would silently understate demand, so it is never done.)
* Energy (kWh) and power (kW) are kept apart: one hourly kWh reading is energy for that hour; the
  average demand over the hour is the same number read as kW. Daily energy is the sum of 24 hourly
  kWh values. Peak demand is the highest *hourly average* kW, not an instantaneous peak.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .cleaning import CleaningConfig, clean_meter, regularise_hourly


@dataclass(frozen=True)
class SocietyRule:
    primary_use: str = "Lodging/residential"
    exclude_sub_uses: tuple[str, ...] = ("Hotel",)
    min_meter_valid_share: float = 0.95
    min_buildings: int = 8
    min_society_valid_share: float = 0.94

    def to_dict(self) -> dict:
        d = asdict(self)
        d["exclude_sub_uses"] = list(self.exclude_sub_uses)
        return d


def residential_candidates(metadata: pd.DataFrame, meters: pd.DataFrame, rule: SocietyRule = SocietyRule()) -> pd.DataFrame:
    """Residential buildings that have an electricity column, one row per building."""
    md = metadata[(metadata["primaryspaceusage"] == rule.primary_use)
                  & ~metadata["sub_primaryspaceusage"].fillna("").str.strip().isin(rule.exclude_sub_uses)
                  & metadata["building_id"].isin(meters.columns)].copy()
    md["sub_primaryspaceusage"] = md["sub_primaryspaceusage"].fillna("").str.strip()
    return md


def build_society(site: str, metadata: pd.DataFrame, meters: pd.DataFrame, weather: pd.DataFrame,
                  rule: SocietyRule = SocietyRule(), cleaning: CleaningConfig = CleaningConfig()) -> dict | None:
    """Clean every candidate meter of a site and aggregate. Returns None if the site does not qualify."""
    cand = residential_candidates(metadata[metadata["site_id"] == site], meters, rule)
    if cand.empty:
        return None
    raw, ts_report = regularise_hourly(meters[cand["building_id"].tolist()])
    cleaned: dict[str, pd.Series] = {}
    per_meter: dict[str, dict] = {}
    for b in raw.columns:
        cleaned[b], per_meter[b] = clean_meter(raw[b], cleaning)
    clean_df = pd.DataFrame(cleaned)
    share = clean_df.notna().mean()
    kept = [b for b in clean_df.columns if share[b] >= rule.min_meter_valid_share]
    excluded = [{"source_id": b, "valid_share": round(float(share[b]), 4), "reason": f"valid hours {share[b]:.1%} below the {rule.min_meter_valid_share:.0%} rule", **per_meter[b]}
                for b in clean_df.columns if b not in kept]
    if len(kept) < rule.min_buildings:
        return {"site": site, "qualifies": False, "reason": f"only {len(kept)} meters pass the validity rule (need {rule.min_buildings})",
                "candidates": int(len(cand)), "kept": len(kept)}
    kept_df = clean_df[kept]
    total = kept_df.sum(axis=1, min_count=len(kept))  # NaN unless every retained meter is valid
    n_valid = kept_df.notna().sum(axis=1)
    society_share = float(total.notna().mean())
    if society_share < rule.min_society_valid_share:
        return {"site": site, "qualifies": False, "reason": f"society total valid in only {society_share:.1%} of hours",
                "candidates": int(len(cand)), "kept": len(kept)}

    wx = weather[weather["site_id"] == site].drop(columns=["site_id"]).copy()
    wx["timestamp"] = pd.to_datetime(wx["timestamp"])
    wx = wx.drop_duplicates("timestamp").set_index("timestamp").sort_index().reindex(total.index)
    wx.index.name = "timestamp"

    md = cand.set_index("building_id").loc[kept]
    buildings = pd.DataFrame({
        "source_id": md.index,
        "sub_use": md["sub_primaryspaceusage"].to_numpy(),
        "floor_area_sqm": md["sqm"].to_numpy(),
        "year_built": md["yearbuilt"].to_numpy(),
        "floors": md["numberoffloors"].to_numpy(),
        "valid_share": [round(float(share[b]), 4) for b in kept],
    })
    tz = str(cand["timezone"].iloc[0])
    return {
        "site": site, "qualifies": True, "timezone": tz,
        "lat": float(cand["lat"].iloc[0]), "lng": float(cand["lng"].iloc[0]),
        "buildings": buildings, "excluded": excluded,
        "meters": kept_df, "society_kwh": total.rename("society_kwh"), "n_valid_meters": n_valid.rename("n_valid_meters"),
        "weather": wx, "timestamps": ts_report, "candidates": int(len(cand)),
        "society_valid_share": society_share,
        "cleaning_counts": {b: per_meter[b] for b in kept},
        "rule": rule.to_dict(), "cleaning": cleaning.to_dict(),
    }
