"""平坦地形、稳态风条件下的高斯烟羽地面浓度模型。

在反射边界（地面全反射、无逆温盖）下，z=0 处浓度为：

    C(x, y, 0) = Q / (π u σ_y σ_z)
                 · exp(− y² / (2 σ_y²))
                 · exp(− H_e² / (2 σ_z²))

    Q: 源排放率（g/s）；u: 风速（m/s）
    H_e: 有效源高（m，烟囱高 + 抬升）
    x: 下风向距离；y: 横风向距离；σ 单位 m

乘 1e6 后输出 μg/m³。

限制（重要）：
* 稳态、平坦、定常排放；不模拟地形、建筑物下洗、干湿沉降、化学转化。
* 静风（u < 阈值）时输运假设失效，**不做除法**，直接报错，
  绝不用接近零的风速算出无意义的巨大浓度。
* 上风向 x <= 0 处置零；σ 有 0.5 m 下限，源点近场（建议 x < 100 m）
  结果不具物理意义，诊断中给出近场栅格计数。
"""
from __future__ import annotations

import math

import numpy as np

from .dispersion import (
    SIGMA_FLOOR_M,
    dispersion_sigmas,
)
from .geometry import local_to_plume_coords
from .units import GRAMS_TO_MICROGRAMS


class CalmWindError(ValueError):
    """风速低于静风阈值，高斯烟羽模型不适用。"""


class PlumeInputError(ValueError):
    """输入参数不合法。"""


def compute_plume_field(
    emission_rate_g_s: float,
    wind_speed_ms: float,
    wind_from_deg: float,
    stability_class: str,
    effective_height_m: float,
    east_m: np.ndarray,
    north_m: np.ndarray,
    parameterization: str = "briggs_rural",
    power_law: dict | None = None,
    calm_threshold_ms: float = 1.0,
    near_source_advisory_m: float = 100.0,
    briggs_valid_range_m: tuple[float, float] = (100.0, 10_000.0),
) -> dict:
    """计算采样网格上的**烟羽贡献**浓度（μg/m³，不含背景值）。

    east_m / north_m 为形状相同的二维数组（米，源为原点）。
    返回 dict：field（同形数组）、diagnostics。
    """
    # ---- 输入校验：静风是硬错误，绝不硬算 ----
    if wind_speed_ms is None or not np.isfinite(wind_speed_ms):
        raise PlumeInputError("风速缺失或非有限值")
    if wind_speed_ms < 0:
        raise PlumeInputError("风速不能为负")
    if wind_speed_ms < calm_threshold_ms:
        raise CalmWindError(
            f"风速 {wind_speed_ms:.3g} m/s 低于静风阈值 "
            f"{calm_threshold_ms:.3g} m/s：定常高斯烟羽的输运假设失效，"
            "本模型拒绝计算（不使用近零风速除出巨大浓度）。"
        )
    if emission_rate_g_s < 0:
        raise PlumeInputError("排放率不能为负")
    if effective_height_m < 0:
        raise PlumeInputError("有效源高不能为负")
    if not np.isfinite(wind_from_deg):
        raise PlumeInputError("风向非有限值")

    e = np.asarray(east_m, dtype=float)
    n = np.asarray(north_m, dtype=float)
    x, y = local_to_plume_coords(e, n, wind_from_deg)

    from .dispersion import PowerLawParams

    pl = PowerLawParams(**power_law) if power_law else None
    sigma_y, sigma_z = dispersion_sigmas(
        x, stability_class, parameterization, pl
    )

    downwind = x > 0.0
    # 高斯主公式（向量化）。先按零数组填，避免上风向参与指数运算。
    field = np.zeros_like(x)
    cross = np.exp(-(y**2) / (2.0 * sigma_y**2), where=downwind, out=np.zeros_like(x))
    vert = np.exp(
        -(effective_height_m**2) / (2.0 * sigma_z**2),
        where=downwind,
        out=np.zeros_like(x),
    )
    denom = math.pi * wind_speed_ms * sigma_y * sigma_z
    np.divide(
        emission_rate_g_s * GRAMS_TO_MICROGRAMS * cross * vert,
        denom,
        where=downwind,
        out=field,
    )
    # 数值保险
    field = np.where(np.isfinite(field), field, 0.0)
    field = np.maximum(field, 0.0)

    # ---- 诊断 ----
    valid_x_min, valid_x_max = briggs_valid_range_m
    near_mask = downwind & (x < near_source_advisory_m)
    oob_mask = downwind & ((x < valid_x_min) | (x > valid_x_max))
    max_idx = np.unravel_index(np.argmax(field), field.shape)
    diagnostics = {
        "calm_threshold_ms": calm_threshold_ms,
        "calm": bool(wind_speed_ms < calm_threshold_ms),
        "grid_shape": list(field.shape),
        "max_plume_conc_ug_m3": float(field[max_idx]),
        "max_location_east_north_m": [
            float(e[max_idx]),
            float(n[max_idx]),
        ],
        "max_location_downwind_crosswind_m": [
            float(x[max_idx]),
            float(y[max_idx]),
        ],
        "n_downwind_cells": int(np.count_nonzero(downwind)),
        "n_near_source_cells_lt_100m": int(np.count_nonzero(near_mask)),
        "n_out_of_briggs_range_cells": (
            int(np.count_nonzero(oob_mask))
            if parameterization == "briggs_rural"
            else 0
        ),
        "sigma_floor_m": SIGMA_FLOOR_M,
        "near_source_advisory_m": near_source_advisory_m,
        "plume_only_note": "本字段仅为烟羽贡献，背景浓度在结果中单独给出",
    }
    return {
        "field": field,
        "diagnostics": diagnostics,
        "x_downwind_m": x,
        "y_crosswind_m": y,
        "sigma_y_m": sigma_y,
        "sigma_z_m": sigma_z,
    }
