"""水平/垂直弥散系数 sigma_y(x), sigma_z(x)。

显式参数化，所有系数在代码中可读、在 API 元数据中可检查，不使用查表插值黑箱。

提供两套方案：

1. ``briggs_rural``（默认）
   Briggs 开阔乡村系数（教学常用汇编值，单位：x 用 m，sigma 用 m）：

   sigma_y = k * x / (1 + a*x)^p
   sigma_z 按稳定度分段（同样 x 以 m 代入）：

   A (100 m <= x <= 10 km):  sigma_z = 0.20 * x
   B (100 m <= x <= 500 m):  sigma_z = 0.12 * x
     (x > 500 m):             sigma_z = 0.12 x + 0.0001*(x-500) ... 分段，见下
   C:  sigma_z = 0.08 x * (1 + 0.0002 x)^(-1/2)
   D:  sigma_z = 0.06 x * (1 + 0.0015 x)^(-1/2)
   E:  sigma_z = 0.03 x * (1 + 0.0003 x)^(-1)
   F:  sigma_z = 0.02 x * (1 + 0.0003 x)^(-1)

   参考：Briggs, G.A., *Diffusion Estimation for Small Emissions*, 1973；
   各类大气扩散教材中的 Briggs 乡村参数表。建议适用 x ≈ 100 m–10 km，
   超范围时结果仅作趋势演示。

2. ``power_law``（核对用）
   sigma_y = ay * x^py, sigma_z = az * x^pz
   纯幂律，便于与解析结论对照（例如峰值处 sigma_z = H/sqrt(2)）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Pasquill 稳定度等级
STABILITY_CLASSES = ("A", "B", "C", "D", "E", "F")

STABILITY_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "A": {"name_cn": "极不稳定", "pasquill": "强日照、微风"},
    "B": {"name_cn": "不稳定", "pasquill": "日照较强"},
    "C": {"name_cn": "弱不稳定", "pasquill": "中等日照"},
    "D": {"name_cn": "中性", "pasquill": "阴天/白天大风/夜间任意天空"},
    "E": {"name_cn": "较稳定", "pasquill": "夜间低云"},
    "F": {"name_cn": "稳定", "pasquill": "夜间晴空逆温"},
}

# sigma_y = k*x/(1+a*x)^p，a 中 x 以 m 计。系数为常见 Briggs 乡村汇编值。
BRIGGS_SY: dict[str, tuple[float, float, float]] = {
    # class: (k, a [1/m], p)
    "A": (0.22, 0.0001, 0.5),
    "B": (0.16, 0.0001, 0.5),
    "C": (0.11, 0.0001, 0.5),
    "D": (0.08, 0.0001, 0.5),
    "E": (0.06, 0.0001, 0.5),
    "F": (0.04, 0.0001, 0.5),
}

# sigma_z 公式参数与对应公式 id，见 _briggs_sz()
# B 类在 x=500 m 处分段
BRIGGS_B_BREAK_M = 500.0
BRIGGS_SZ: dict[str, dict] = {
    "A": {"form": "linear", "c": 0.20},
    "B": {"form": "b_piecewise"},
    "C": {"form": "pl_exp_half", "c": 0.08, "a": 0.0002},
    "D": {"form": "pl_exp_half", "c": 0.06, "a": 0.0015},
    "E": {"form": "pl_exp_one", "c": 0.03, "a": 0.0003},
    "F": {"form": "pl_exp_one", "c": 0.02, "a": 0.0003},
}

# 数值防奇异：下风向极近源处 sigma 趋近 0 时高斯式发散，
# 教学模型不计算烟囱出口截面，给一个下限并在诊断中标注。
SIGMA_FLOOR_M = 0.5


@dataclass(frozen=True)
class PowerLawParams:
    ay: float = 0.22
    py: float = 1.0
    az: float = 0.16
    pz: float = 1.0


DEFAULT_POWER_LAW = PowerLawParams()


def _briggs_sy(stability: str, x: np.ndarray) -> np.ndarray:
    k, a, p = BRIGGS_SY[stability]
    return np.maximum(SIGMA_FLOOR_M, k * x / np.power(1.0 + a * x, p))


def _briggs_sz(stability: str, x: np.ndarray) -> np.ndarray:
    spec = BRIGGS_SZ[stability]
    form = spec["form"]
    if form == "linear":
        sigma = spec["c"] * x
    elif form == "b_piecewise":
        # B 类：x<=500 m 时 0.12x；之后斜率变化并随距离放缓。
        # 采用 Briggs 汇编中常用的连续分段：0.12x (x<=500)，
        # 0.12x + 0.0001(x-500) 线性段（至约 5 km），更远用饱和式。
        x = np.asarray(x, dtype=float)
        sigma = np.where(
            x <= BRIGGS_B_BREAK_M,
            0.12 * x,
            0.12 * x + 0.0001 * (x - BRIGGS_B_BREAK_M),
        )
    elif form == "pl_exp_half":
        sigma = spec["c"] * x / np.sqrt(1.0 + spec["a"] * x)
    elif form == "pl_exp_one":
        sigma = spec["c"] * x / (1.0 + spec["a"] * x)
    else:  # pragma: no cover - 防御性分支
        raise ValueError(f"未知 sigma_z 形式: {form}")
    return np.maximum(SIGMA_FLOOR_M, sigma)


def dispersion_sigmas(
    x_m: np.ndarray,
    stability: str,
    parameterization: str = "briggs_rural",
    power_law: PowerLawParams | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """返回 (sigma_y, sigma_z)，单位 m。输入 x 单位 m，非正值给 SIGMA_FLOOR。

    Parameters
    ----------
    x_m:
        下风向距离数组（m）。x <= 0（上风向/源处）不参与烟羽主体，
        仍返回下限值以便统一掩码处理。
    stability:
        Pasquill 等级 A–F。
    parameterization:
        ``briggs_rural`` 或 ``power_law``。
    power_law:
        power_law 方案的系数。
    """
    s = stability.upper()
    if s not in STABILITY_CLASSES:
        raise ValueError(f"未知稳定度等级: {stability!r}，应为 A–F 之一")
    x = np.asarray(x_m, dtype=float)
    if parameterization == "briggs_rural":
        sy = _briggs_sy(s, np.maximum(x, 0.0))
        sz = _briggs_sz(s, np.maximum(x, 0.0))
    elif parameterization == "power_law":
        p = power_law or DEFAULT_POWER_LAW
        if p.ay <= 0 or p.az <= 0 or p.py <= 0 or p.pz <= 0:
            raise ValueError("幂律系数必须为正")
        xp = np.maximum(x, 0.0)
        sy = np.maximum(SIGMA_FLOOR_M, p.ay * np.power(xp, p.py))
        sz = np.maximum(SIGMA_FLOOR_M, p.az * np.power(xp, p.pz))
    else:
        raise ValueError(
            f"未知参数化方案 {parameterization!r}，"
            "应为 'briggs_rural' 或 'power_law'"
        )
    return sy, sz


def parameterization_metadata() -> list[dict]:
    """供 /api/meta 展示：把实际使用的系数完整列出，做到可检查。"""
    items: list[dict] = []
    for s in STABILITY_CLASSES:
        k, a, p = BRIGGS_SY[s]
        items.append(
            {
                "stability": s,
                "stability_cn": STABILITY_DESCRIPTIONS[s]["name_cn"],
                "sigma_y": f"{k}*x/(1+{a:g}*x)^{p}",
                "sigma_z_form": BRIGGS_SZ[s]["form"],
                "sigma_z_constants": {
                    key: val
                    for key, val in BRIGGS_SZ[s].items()
                    if key != "form"
                },
                "x_valid_range_m": [100.0, 10_000.0],
            }
        )
    return items
