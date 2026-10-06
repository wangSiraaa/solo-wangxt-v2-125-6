"""请求/响应数据模型。

设计要点：
* 源项（SourceInput）、气象（MeteorologyInput）、采样网格（GridSpec）
  在结构上完全分离——改变网格分辨率不会修改源与气象输入。
* 浓度始终分三部分返回：plume（烟羽贡献）、background（背景值）、total。
* override 用于在已有虚构源/情景上做参数调整，不改动数据库记录。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .dispersion import STABILITY_CLASSES

StabilityClass = Literal["A", "B", "C", "D", "E", "F"]


class SourceInput(BaseModel):
    """源项（虚构排放源）。"""

    name: str = Field(..., description="源名称")
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-85.0, le=85.0)
    stack_height_m: float = Field(..., ge=0.0, description="烟囱几何高度 m")
    emission_rate_g_s: float = Field(..., ge=0.0, description="排放率 g/s")
    stack_diameter_m: float = Field(0.8, ge=0.0)
    exit_velocity_ms: float = Field(15.0, ge=0.0, description="出口烟气流速 m/s")
    stack_temp_k: float = Field(400.0, gt=0.0)
    pollutant: str = Field("SO2", description="污染物标识")


class MeteorologyInput(BaseModel):
    """气象情景。wind_from_deg 为气象来向角（从哪吹来）。"""

    name: str
    wind_from_deg: float = Field(..., ge=0.0, lt=360.0)
    wind_speed_ms: float = Field(..., ge=0.0)
    stability_class: StabilityClass
    ambient_temp_k: float = Field(293.15, gt=0.0)
    pressure_hpa: float = Field(1013.0, gt=0.0)
    background_conc_ug_m3: float = Field(..., ge=0.0, description="背景浓度 μg/m³")


class PlumeRiseInput(BaseModel):
    use_plume_rise: bool = Field(
        False, description="是否叠加 Holland 抬升；默认关闭，便于核对源高影响"
    )


class SourceOverride(BaseModel):
    """前端临时改参数，不写回数据库。None 字段保持原值。"""

    stack_height_m: float | None = Field(None, ge=0.0)
    emission_rate_g_s: float | None = Field(None, ge=0.0)
    stack_diameter_m: float | None = Field(None, ge=0.0)
    exit_velocity_ms: float | None = Field(None, ge=0.0)
    stack_temp_k: float | None = Field(None, gt=0.0)


class MetOverride(BaseModel):
    wind_from_deg: float | None = Field(None, ge=0.0, lt=360.0)
    wind_speed_ms: float | None = Field(None, ge=0.0)
    stability_class: StabilityClass | None = None
    ambient_temp_k: float | None = Field(None, gt=0.0)
    pressure_hpa: float | None = Field(None, gt=0.0)
    background_conc_ug_m3: float | None = Field(None, ge=0.0)


class GridSpec(BaseModel):
    """采样网格规范（仅描述如何采样，不改变任何模型输入）。"""

    downwind_extent_m: float = Field(6000.0, gt=0.0, le=50_000.0)
    crosswind_extent_m: float = Field(2000.0, gt=0.0, le=50_000.0)
    upwind_extent_m: float = Field(300.0, ge=0.0, le=10_000.0)
    nx: int = Field(121, ge=5, le=401)
    ny: int = Field(81, ge=5, le=401)
    spacing_note: str | None = None


class PlumeGridRequest(BaseModel):
    source: SourceInput
    meteorology: MeteorologyInput
    grid: GridSpec = Field(default_factory=GridSpec)
    plume_rise: PlumeRiseInput = Field(default_factory=PlumeRiseInput)
    source_override: SourceOverride | None = None
    met_override: MetOverride | None = None
    parameterization: Literal["briggs_rural", "power_law"] = "briggs_rural"
    power_law: dict | None = Field(
        None,
        description="power_law 参数: ay, py, az, pz（均为正）",
    )
    calm_threshold_ms: float = Field(1.0, gt=0.0, le=5.0)
    threshold_ug_m3: float = Field(
        50.0,
        ge=0.0,
        description=(
            "课堂自定义浓度阈值（μg/m³），仅用于超阈面积的教学统计，"
            "不代表任何法定限值；与采样网格一样不回写源项/气象。"
        ),
    )


class PlumeGridResponse(BaseModel):
    """结果：烟羽、背景、总量分开；网格角点显式给出，避免任何精度暗示。"""

    source_lonlat: tuple[float, float]
    crs_note: str
    grid: dict
    plume_field_ug_m3: list[list[float]]
    background_conc_ug_m3: float
    total_conc_ug_m3: list[list[float]]
    iso_levels_ug_m3: list[float]
    threshold_statistics: dict = Field(
        description=(
            "课堂自定义阈值下的超阈面积统计（按实际米制网格间距、"
            "以单元四角节点均值判定，非等值线插值面积）"
        )
    )
    effective_stack_height_m: float
    plume_rise_delta_h_m: float
    wind: dict
    source_term: dict
    diagnostics: dict
    validity: dict
    disclaimer: str


class PlumePointRequest(PlumeGridRequest):
    """在指定经纬度上求值（用于核对，与网格无关）。"""

    points: list[tuple[float, float]] = Field(..., description="[[lon, lat], ...]")


class PlumePointResponse(BaseModel):
    points: list[dict]
