"""后端核对：所有解析用例必须通过；API 行为（静风 422、分辨率无关等）。"""
from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.checks import run_all_checks
from app.main import app
from app.services import run_points

client = TestClient(app)


def _base_payload(wind_speed=4.0, wind_from=270.0, stability="D", bg=10.0):
    return {
        "source": {
            "name": "测试源", "lon": 116.40, "lat": 39.90,
            "stack_height_m": 60.0, "emission_rate_g_s": 50.0,
            "stack_diameter_m": 4.0, "exit_velocity_ms": 18.0,
            "stack_temp_k": 410.0, "pollutant": "SO2",
        },
        "meteorology": {
            "name": "测试气象", "wind_from_deg": wind_from,
            "wind_speed_ms": wind_speed, "stability_class": stability,
            "ambient_temp_k": 293.15, "pressure_hpa": 1013.0,
            "background_conc_ug_m3": bg,
        },
        "grid": {
            "downwind_extent_m": 6000.0, "crosswind_extent_m": 2000.0,
            "upwind_extent_m": 300.0, "nx": 121, "ny": 81,
        },
    }


def test_all_analytical_checks_pass():
    report = run_all_checks()
    assert report["all_passed"], [
        (r["id"], r["actual"]) for r in report["results"] if not r["passed"]
    ]


def test_health_and_meta():
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["units"]["concentration"] == "μg/m³"
    assert "briggs_rural" in meta["parameterizations"]


def test_seed_data_present():
    sources = client.get("/api/sources").json()
    mets = client.get("/api/meteorology").json()
    assert len(sources) >= 3 and len(mets) >= 5


def test_grid_endpoint_shape_and_separation():
    resp = client.post("/api/plume/grid", json=_base_payload())
    assert resp.status_code == 200
    data = resp.json()
    plume = np.array(data["plume_field_ug_m3"])
    total = np.array(data["total_conc_ug_m3"])
    assert plume.shape == (81, 121)
    assert np.allclose(total, plume + data["background_conc_ug_m3"])
    assert data["grid"]["corners_lonlat"]
    # 等值级均为正且不超过最大值
    levels = data["iso_levels_ug_m3"]
    assert levels and max(levels) <= plume.max()


def test_calm_wind_rejected_via_api():
    payload = _base_payload(wind_speed=0.3)
    resp = client.post("/api/plume/grid", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"] == "calm_wind"


def test_points_and_grid_consistent():
    """API 点求值：源正东（270° 西风的下风向）点的下风向距离必须为正。"""
    payload = _base_payload(wind_from=270.0)
    src_lon, src_lat = payload["source"]["lon"], payload["source"]["lat"]
    # 源以东约 1 km：等距圆柱近似 dlon[rad]=1000/(R cos lat)，再转度
    dlon = math.degrees(1000.0 / (6_371_000.0 * math.cos(math.radians(src_lat))))
    payload["points"] = [[src_lon + dlon, src_lat]]
    presp = client.post("/api/plume/points", json=payload)
    assert presp.status_code == 200
    p = presp.json()["points"][0]
    # 平面近似闭环，米级误差（平面/球面差异量级，已在界面声明）
    assert abs(p["downwind_crosswind_m"][0] - 1000.0) < 2.0
    assert abs(p["downwind_crosswind_m"][1]) < 2.0
    assert p["plume_conc_ug_m3"] >= 0


def test_wind_check_known_values():
    # 北风（0° 来向）-> 烟羽向南 180°，下风向单位向量 (0,-1)
    r = client.get("/api/plume/wind-check", params={"wind_from_deg": 0}).json()
    assert r["transport_bearing_deg"] == 180.0
    assert r["dot_product_check"] == pytest.approx(0.0, abs=1e-9)
    assert r["norm_check"] == pytest.approx(1.0, abs=1e-9)
    # 西风（270° 来向）-> 向东 90°
    r2 = client.get("/api/plume/wind-check", params={"wind_from_deg": 270}).json()
    assert r2["transport_bearing_deg"] == 90.0


def test_override_does_not_mutate_base_input():
    payload = _base_payload()
    payload["source_override"] = {"stack_height_m": 200.0}
    payload["met_override"] = {"wind_speed_ms": 5.0}
    # 源/气象对象本身保持 60 m / 4 m/s
    assert payload["source"]["stack_height_m"] == 60.0
    assert payload["meteorology"]["wind_speed_ms"] == 4.0
    resp = client.post("/api/plume/grid", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # 有效源高采用 override 值（无抬升时等于 200 m）
    assert data["effective_stack_height_m"] == 200.0


def test_power_law_peak_location_analytic():
    """端到端验证 x_peak = H/(sqrt2 az)。"""
    payload = _base_payload(wind_speed=4.0, stability="D")
    payload["parameterization"] = "power_law"
    payload["power_law"] = {"ay": 0.22, "py": 1.0, "az": 0.16, "pz": 1.0}
    payload["source"]["stack_height_m"] = 60.0
    payload["grid"] = {
        "downwind_extent_m": 1000.0, "crosswind_extent_m": 60.0,
        "upwind_extent_m": 0.0, "nx": 401, "ny": 5,
    }
    data = client.post("/api/plume/grid", json=payload)
    assert data.status_code == 200, data.text
    data = data.json()
    plume = np.array(data["plume_field_ug_m3"])
    ix = int(np.argmax(plume[1]))
    x = data["grid"]["x_edges_m"][ix]
    expected = 60.0 / (math.sqrt(2) * 0.16)
    assert abs(x - expected) / expected < 0.02
