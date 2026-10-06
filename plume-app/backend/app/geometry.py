"""风向与地图坐标换算，全部中间量可检查。

约定（在 API 文档 / 前端换算检查器中同步展示）：

* 地图坐标：经度 lon（东为正）、纬度 lat（北为正），EPSG:4326。
* 平面坐标：以源为原点的右手局部坐标，E 向东(米)，N 向北(米)。
* 风向 ``wind_from_deg`` 为气象学风向：**风从哪个方向吹来**，
  0=北来风, 90=东来风, 180=南来风, 270=西来风。
* 烟羽输运方向（风吹去的方位角）= (wind_from_deg + 180) % 360。
* 平坦地形、小尺度（建议 < 30 km），用等距圆柱平面近似：
    E = (lon - lon0) * R * cos(lat0_rad)
    N = (lat - lat0) * R
  R = 6_371_000 m。尺度更大时需换用正式投影——本教学应用不做。
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def wrap_360(angle_deg: float) -> float:
    """规整到 [0, 360)。"""
    return angle_deg % 360.0


def transport_bearing_deg(wind_from_deg: float) -> float:
    """气象来向角 -> 烟羽输运方位角（风吹去的方向，0=北，顺时针）。"""
    return wrap_360(wind_from_deg + 180.0)


def wind_unit_vectors(wind_from_deg: float) -> dict[str, tuple[float, float]]:
    """返回下风向与横风向单位向量（分量为 (E, N)），供核对。

    下风向 d = (sin θ, cos θ)，θ 为输运方位角；
    横风向 c = (cos θ, -sin θ)，风从左向右吹时 y 正向在风的左侧。
    由 c·d = 0、|c|=1 可直接验证正交归一。
    """
    theta = math.radians(transport_bearing_deg(wind_from_deg))
    downwind = (math.sin(theta), math.cos(theta))
    crosswind = (math.cos(theta), -math.sin(theta))
    return {"downwind": downwind, "crosswind": crosswind}


def lonlat_to_local(
    lon,
    lat,
    lon0: float,
    lat0: float,
):
    """经纬度 -> 以 (lon0, lat0) 为原点的局部平面坐标 (E, N)，米。

    标量或 numpy 数组均可。
    """
    import numpy as np

    lat0_rad = np.radians(lat0)
    east = np.radians(lon - lon0) * EARTH_RADIUS_M * np.cos(lat0_rad)
    north = np.radians(lat - lat0) * EARTH_RADIUS_M
    return east, north


def local_to_lonlat(
    east,
    north,
    lon0: float,
    lat0: float,
):
    """局部平面坐标 (E, N)，米 -> 经纬度，为 lonlat_to_local 的逆变换。

    标量或 numpy 数组均可。
    """
    import numpy as np

    lat0_rad = np.radians(lat0)
    lon = lon0 + np.degrees(east / (EARTH_RADIUS_M * np.cos(lat0_rad)))
    lat = lat0 + np.degrees(north / EARTH_RADIUS_M)
    return lon, lat


def local_to_plume_coords(
    east_m: "array-like",
    north_m: "array-like",
    wind_from_deg: float,
) -> tuple["array-like", "array-like"]:
    """平面坐标 (E, N) -> 烟羽坐标 (x=下风向, y=横风向)，米。

    x = E·sinθ + N·cosθ；y = E·cosθ − N·sinθ。
    风从北方吹来(0°) 时 θ=180°，x = -N（烟羽向南），可用于手算核对。
    """
    import numpy as np

    theta = np.radians(transport_bearing_deg(wind_from_deg))
    e = np.asarray(east_m, dtype=float)
    n = np.asarray(north_m, dtype=float)
    x = e * np.sin(theta) + n * np.cos(theta)
    y = e * np.cos(theta) - n * np.sin(theta)
    return x, y


def wind_transform_check(wind_from_deg: float) -> dict:
    """生成一条供界面展示的换算检查记录。"""
    theta_deg = transport_bearing_deg(wind_from_deg)
    (de, dn), (ce, cn) = (
        wind_unit_vectors(wind_from_deg)["downwind"],
        wind_unit_vectors(wind_from_deg)["crosswind"],
    )
    return {
        "wind_from_deg": wrap_360(wind_from_deg),
        "transport_bearing_deg": theta_deg,
        "downwind_unit_E_N": [round(de, 6), round(dn, 6)],
        "crosswind_unit_E_N": [round(ce, 6), round(cn, 6)],
        "dot_product_check": round(de * ce + dn * cn, 12),
        "norm_check": round(math.hypot(de, dn), 12),
        "interpretation": (
            f"风从 {wrap_360(wind_from_deg):.0f}° 方向吹来，"
            f"烟羽向 {theta_deg:.0f}° 方位输运"
        ),
    }
