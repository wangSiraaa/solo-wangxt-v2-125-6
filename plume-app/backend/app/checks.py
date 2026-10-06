"""解析核对用例（analytical verification cases）。

每一条都给出期望值、实际值与容差，通过 /api/checks 暴露给界面，
也被 pytest 复用。覆盖需求中的四类核对：

* 解析对称性：横风向 C(x,y)=C(x,-y)；横风向比值严格等于高斯因子。
* 下风向衰减：中心线过峰值后单调衰减。
* 源高变化：Q 与线性幂律下 C_max ∝ 1/H²、x_peak ∝ H；
  高烟囱近-中距离地面浓度更低。
* 附加：Q 线性、单位换算 1e6、风向旋转不变性、
  分辨率不改变固定点物理值、静风必须被拒绝。
"""
from __future__ import annotations

import math

import numpy as np

from .gaussian import CalmWindError, compute_plume_field
from .geometry import local_to_lonlat

# 核对用例固定参数（显式列出，可手算复核）
LON0, LAT0 = 116.40, 39.90
Q_G_S = 50.0
U_MS = 4.0
H_M = 60.0
STAB = "D"
WIND_FROM = 0.0  # 北风，烟羽向南，便于手算


def _field_along(points_x, points_y, *, h=H_M, q=Q_G_S, u=U_MS,
                 stab=STAB, wind_from=WIND_FROM,
                 parameterization="briggs_rural", power_law=None):
    """在给定烟羽坐标点数组上直接算浓度（μg/m³），绕开 API 层。"""
    theta = math.radians((wind_from + 180.0) % 360.0)
    x = np.asarray(points_x, dtype=float)
    y = np.asarray(points_y, dtype=float)
    east = x * math.sin(theta) + y * math.cos(theta)
    north = x * math.cos(theta) - y * math.sin(theta)
    res = compute_plume_field(
        emission_rate_g_s=q,
        wind_speed_ms=u,
        wind_from_deg=wind_from,
        stability_class=stab,
        effective_height_m=h,
        east_m=east,
        north_m=north,
        parameterization=parameterization,
        power_law=power_law,
        calm_threshold_ms=1.0,
        near_source_advisory_m=1.0,
        briggs_valid_range_m=(1.0, 1.0e9),
    )
    return res["field"], res


def _result(cid, title, description, passed, expected, actual, tol=None, extra=None):
    return {
        "id": cid,
        "title": title,
        "description": description,
        "passed": bool(passed),
        "expected": expected,
        "actual": actual,
        "tolerance": tol,
        "extra": extra or {},
    }


def check_crosswind_symmetry() -> dict:
    x0 = 800.0
    ys = np.linspace(50, 900, 12)
    c_pos, _ = _field_along(np.full_like(ys, x0), ys)
    c_neg, _ = _field_along(np.full_like(ys, x0), -ys)
    rel = np.max(np.abs(c_pos - c_neg) / np.maximum(c_pos, 1e-30))
    return _result(
        "symmetry",
        "横风向解析对称性",
        "同一 x 上 C(x, +y) 必须等于 C(x, −y)。",
        rel < 1e-10,
        "max 相对差 = 0",
        f"max 相对差 = {rel:.2e}",
        1e-10,
        {"x_m": x0, "y_values_m": ys.tolist()},
    )


def check_crosswind_gaussian_ratio() -> dict:
    x0 = 1000.0
    y0 = 150.0
    vals, res = _field_along(np.array([x0, x0, x0]), np.array([0.0, y0, -y0]))
    c0, cy = vals[0], vals[1]
    sy = float(res["sigma_y_m"][0])
    expected_ratio = math.exp(-(y0**2) / (2.0 * sy**2))
    actual_ratio = float(cy / c0)
    relerr = abs(actual_ratio - expected_ratio) / expected_ratio
    return _result(
        "gaussian_ratio",
        "横风向高斯比值",
        "C(x,y)/C(x,0) 必须严格等于 exp(−y²/(2σ_y²))。",
        relerr < 1e-9,
        f"exp(...)={expected_ratio:.6f}",
        f"浓度比 ={actual_ratio:.6f}",
        1e-9,
        {"x_m": x0, "y_m": y0, "sigma_y_m": sy},
    )


def check_downwind_decay() -> dict:
    xs = np.linspace(500, 60000, 1200)
    c, res = _field_along(xs, np.zeros_like(xs))
    peak_i = int(np.argmax(c))
    tail = c[peak_i:]
    decreasing = bool(np.all(np.diff(tail) <= 1e-15))
    ratio_at = lambda d: float(c[np.argmin(np.abs(xs - d))] / c[peak_i])
    return _result(
        "downwind_decay",
        "下风向衰减",
        "中心线浓度过峰值后必须单调下降，40 km 处远低于峰值"
        "（远距离已超出 Briggs 建议 10 km 区间，仅作趋势核对）。",
        decreasing and ratio_at(40000.0) < 0.03,
        "单调递减且 40 km 处 < 峰值 3%",
        f"单调={decreasing}；C(30km)/Cmax={ratio_at(30000.0):.4f}，"
        f"C(40km)/Cmax={ratio_at(40000.0):.4f}",
        0.03,
        {"peak_x_m": float(xs[peak_i]), "peak_c": float(c[peak_i])},
    )


def check_source_height() -> dict:
    """线性幂律下解析结论：x_peak = H/(√2·az)，C_max = 2Q·az/(π e u ay H²)。"""
    pl = {"ay": 0.22, "py": 1.0, "az": 0.16, "pz": 1.0}
    xs = np.linspace(50, 4000, 20000)
    out = {}
    rows = []
    for h in (40.0, 80.0):
        c, _ = _field_along(
            xs, np.zeros_like(xs), h=h,
            parameterization="power_law", power_law=pl,
        )
        i = int(np.argmax(c))
        out[h] = (float(xs[i]), float(c[i]))
        x_peak_theory = h / (math.sqrt(2.0) * pl["az"])
        cmax_theory = (
            2.0 * Q_G_S * 1.0e6 * pl["az"]
            / (math.pi * math.e * U_MS * pl["ay"] * h**2)
        )
        rows.append(
            {
                "h_m": h,
                "x_peak_numeric_m": out[h][0],
                "x_peak_theory_m": x_peak_theory,
                "cmax_numeric_ug_m3": out[h][1],
                "cmax_theory_ug_m3": cmax_theory,
            }
        )
    x_ratio = out[40][0] / out[80][0]
    c_ratio = out[80][1] / out[40][1]  # 高度加倍，峰值约为 1/4
    loc_ok = all(
        abs(r["x_peak_numeric_m"] - r["x_peak_theory_m"])
        / r["x_peak_theory_m"] < 0.02
        for r in rows
    )
    c_ok = all(
        abs(r["cmax_numeric_ug_m3"] - r["cmax_theory_ug_m3"])
        / r["cmax_theory_ug_m3"] < 0.02
        for r in rows
    )
    return _result(
        "source_height",
        "源高变化（解析峰值）",
        "线性幂律 σz=az·x 时 x_peak=H/(√2·az)、"
        "C_max=2Q·az/(π e u ay H²)：H 加倍则 x_peak 加倍、C_max 变 1/4。",
        loc_ok and c_ok and abs(x_ratio - 0.5) < 0.03 and abs(c_ratio - 0.25) < 0.03,
        "x_peak(40)/x_peak(80)=0.5；Cmax(80)/Cmax(40)=0.25",
        f"x_peak 比={x_ratio:.3f}；Cmax 比={c_ratio:.3f}",
        0.03,
        {"rows": rows},
    )


def check_emission_linearity() -> dict:
    x0 = np.array([700.0])
    y0 = np.array([0.0])
    c1, _ = _field_along(x0, y0, q=Q_G_S)
    c2, _ = _field_along(x0, y0, q=2 * Q_G_S)
    ratio = float(c2[0] / c1[0])
    return _result(
        "emission_linearity",
        "排放率线性",
        "Q 加倍则各点浓度加倍（高斯式对 Q 线性）。",
        abs(ratio - 2.0) < 1e-9,
        "2.0",
        f"{ratio:.6f}",
        1e-9,
    )


def check_units() -> dict:
    """手算一点：与公式直接代入（g→μg ×1e6）核对。"""
    x0, y0 = 600.0, 0.0
    vals, res = _field_along(np.array([x0]), np.array([y0]))
    sy = float(res["sigma_y_m"][0])
    sz = float(res["sigma_z_m"][0])
    manual = (
        Q_G_S * 1.0e6
        / (math.pi * U_MS * sy * sz)
        * math.exp(-(H_M**2) / (2.0 * sz**2))
    )
    relerr = abs(float(vals[0]) - manual) / manual
    return _result(
        "units",
        "单位与公式逐项核对",
        "Q=g/s 乘 1e6 输出 μg/m³；手算 πuσyσz 分母项。",
        relerr < 1e-9,
        f"{manual:.4f} μg/m³",
        f"{float(vals[0]):.4f} μg/m³",
        1e-9,
        {"sigma_y_m": sy, "sigma_z_m": sz},
    )


def check_rotation_invariance() -> dict:
    """同一烟羽坐标 (x,y)，在不同风向下经经纬度映射求值，浓度必须相同。"""
    x_p, y_p = 900.0, 120.0
    values = []
    detail = []
    for wf in (0.0, 90.0, 137.0, 270.0):
        theta = math.radians((wf + 180.0) % 360.0)
        e = x_p * math.sin(theta) + y_p * math.cos(theta)
        n = x_p * math.cos(theta) - y_p * math.sin(theta)
        lon, lat = local_to_lonlat(e, n, LON0, LAT0)
        from .geometry import lonlat_to_local

        e2, n2 = lonlat_to_local(lon, lat, LON0, LAT0)
        res = compute_plume_field(
            Q_G_S, U_MS, wf, STAB, H_M,
            np.array([[e2]]), np.array([[n2]]),
            calm_threshold_ms=1.0,
            near_source_advisory_m=1.0,
            briggs_valid_range_m=(1.0, 1.0e9),
        )
        values.append(float(res["field"][0, 0]))
        detail.append({"wind_from_deg": wf, "lonlat": [lon, lat],
                       "c_ug_m3": values[-1]})
    spread = (max(values) - min(values)) / max(values)
    return _result(
        "rotation_invariance",
        "风向旋转不变性 + 坐标换算闭环",
        "烟羽坐标相同的点，无论风向如何（经局部平面↔经纬度闭环映射），浓度相同。",
        spread < 1e-9,
        "各风向值相同（相对极差 0）",
        f"相对极差 {spread:.2e}",
        1e-9,
        {"points": detail},
    )


def check_calm_wind() -> dict:
    rejected = False
    message = ""
    try:
        _field_along(np.array([500.0]), np.array([0.0]), u=0.3)
    except CalmWindError as exc:
        rejected = True
        message = str(exc)
    # 显式确认：静风分支没有执行任何除法/返回数值
    return _result(
        "calm_wind",
        "静风拒绝硬算",
        "u=0.3 m/s < 阈值 1.0 m/s 时模型必须拒绝计算，"
        "不得用近零风速除出巨大浓度。",
        rejected,
        "抛出 CalmWindError",
        message[:80] + ("…" if len(message) > 80 else ""),
    )


def check_resolution_independence() -> dict:
    """固定物理点的值由模型决定，与采样网格分辨率无关。

    取烟羽坐标 x=1000 m（两种网格下都是格点）、y=0，
    粗网格(21×5)与细网格(41×9)在该点的值必须一致。
    """
    from .schemas import (
        GridSpec,
        MeteorologyInput,
        PlumeGridRequest,
        SourceInput,
    )
    from .services import run_grid

    src = SourceInput(
        name="核对源", lon=LON0, lat=LAT0,
        stack_height_m=H_M, emission_rate_g_s=Q_G_S,
    )
    met = MeteorologyInput(
        name="核对气象", wind_from_deg=0.0, wind_speed_ms=U_MS,
        stability_class="D", background_conc_ug_m3=2.0,
    )
    vals = []
    for nx, ny in ((21, 5), (41, 9)):
        req = PlumeGridRequest(
            source=src, meteorology=met,
            grid=GridSpec(
                downwind_extent_m=2000.0, crosswind_extent_m=400.0,
                upwind_extent_m=0.0, nx=nx, ny=ny,
            ),
        )
        out = run_grid(req)
        # x 从 0 起、x=1000 m 恰为中间格点；y=0 为中心行
        ix = (nx - 1) // 2
        iy = (ny - 1) // 2
        vals.append(out["plume_field_ug_m3"][iy][ix])
    rel = abs(vals[1] - vals[0]) / max(vals[0], 1e-30)
    return _result(
        "resolution_independence",
        "网格分辨率不改变物理值",
        "同一物理格点在 200 m 间距与 100 m 间距网格中的浓度必须相同；"
        "网格只是采样方式（背景值也单独相加，不随分辨率变化）。",
        rel < 1e-12,
        "两网格同点浓度相等",
        f"粗={vals[0]:.6f}，细={vals[1]:.6f}，相对差 {rel:.2e}",
        1e-12,
    )


def check_background_separate() -> dict:
    from .schemas import (
        GridSpec,
        MeteorologyInput,
        PlumeGridRequest,
        SourceInput,
    )
    from .services import run_grid

    bg = 7.5
    src = SourceInput(
        name="核对源", lon=LON0, lat=LAT0,
        stack_height_m=H_M, emission_rate_g_s=Q_G_S,
    )
    met = MeteorologyInput(
        name="核对气象", wind_from_deg=270.0, wind_speed_ms=U_MS,
        stability_class="C", background_conc_ug_m3=bg,
    )
    out = run_grid(
        PlumeGridRequest(source=src, meteorology=met,
                         grid=GridSpec(nx=11, ny=11))
    )
    plume = np.array(out["plume_field_ug_m3"])
    total = np.array(out["total_conc_ug_m3"])
    max_err = float(np.max(np.abs(total - (plume + bg))))
    return _result(
        "background_separate",
        "背景值分开计量",
        "total = plume + background 处处成立，背景值为空间常数，独立返回。",
        max_err < 1e-9,
        "max |total − plume − bg| = 0",
        f"max 偏差 {max_err:.2e} μg/m³",
        1e-9,
        {"background_ug_m3": bg},
    )


ALL_CHECKS = [
    check_crosswind_symmetry,
    check_crosswind_gaussian_ratio,
    check_downwind_decay,
    check_source_height,
    check_emission_linearity,
    check_units,
    check_rotation_invariance,
    check_calm_wind,
    check_resolution_independence,
    check_background_separate,
]


def run_all_checks() -> dict:
    results = [fn() for fn in ALL_CHECKS]
    return {
        "title": "高斯烟羽模型解析核对",
        "all_passed": all(r["passed"] for r in results),
        "n_passed": sum(r["passed"] for r in results),
        "n_total": len(results),
        "results": results,
        "note": "核对参数固定：Q=50 g/s, u=4 m/s, H=60 m, D 类，"
        "另在线性幂律(ay=0.22, az=0.16)下核对源高解析解。",
    }
