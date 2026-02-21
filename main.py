# backend/main.py
import os
from typing import Optional, Dict, Any

import numpy as np
import pandapower as pp
from pandapower.converter.matpower.from_mpc import from_mpc
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware

CASE_PATH = os.environ.get(
    "CASE_PATH",
    r"C:\Users\USER\PycharmProjects\PythonProject\snemQLD.m"
)

F_HZ = float(os.environ.get("F_HZ", "50"))

app = FastAPI(title="Pandapower Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache: Dict[str, Any] = {"last_result": None}


def _safe_float(x):
    try:
        if x is None:
            return None
        if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
            return None
        return float(x)
    except Exception:
        return None


def run_powerflow() -> Dict[str, Any]:
    # Load MATPOWER case
    net = from_mpc(CASE_PATH, f_hz=F_HZ)

    # Run power flow
    pp.runpp(net, algorithm="nr", init="auto")

    if not bool(getattr(net, "converged", False)):
        return {"converged": False, "error": "Power flow did not converge."}

    # Voltage
    v = net.res_bus["vm_pu"].to_numpy()
    va = net.res_bus["va_degree"].to_numpy()

    vmin, vmax = 0.94, 1.06
    viol_idx = np.where((v < vmin) | (v > vmax))[0]

    viol_buses = [
        {"bus": int(i), "vm_pu": _safe_float(v[i]), "va_degree": _safe_float(va[i])}
        for i in viol_idx[:200]
    ]

    # Line loading
    line_loading = []
    top_lines = []

    if len(net.line) > 0 and "loading_percent" in net.res_line.columns:
        ll = net.res_line["loading_percent"].to_numpy()
        line_loading = [_safe_float(x) for x in ll]

        top_idx = np.argsort(-np.nan_to_num(ll))[:10]

        for j in top_idx:
            top_lines.append({
                "line": int(j),
                "loading_percent": _safe_float(ll[j]),
                "from_bus": int(net.line.at[j, "from_bus"]),
                "to_bus": int(net.line.at[j, "to_bus"]),
            })

    # Transformer loading
    trafo_loading = []
    top_trafos = []

    if len(net.trafo) > 0 and "loading_percent" in net.res_trafo.columns:
        tl = net.res_trafo["loading_percent"].to_numpy()
        trafo_loading = [_safe_float(x) for x in tl]

        top_idx = np.argsort(-np.nan_to_num(tl))[:10]

        for j in top_idx:
            top_trafos.append({
                "trafo": int(j),
                "loading_percent": _safe_float(tl[j]),
                "hv_bus": int(net.trafo.at[j, "hv_bus"]),
                "lv_bus": int(net.trafo.at[j, "lv_bus"]),
            })

    # KPIs
    total_load_mw = float(net.load["p_mw"].sum()) if len(net.load) else 0.0
    total_gen_mw = float(net.gen["p_mw"].sum()) if len(net.gen) else 0.0

    return {
        "converged": True,
        "case_path": CASE_PATH,
        "kpis": {
            "n_bus": int(len(net.bus)),
            "n_line": int(len(net.line)),
            "n_trafo": int(len(net.trafo)),
            "n_load": int(len(net.load)),
            "n_gen": int(len(net.gen)),
            "total_load_mw": total_load_mw,
            "total_gen_mw": total_gen_mw,
            "v_min": float(np.nanmin(v)) if len(v) else None,
            "v_max": float(np.nanmax(v)) if len(v) else None,
            "v_mean": float(np.nanmean(v)) if len(v) else None,
            "voltage_violations": int(len(viol_idx)),
            "line_over_80pct": int(np.sum(np.array(line_loading, dtype=float) > 80)) if line_loading else 0,
            "trafo_over_80pct": int(np.sum(np.array(trafo_loading, dtype=float) > 80)) if trafo_loading else 0,
        },
        "limits": {
            "vmin_pu": vmin,
            "vmax_pu": vmax,
            "thermal_warn_pct": 80.0
        },
        "series": {
            "bus_voltage_pu": [_safe_float(x) for x in v],
            "line_loading_percent": line_loading,
            "trafo_loading_percent": trafo_loading,
        },
        "tables": {
            "voltage_violations": viol_buses,
            "top_lines": top_lines,
            "top_trafos": top_trafos,
        },
    }


def run_powerflow_scenario(load_scale: float = 1.0, gen_scale: float = 1.0) -> Dict[str, Any]:
    # Load MATPOWER case fresh each scenario
    net = from_mpc(CASE_PATH, f_hz=F_HZ)

    # Scale loads
    if len(net.load):
        net.load["p_mw"] *= load_scale
        net.load["q_mvar"] *= load_scale

    # Scale generation
    if len(net.gen):
        net.gen["p_mw"] *= gen_scale

    # Run power flow
    pp.runpp(net, algorithm="nr", init="auto")

    if not bool(getattr(net, "converged", False)):
        return {"converged": False, "error": "Power flow did not converge."}

    # Voltage
    v = net.res_bus["vm_pu"].to_numpy()
    va = net.res_bus["va_degree"].to_numpy()

    vmin, vmax = 0.94, 1.06
    viol_idx = np.where((v < vmin) | (v > vmax))[0]

    viol_buses = [
        {"bus": int(i), "vm_pu": _safe_float(v[i]), "va_degree": _safe_float(va[i])}
        for i in viol_idx[:200]
    ]

    # Line loading
    line_loading, top_lines = [], []

    if len(net.line) > 0 and "loading_percent" in net.res_line.columns:
        ll = net.res_line["loading_percent"].to_numpy()
        line_loading = [_safe_float(x) for x in ll]

        top_idx = np.argsort(-np.nan_to_num(ll))[:10]

        for j in top_idx:
            top_lines.append({
                "line": int(j),
                "loading_percent": _safe_float(ll[j]),
                "from_bus": int(net.line.at[j, "from_bus"]),
                "to_bus": int(net.line.at[j, "to_bus"]),
            })

    # Trafo loading
    trafo_loading, top_trafos = [], []

    if len(net.trafo) > 0 and "loading_percent" in net.res_trafo.columns:
        tl = net.res_trafo["loading_percent"].to_numpy()
        trafo_loading = [_safe_float(x) for x in tl]

        top_idx = np.argsort(-np.nan_to_num(tl))[:10]

        for j in top_idx:
            top_trafos.append({
                "trafo": int(j),
                "loading_percent": _safe_float(tl[j]),
                "hv_bus": int(net.trafo.at[j, "hv_bus"]),
                "lv_bus": int(net.trafo.at[j, "lv_bus"]),
            })

    total_load_mw = float(net.load["p_mw"].sum()) if len(net.load) else 0.0
    total_gen_mw = float(net.gen["p_mw"].sum()) if len(net.gen) else 0.0

    return {
        "converged": True,
        "case_path": CASE_PATH,
        "scenario": {"load_scale": load_scale, "gen_scale": gen_scale},
        "kpis": {
            "n_bus": int(len(net.bus)),
            "n_line": int(len(net.line)),
            "n_trafo": int(len(net.trafo)),
            "n_load": int(len(net.load)),
            "n_gen": int(len(net.gen)),
            "total_load_mw": total_load_mw,
            "total_gen_mw": total_gen_mw,
            "v_min": float(np.nanmin(v)) if len(v) else None,
            "v_max": float(np.nanmax(v)) if len(v) else None,
            "v_mean": float(np.nanmean(v)) if len(v) else None,
            "voltage_violations": int(len(viol_idx)),
            "line_over_80pct": int(np.sum(np.array(line_loading, dtype=float) > 80)) if line_loading else 0,
            "trafo_over_80pct": int(np.sum(np.array(trafo_loading, dtype=float) > 80)) if trafo_loading else 0,
        },
        "limits": {
            "vmin_pu": 0.94,
            "vmax_pu": 1.06,
            "thermal_warn_pct": 80.0
        },
        "series": {
            "bus_voltage_pu": [_safe_float(x) for x in v],
            "line_loading_percent": line_loading,
            "trafo_loading_percent": trafo_loading,
        },
        "tables": {
            "voltage_violations": viol_buses,
            "top_lines": top_lines,
            "top_trafos": top_trafos,
        },
    }


@app.get("/api/health")
def health():
    return {"ok": True, "case_path": CASE_PATH, "f_hz": F_HZ}


@app.get("/api/results")
def results():
    if _cache["last_result"] is None:
        _cache["last_result"] = run_powerflow()
    return _cache["last_result"]


@app.post("/api/run")
def run(payload: Dict[str, Any] = Body(default={})):
    load_scale = float(payload.get("load_scale", 1.0))
    gen_scale = float(payload.get("gen_scale", 1.0))

    _cache["last_result"] = run_powerflow_scenario(
        load_scale=load_scale,
        gen_scale=gen_scale
    )
    return _cache["last_result"]