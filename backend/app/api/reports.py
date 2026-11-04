"""Downloadable, self-contained HTML report for a dataset. All user-controlled text is HTML-escaped."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml_engine.optimization.tariff import DEMO_TARIFF, cost_of_series

from ..models import Anomaly, Forecast, ModelVersion, User, utcnow
from ..security import current_user_dep
from ..services.data import load_series
from .deps import get_session, owned_dataset

router = APIRouter(tags=["reports"])
CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
CSS = ("body{font:14px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1b1b1a}"
       "h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:1.8rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}"
       "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #eee;font-size:13px}"
       ".note{color:#555;font-size:12px}.warn{background:#fff6e0;padding:.5rem .7rem;border-radius:6px}")


def _table(headers: list[str], rows: list[list]) -> str:
    th = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>"


@router.get("/datasets/{dataset_id}/report", response_class=HTMLResponse)
def dataset_report(dataset_id: int, user: User = Depends(current_user_dep), db: Session = Depends(get_session)):
    ds = owned_dataset(db, user, dataset_id)
    q = (ds.report or {}).get("quality", {})
    parts = [f"<h1>EnergiQ AI report: {escape(ds.name)}</h1>",
             f"<p class='note'>Generated {utcnow():%Y-%m-%d %H:%M} UTC. Figures come from the stored hourly data; nothing is imputed.</p>",
             "<h2>Data</h2>",
             _table(["Item", "Value"], [["Status", ds.status], ["Period", f"{ds.start_ts} to {ds.end_ts}"], ["Hours", ds.hours],
                                        ["Valid hours", ds.valid_hours], ["Quality score (0-100)", ds.quality_score],
                                        ["Completeness", q.get("completeness")], ["Unit declared", (ds.report or {}).get("unit_declared")],
                                        ["Timezone convention", (ds.report or {}).get("timezone_convention")]])]
    for w in (ds.report or {}).get("warnings", []):
        parts.append(f"<p class='warn'>{escape(w)}</p>")
    s = load_series(db, ds.id)
    if s.notna().any():
        c = cost_of_series(s, DEMO_TARIFF)
        parts += ["<h2>Energy and cost</h2>",
                  f"<p>Total energy {c['energy_kwh']:.0f} kWh. Cost under the built-in <b>DEMO tariff</b> (illustrative prices, not a real utility): "
                  f"{c['total_cost']:.2f} {escape(c['currency'])}. Use the app with your own tariff for real figures.</p>"]
    mv = db.scalar(select(ModelVersion).where(ModelVersion.dataset_id == ds.id, ModelVersion.is_active.is_(True)))
    if mv:
        rows = [[f"{h} h", f"{v['metrics']['xgboost']['mae']:.3f}", f"{v['metrics'][v['best_baseline']]['mae']:.3f}", v["best_baseline"],
                 f"{v['mae_improvement_vs_best_baseline_pct']:.1f}%"] for h, v in mv.evaluation["horizons"].items()]
        parts += ["<h2>Forecast model (hold-out accuracy)</h2>",
                  f"<p class='note'>Scored on the final chronological block ({escape(mv.evaluation['holdout_start'])} onward), fitted only on earlier data.</p>",
                  _table(["Horizon", "Model MAE (kW)", "Best baseline MAE (kW)", "Baseline", "Improvement"], rows)]
        fc = db.scalar(select(Forecast).where(Forecast.dataset_id == ds.id, Forecast.model_id == mv.id).order_by(Forecast.id.desc()))
        if fc:
            parts += [f"<h2>Latest 24 h forecast (origin {escape(str(fc.origin))})</h2>",
                      _table(["Time", "Forecast kW", "Range kW"], [[p["ts"], f"{p['kw']:.2f}", f"{p['lower_kw']:.2f} - {p['upper_kw']:.2f}"] for p in fc.points])]
    an = db.scalars(select(Anomaly).where(Anomaly.dataset_id == ds.id).order_by(Anomaly.severity_level.desc(), Anomaly.peak_excess_ratio.desc().nulls_last()).limit(10)).all()
    if an:
        parts += ["<h2>Most severe anomalies</h2>",
                  _table(["Start", "Severity", "Hours", "Explanation"], [[a.start_ts, a.severity, a.hours, a.explanation] for a in an]),
                  "<p class='note'>Anomalies are unusual readings found without labels; they are not confirmed faults.</p>"]
    html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>EnergiQ report</title><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"
    return HTMLResponse(html, headers={"Content-Security-Policy": CSP, "Content-Disposition": f'attachment; filename="energiq_report_{ds.id}.html"'})
