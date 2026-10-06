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


# ---------- 课堂自定义阈值统计 ----------

def _cell_means(field: np.ndarray) -> np.ndarray:
    return 0.25 * (
        field[:-1, :-1] + field[:-1, 1:] + field[1:, :-1] + field[1:, 1:]
    )


def test_threshold_stats_shape_and_area():
    """超阈单元数×实际米制间距 = 面积；占比按单元数；与独立复算一致。"""
    payload = _base_payload(bg=10.0)
    payload["threshold_ug_m3"] = 50.0
    data = client.post("/api/plume/grid", json=payload).json()
    ts = data["threshold_statistics"]

    plume = np.array(data["plume_field_ug_m3"])
    total = np.array(data["total_conc_ug_m3"])
    dx = data["grid"]["spacing_downwind_m"]
    dy = data["grid"]["spacing_crosswind_m"]
    n_cells = (121 - 1) * (81 - 1)

    for key, field in (("plume", plume), ("total", total)):
        blk = ts[key]
        n_over = int(np.count_nonzero(_cell_means(field) > 50.0))
        assert blk["n_exceedance_cells"] == n_over
        assert blk["exceedance_area_m2"] == pytest.approx(n_over * dx * dy)
        assert blk["fraction_of_sampling_box"] == pytest.approx(n_over / n_cells)
        assert 0.0 <= blk["fraction_of_sampling_box"] <= 1.0
    assert ts["method"]["cell_area_m2"] == pytest.approx(dx * dy)
    # 总面积不超过采样框
    assert ts["plume"]["exceedance_area_m2"] <= ts["method"]["sampling_box_area_m2"]
    assert ts["total"]["exceedance_area_m2"] <= ts["method"]["sampling_box_area_m2"]


def test_threshold_above_all_values_gives_zero_area():
    """阈值高于全部采样值：两类面积均为 0、占比 0、empty=True。"""
    payload = _base_payload(bg=10.0)
    payload["threshold_ug_m3"] = 1.0e9
    data = client.post("/api/plume/grid", json=payload).json()
    ts = data["threshold_statistics"]
    for key in ("plume", "total"):
        blk = ts[key]
        assert blk["n_exceedance_cells"] == 0
        assert blk["exceedance_area_m2"] == 0.0
        assert blk["exceedance_area_km2"] == 0.0
        assert blk["fraction_of_sampling_box"] == 0.0
        assert blk["empty"] is True
    assert ts["threshold_ug_m3"] == 1.0e9
    assert ts["teaching_only"] is True


def test_background_changes_only_total_stats():
    """背景升高：plume 统计不变，仅 total 统计改变。"""
    p1 = _base_payload(bg=0.0)
    p1["threshold_ug_m3"] = 50.0
    p2 = _base_payload(bg=80.0)
    p2["threshold_ug_m3"] = 50.0
    ts1 = client.post("/api/plume/grid", json=p1).json()["threshold_statistics"]
    ts2 = client.post("/api/plume/grid", json=p2).json()["threshold_statistics"]
    assert ts1["plume"] == ts2["plume"]
    assert (
        ts2["total"]["n_exceedance_cells"]
        > ts1["total"]["n_exceedance_cells"]
    )
    # bg=80 > 阈值 50：总浓度处处超阈，占满整个采样框
    assert ts2["total"]["fraction_of_sampling_box"] == pytest.approx(1.0)


def test_threshold_stats_recompute_per_grid_resolution():
    """切换粗细网格：源/气象不被回写；统计按各自间距重新计算。

    粗网格覆盖的物理范围与细网格相同，超阈**面积**应相近（采样离散差异），
    但单元数、间距、单元面积必须随分辨率改变。
    """
    coarse = _base_payload(bg=10.0)
    coarse["grid"] = dict(coarse["grid"])
    coarse["grid"].update(nx=41, ny=21)
    coarse["threshold_ug_m3"] = 50.0
    fine = _base_payload(bg=10.0)
    fine["threshold_ug_m3"] = 50.0

    r_c = client.post("/api/plume/grid", json=coarse).json()
    r_f = client.post("/api/plume/grid", json=fine).json()

    # 源项/气象未被网格回写
    assert r_c["source_term"]["stack_height_m"] == 60.0
    assert r_f["source_term"]["stack_height_m"] == 60.0
    assert r_c["wind"]["wind_speed_ms"] == 4.0

    tc, tf = r_c["threshold_statistics"], r_f["threshold_statistics"]
    assert tc["method"]["spacing_downwind_m"] != tf["method"]["spacing_downwind_m"]
    assert tc["method"]["spacing_crosswind_m"] != tf["method"]["spacing_crosswind_m"]
    assert tc["plume"]["n_exceedance_cells"] != tf["plume"]["n_exceedance_cells"]
    # 面积各自按实际间距重算（粗网格每单元面积更大）
    assert tc["method"]["cell_area_m2"] > tf["method"]["cell_area_m2"]
    for blk_c, blk_f in (
        (tc["plume"], tf["plume"]),
        (tc["total"], tf["total"]),
    ):
        assert blk_c["exceedance_area_m2"] == pytest.approx(
            blk_c["n_exceedance_cells"] * tc["method"]["cell_area_m2"]
        )
        assert blk_f["exceedance_area_m2"] == pytest.approx(
            blk_f["n_exceedance_cells"] * tf["method"]["cell_area_m2"]
        )
        # 同一连续场在同一范围上的面积估计应接近（<25% 离散差异）
        assert abs(blk_c["exceedance_area_m2"] - blk_f["exceedance_area_m2"]) / max(
            blk_f["exceedance_area_m2"], 1.0
        ) < 0.25


def test_threshold_stats_nodes_out_of_range_counted():
    """下风向延伸到 Briggs 建议 10 km 之外：建议范围外格点数 > 0，
    且超阈单元中的越界单元被单独计数。"""
    payload = _base_payload(bg=0.0)
    payload["grid"].update(downwind_extent_m=12000.0, nx=241, ny=41)
    payload["threshold_ug_m3"] = 1.0
    data = client.post("/api/plume/grid", json=payload).json()
    ts = data["threshold_statistics"]
    assert ts["recommended_range"]["applicable"] is True
    assert ts["recommended_range"]["n_nodes_out_of_range"] > 0
    # 10–12 km 处浓度很低，阈值 1 μg/m³ 下可能有少量超阈越界单元，计数合法
    assert (
        ts["plume"]["n_exceedance_cells_out_of_recommended_range"]
        <= ts["plume"]["n_exceedance_cells"]
    )


def test_threshold_stats_power_law_range_not_applicable():
    """幂律参数化没有 Briggs 建议区间：越界计数为 0、applicable=False。"""
    payload = _base_payload(bg=0.0)
    payload["parameterization"] = "power_law"
    payload["power_law"] = {"ay": 0.22, "py": 1.0, "az": 0.16, "pz": 1.0}
    payload["threshold_ug_m3"] = 50.0
    ts = client.post("/api/plume/grid", json=payload).json()["threshold_statistics"]
    assert ts["recommended_range"]["applicable"] is False
    assert ts["recommended_range"]["n_nodes_out_of_range"] == 0


def test_calm_wind_has_no_threshold_stats():
    """静风仍返回 422 calm_wind，绝不产生任何浓度场或阈值统计。"""
    payload = _base_payload(wind_speed=0.3)
    payload["threshold_ug_m3"] = 50.0
    resp = client.post("/api/plume/grid", json=payload)
    assert resp.status_code == 422
    assert "threshold_statistics" not in resp.json()


def test_threshold_does_not_mutate_source_or_met():
    """阈值只是课堂分析参数：不改变任何源项/气象物理量。"""
    payload = _base_payload(bg=10.0)
    payload["threshold_ug_m3"] = 999.0
    data = client.post("/api/plume/grid", json=payload).json()
    assert data["source_term"]["emission_rate_g_s"] == 50.0
    assert data["wind"]["wind_speed_ms"] == 4.0
    assert data["background_conc_ug_m3"] == 10.0
    # 浓度场本身不因阈值而变
    ref = client.post("/api/plume/grid", json=_base_payload(bg=10.0)).json()
    assert np.allclose(
        np.array(data["plume_field_ug_m3"]),
        np.array(ref["plume_field_ug_m3"]),
    )
