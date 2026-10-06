"""把模型组装为可复用的计算服务（网格与单点）。"""
from __future__ import annotations

import math

import numpy as np

from .config import settings
from .dispersion import STABILITY_CLASSES, parameterization_metadata
from .gaussian import CalmWindError, PlumeInputError, compute_plume_field
from .geometry import (
    local_to_lonlat,
    local_to_plume_coords,
    lonlat_to_local,
    transport_bearing_deg,
    wind_transform_check,
)
from .plume_rise import holland_plume_rise
from .schemas import (
    GridSpec,
    MeteorologyInput,
    PlumeGridRequest,
    SourceInput,
)

DISCLAIMER = (
    "教学演示结果：基于平坦地形、稳态风、定常排放的解析高斯烟羽模型，"
    "不含地形、建筑物下洗、沉降与化学反应。不得用于真实事故预警或法规达标判定。"
)


def merge_overrides(req: PlumeGridRequest) -> tuple[SourceInput, MeteorologyInput]:
    """把临时 override 合并到源/气象副本上；原始输入对象不变。"""
    src = req.source.model_copy(deep=True)
    met = req.meteorology.model_copy(deep=True)
    if req.source_override is not None:
        for key, val in req.source_override.model_dump(exclude_none=True).items():
            setattr(src, key, val)
    if req.met_override is not None:
        for key, val in req.met_override.model_dump(exclude_none=True).items():
            setattr(met, key, val)
    return src, met


def effective_height(src: SourceInput, met: MeteorologyInput, use_rise: bool) -> tuple[float, dict]:
    """计算有效源高；返回 (H_e, 抬升明细)。"""
    if not use_rise:
        return src.stack_height_m, {"delta_h_m": 0.0, "used": False}
    detail = holland_plume_rise(
        exit_velocity_ms=src.exit_velocity_ms,
        stack_diameter_m=src.stack_diameter_m,
        wind_speed_ms=met.wind_speed_ms,
        stack_temp_k=src.stack_temp_k,
        ambient_temp_k=met.ambient_temp_k,
        pressure_hpa=met.pressure_hpa,
    )
    detail["used"] = True
    return src.stack_height_m + detail["delta_h_m"], detail


def build_sampling_grid(spec: GridSpec, wind_from_deg: float, lon0: float, lat0: float) -> dict:
    """在烟羽坐标 (x 下风向, y 横风向) 上建采样矩形，再转回经纬度。

    返回 E/N 二维网格、角点（经纬度+米）和间距。分辨率只影响采样，
    不触碰任何源/气象输入。
    """
    x = np.linspace(-spec.upwind_extent_m, spec.downwind_extent_m, spec.nx)
    y = np.linspace(-spec.crosswind_extent_m / 2.0, spec.crosswind_extent_m / 2.0, spec.ny)
    xx, yy = np.meshgrid(x, y)  # 行=y, 列=x

    theta = math.radians(transport_bearing_deg(wind_from_deg))
    # 烟羽坐标 -> 局部 E/N（local_to_plume_coords 的逆）
    east = xx * math.sin(theta) + yy * math.cos(theta)
    north = xx * math.cos(theta) - yy * math.sin(theta)

    lon_grid, lat_grid = local_to_lonlat(east, north, lon0, lat0)

    corners = []
    for (cx, cy) in [
        (x[0], y[0]),
        (x[-1], y[0]),
        (x[-1], y[-1]),
        (x[0], y[-1]),
    ]:
        ce = cx * math.sin(theta) + cy * math.cos(theta)
        cn = cx * math.cos(theta) - cy * math.sin(theta)
        clon, clat = local_to_lonlat(ce, cn, lon0, lat0)
        corners.append(
            {
                "plume_x_y_m": [float(cx), float(cy)],
                "east_north_m": [float(ce), float(cn)],
                "lonlat": [float(clon), float(clat)],
            }
        )

    dx = (spec.downwind_extent_m + spec.upwind_extent_m) / (spec.nx - 1)
    dy = spec.crosswind_extent_m / (spec.ny - 1)
    flat_scale = max(
        spec.downwind_extent_m + spec.upwind_extent_m,
        spec.crosswind_extent_m,
    )
    return {
        "x_edges_m": x.tolist(),
        "y_edges_m": y.tolist(),
        "east_m": east,
        "north_m": north,
        "lon_grid": lon_grid,
        "lat_grid": lat_grid,
        "corners": corners,
        "nx": spec.nx,
        "ny": spec.ny,
        "spacing_downwind_m": float(dx),
        "spacing_crosswind_m": float(dy),
        "flat_earth_scale_m": float(flat_scale),
        "flat_earth_advisory_m": settings.flat_earth_advisory_m,
        "flat_earth_warning": flat_scale > settings.flat_earth_advisory_m,
    }


def iso_levels(max_value: float, n_levels: int = 8) -> list[float]:
    """以 1-2-5 ×10^k 生成友好等值级，始终包含 0 以上的正级；
    最大浓度为零时返回空列表。"""
    if max_value <= 0 or not np.isfinite(max_value):
        return []
    hi_exp = math.floor(math.log10(max_value))
    mantissas = [1.0, 2.0, 5.0]
    levels: list[float] = []
    for e in range(hi_exp - 4, hi_exp + 1):
        for m in mantissas:
            v = m * 10.0**e
            if v < max_value:
                levels.append(v)
    # 去重保序，控制数量
    out: list[float] = []
    for v in levels:
        if not out or abs(v - out[-1]) / v > 1e-9:
            out.append(v)
    return out[-n_levels:]


def run_grid(req: PlumeGridRequest) -> dict:
    """完整的网格计算流程；静风/非法输入向上抛 CalmWindError/PlumeInputError。"""
    spec = req.grid
    if (
        (spec.downwind_extent_m + spec.upwind_extent_m) / max(spec.nx - 1, 1)
        < settings.grid_min_spacing_m
        or spec.crosswind_extent_m / max(spec.ny - 1, 1)
        < settings.grid_min_spacing_m
    ):
        raise PlumeInputError(
            f"采样间距不能小于 {settings.grid_min_spacing_m:g} m"
        )

    src, met = merge_overrides(req)
    h_eff, rise_detail = effective_height(src, met, req.plume_rise.use_plume_rise)
    grid = build_sampling_grid(spec, met.wind_from_deg, src.lon, src.lat)

    result = compute_plume_field(
        emission_rate_g_s=src.emission_rate_g_s,
        wind_speed_ms=met.wind_speed_ms,
        wind_from_deg=met.wind_from_deg,
        stability_class=met.stability_class,
        effective_height_m=h_eff,
        east_m=grid["east_m"],
        north_m=grid["north_m"],
        parameterization=req.parameterization,
        power_law=req.power_law,
        calm_threshold_ms=req.calm_threshold_ms,
    )
    plume = result["field"]
    bg = met.background_conc_ug_m3
    total = plume + bg

    return {
        "source_lonlat": [src.lon, src.lat],
        "crs_note": (
            "经纬度 EPSG:4326；内部为以源为原点的局部等距圆柱平面(米)，"
            "小尺度平坦地形近似，建议采样尺度 ≤ 30 km"
        ),
        "grid": {
            "nx": grid["nx"],
            "ny": grid["ny"],
            "x_edges_m": grid["x_edges_m"],
            "y_edges_m": grid["y_edges_m"],
            "lon_grid": np.asarray(grid["lon_grid"]).tolist(),
            "lat_grid": np.asarray(grid["lat_grid"]).tolist(),
            "spacing_downwind_m": grid["spacing_downwind_m"],
            "spacing_crosswind_m": grid["spacing_crosswind_m"],
            "corners_lonlat": [c["lonlat"] for c in grid["corners"]],
            "sampling_extent_lonlat": {
                "lon_min": float(np.min(grid["lon_grid"])),
                "lon_max": float(np.max(grid["lon_grid"])),
                "lat_min": float(np.min(grid["lat_grid"])),
                "lat_max": float(np.max(grid["lat_grid"])),
            },
            "flat_earth_warning": grid["flat_earth_warning"],
            "resolution_disclaimer": (
                "等值面为有限采样网格上的估计值，网格间距 "
                f"{grid['spacing_downwind_m']:.0f}(下风向)/"
                f"{grid['spacing_crosswind_m']:.0f}(横风向) m；"
                "不代表网格之外或亚网格尺度的浓度"
            ),
        },
        "plume_field_ug_m3": plume.tolist(),
        "background_conc_ug_m3": float(bg),
        "total_conc_ug_m3": total.tolist(),
        "iso_levels_ug_m3": iso_levels(float(plume.max())),
        "effective_stack_height_m": float(h_eff),
        "plume_rise_delta_h_m": float(rise_detail["delta_h_m"]),
        "wind": {
            **wind_transform_check(met.wind_from_deg),
            "wind_speed_ms": met.wind_speed_ms,
            "stability_class": met.stability_class,
        },
        "source_term": {
            "name": src.name,
            "pollutant": src.pollutant,
            "emission_rate_g_s": src.emission_rate_g_s,
            "stack_height_m": src.stack_height_m,
            "stack_diameter_m": src.stack_diameter_m,
            "exit_velocity_ms": src.exit_velocity_ms,
            "stack_temp_k": src.stack_temp_k,
            "plume_rise_detail": rise_detail,
        },
        "diagnostics": result["diagnostics"],
        "validity": {
            "model": "steady-state Gaussian plume, flat terrain, full ground reflection",
            "assumptions": [
                "定常排放、稳态风、平坦均一下垫面",
                "污染物守恒（无沉降、无化学转化、无建筑物下洗）",
                "浓度在横风向与垂直方向服从高斯分布",
            ],
            "parameterizations": parameterization_metadata(),
            "briggs_valid_range_m": [
                settings.briggs_valid_x_min_m,
                settings.briggs_valid_x_max_m,
            ],
            "stability_classes": list(STABILITY_CLASSES),
        },
        "disclaimer": DISCLAIMER,
    }


def run_points(req: "PlumePointRequest") -> list[dict]:
    """在任意经纬度点上求值（核对用），与采样网格完全无关。"""
    src, met = merge_overrides(req)
    h_eff, rise_detail = effective_height(src, met, req.plume_rise.use_plume_rise)
    out = []
    for lon, lat in req.points:
        e, n = lonlat_to_local(lon, lat, src.lon, src.lat)
        ea = np.array([[e]])
        na = np.array([[n]])
        result = compute_plume_field(
            emission_rate_g_s=src.emission_rate_g_s,
            wind_speed_ms=met.wind_speed_ms,
            wind_from_deg=met.wind_from_deg,
            stability_class=met.stability_class,
            effective_height_m=h_eff,
            east_m=ea,
            north_m=na,
            parameterization=req.parameterization,
            power_law=req.power_law,
            calm_threshold_ms=req.calm_threshold_ms,
        )
        x = float(result["x_downwind_m"][0, 0])
        y = float(result["y_crosswind_m"][0, 0])
        plume = float(result["field"][0, 0])
        out.append(
            {
                "lonlat": [lon, lat],
                "east_north_m": [e, n],
                "downwind_crosswind_m": [x, y],
                "plume_conc_ug_m3": plume,
                "background_conc_ug_m3": met.background_conc_ug_m3,
                "total_conc_ug_m3": plume + met.background_conc_ug_m3,
                "sigma_y_m": float(result["sigma_y_m"][0, 0]),
                "sigma_z_m": float(result["sigma_z_m"][0, 0]),
            }
        )
    return out
