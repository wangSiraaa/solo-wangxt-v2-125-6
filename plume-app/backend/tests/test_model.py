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


# ---------------------------------------------------------------------------
# 课堂自定义浓度阈值统计（教学用途，非法定限值）
# ---------------------------------------------------------------------------

def test_threshold_stats_basic_metric_areas():
    """超阈值面积按各自网格实际米制间距逐单元计数，比例在 [0,1]。"""
    payload = _base_payload()
    payload["concentration_threshold_ug_m3"] = 30.0
    data = client.post("/api/plume/grid", json=payload).json()
    ts = data["threshold_stats"]
    assert ts["threshold_nature"] == "classroom_custom_non_regulatory"
    dx = data["grid"]["spacing_downwind_m"]
    dy = data["grid"]["spacing_crosswind_m"]
    cell = dx * dy
    for part in (ts["plume_contribution"], ts["total_concentration"]):
        assert part["cell_size_m2"] == pytest.approx(cell)
        assert part["exceeding_area_m2"] == pytest.approx(
            part["n_exceeding_cells"] * cell
        )
        assert part["sampling_frame_area_m2"] == pytest.approx(
            part["n_sampled_cells"] * cell
        )
        assert 0.0 <= part["exceeding_area_fraction"] <= 1.0
        # 单元数 = (nx-1)(ny-1)，面积自洽
        assert part["n_sampled_cells"] == (121 - 1) * (81 - 1)
    # 总浓度处处 >= 烟羽贡献，因此总浓度超阈面积不小于烟羽
    assert (
        ts["total_concentration"]["exceeding_area_m2"]
        >= ts["plume_contribution"]["exceeding_area_m2"]
    )
    # 独立用 numpy 复核单元判定（四角均值 > 阈值）
    plume = np.array(data["plume_field_ug_m3"])
    cm = 0.25 * (
        plume[:-1, :-1] + plume[:-1, 1:] + plume[1:, :-1] + plume[1:, 1:]
    )
    assert ts["plume_contribution"]["n_exceeding_cells"] == int(
        np.count_nonzero(cm > 30.0)
    )


def test_threshold_above_all_gives_zero_area():
    """阈值高于全部采样值：烟羽与总浓度的超阈值面积/格点均为 0。"""
    payload = _base_payload(bg=100.0)
    payload["concentration_threshold_ug_m3"] = 1.0e9
    data = client.post("/api/plume/grid", json=payload).json()
    ts = data["threshold_stats"]
    for part in (ts["plume_contribution"], ts["total_concentration"]):
        assert part["exceeding_area_m2"] == 0.0
        assert part["exceeding_area_fraction"] == 0.0
        assert part["n_exceeding_nodes"] == 0
        assert part["n_exceeding_cells"] == 0
        assert part["max_sampled_ug_m3"] < 1.0e9


def test_threshold_equality_is_strict_gt():
    """阈值恰好等于某常值场时不计入（严格大于口径）。"""
    # 背景 10、Q=0 -> 总浓度处处恰为 10
    payload = _base_payload(bg=10.0)
    payload["source"]["emission_rate_g_s"] = 0.0
    payload["concentration_threshold_ug_m3"] = 10.0
    data = client.post("/api/plume/grid", json=payload).json()
    tot = data["threshold_stats"]["total_concentration"]
    assert tot["n_exceeding_nodes"] == 0
    assert tot["exceeding_area_fraction"] == 0.0


def test_background_only_changes_total_stats():
    """背景升高：烟羽贡献统计完全不变，总浓度统计增大。"""
    def stats_for(bg):
        payload = _base_payload(bg=bg)
        payload["concentration_threshold_ug_m3"] = 30.0
        return client.post("/api/plume/grid", json=payload).json()["threshold_stats"]

    a = stats_for(0.0)
    b = stats_for(120.0)
    assert a["plume_contribution"] == b["plume_contribution"]
    assert (
        b["total_concentration"]["exceeding_area_fraction"]
        > a["total_concentration"]["exceeding_area_fraction"]
    )
    assert b["total_concentration"]["exceeding_area_fraction"] <= 1.0
    # 背景 120 本身已超阈 -> 全部单元超阈
    assert b["total_concentration"]["n_exceeding_cells"] == (
        b["total_concentration"]["n_sampled_cells"]
    )


def test_threshold_stats_null_without_field():
    """不提供阈值时 threshold_stats 为 null，且静风下不会出现统计。"""
    data = client.post("/api/plume/grid", json=_base_payload()).json()
    assert data["threshold_stats"] is None

    calm = _base_payload(wind_speed=0.3)
    calm["concentration_threshold_ug_m3"] = 1.0
    r = client.post("/api/plume/grid", json=calm)
    assert r.status_code == 422 and r.json()["error"] == "calm_wind"


def test_threshold_stats_recomputed_per_resolution_without_writeback():
    """切换粗细网格：源/气象回传不变，阈值统计按各自间距重新计算。"""
    def grid_run(nx, ny):
        payload = _base_payload()
        payload["grid"]["nx"], payload["grid"]["ny"] = nx, ny
        payload["concentration_threshold_ug_m3"] = 30.0
        return client.post("/api/plume/grid", json=payload).json()

    fine = grid_run(121, 81)
    coarse = grid_run(41, 31)
    # 源项与气象不被回写：有效源高（无抬升=几何高）与风一致
    assert fine["effective_stack_height_m"] == coarse["effective_stack_height_m"]
    assert fine["wind"]["wind_speed_ms"] == coarse["wind"]["wind_speed_ms"]
    assert fine["background_conc_ug_m3"] == coarse["background_conc_ug_m3"]
    # 同一物理格点（x=1000m 中线附近）浓度与分辨率无关
    ix_f, iy_f = 60, 40
    ix_c, iy_c = 20, 15
    assert fine["grid"]["x_edges_m"][ix_f] == pytest.approx(
        coarse["grid"]["x_edges_m"][ix_c]
    )
    assert fine["plume_field_ug_m3"][iy_f][ix_f] == pytest.approx(
        coarse["plume_field_ug_m3"][iy_c][ix_c]
    )
    # 统计按各自网格重算：单元面积不同，总面积相等，超阈面积接近但不要求相等
    pf, pc = (fine["threshold_stats"]["total_concentration"],
              coarse["threshold_stats"]["total_concentration"])
    assert pf["cell_size_m2"] != pc["cell_size_m2"]
    assert pf["spacing_downwind_m"] != pc["spacing_downwind_m"]
    assert pf["sampling_frame_area_m2"] == pytest.approx(
        pc["sampling_frame_area_m2"], rel=1e-9
    )
    assert abs(pf["exceeding_area_fraction"] - pc["exceeding_area_fraction"]) < 0.05


def test_threshold_out_of_range_node_counts():
    """Briggs 建议范围（100 m–10 km）外节点计数；幂律下置 null。"""
    payload = _base_payload()
    payload["concentration_threshold_ug_m3"] = 1.0
    data = client.post("/api/plume/grid", json=payload).json()
    adv = data["threshold_stats"]["plume_contribution"]["model_advisory"]
    assert adv["briggs_suggested_range_m"] == [100.0, 10_000.0]
    assert adv["n_out_of_range_nodes_total"] >= 0
    assert (
        adv["n_out_of_range_nodes_exceeding"]
        <= adv["n_out_of_range_nodes_total"]
    )
    # 与既有诊断口径一致（同一下风向范围判定）
    assert adv["n_out_of_range_nodes_total"] == data["diagnostics"][
        "n_out_of_briggs_range_cells"
    ]

    pl = _base_payload()
    pl["parameterization"] = "power_law"
    pl["power_law"] = {"ay": 0.22, "py": 1.0, "az": 0.16, "pz": 1.0}
    pl["concentration_threshold_ug_m3"] = 1.0
    pdata = client.post("/api/plume/grid", json=pl).json()
    padv = pdata["threshold_stats"]["plume_contribution"]["model_advisory"]
    assert padv["n_out_of_range_nodes_total"] is None
    assert pdata["threshold_stats"]["power_law_advisory_note"]


def test_threshold_invalid_value_rejected():
    payload = _base_payload()
    payload["concentration_threshold_ug_m3"] = -1.0
    r = client.post("/api/plume/grid", json=payload)
    assert r.status_code == 422
