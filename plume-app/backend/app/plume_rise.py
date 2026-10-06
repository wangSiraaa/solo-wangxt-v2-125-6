"""烟气抬升高度 Δh（Holland, 1953，US EPA 经典教学公式）。

    Δh = v_s d / u * [1.5 + 2.68e-3 * P * (T_s - T_a)/T_s * d]

    v_s: 烟气出口流速 m/s；d: 出口内径 m；u: 烟囱口高度处风速 m/s
    P:   大气压 hPa；T_s, T_a: 烟气、环境温度 K
    2.68e-3 的量纲为 1/hPa。

仅作教学演示；Δh 可为正（浮力/动力抬升），公式截断为不小于 0。
有效源高 H_e = h_s + Δh。
"""
from __future__ import annotations

HOLLAND_PRESSURE_FACTOR = 2.68e-3  # 1/hPa


def holland_plume_rise(
    exit_velocity_ms: float,
    stack_diameter_m: float,
    wind_speed_ms: float,
    stack_temp_k: float,
    ambient_temp_k: float,
    pressure_hpa: float,
) -> dict:
    """返回抬升高度与分项，便于在界面上解释 Δh 来源。"""
    if wind_speed_ms <= 0:
        raise ZeroDivisionError("抬升公式中风速不能为零")
    if stack_temp_k <= 0:
        raise ValueError("烟气温度必须为正值（K）")
    momentum_term = exit_velocity_ms * stack_diameter_m / wind_speed_ms
    buoyancy_bracket = (
        1.5
        + HOLLAND_PRESSURE_FACTOR
        * pressure_hpa
        * (stack_temp_k - ambient_temp_k)
        / stack_temp_k
        * stack_diameter_m
    )
    delta_h = max(0.0, momentum_term * buoyancy_bracket)
    return {
        "delta_h_m": delta_h,
        "momentum_term_vd_over_u": momentum_term,
        "buoyancy_bracket": buoyancy_bracket,
        "effective_stack_height_note": "H_e = h_s + delta_h",
    }
