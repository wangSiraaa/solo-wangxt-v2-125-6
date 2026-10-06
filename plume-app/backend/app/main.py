"""FastAPI 应用入口。

端点：
GET  /api/health                健康检查与仓储后端类型
GET  /api/meta                  单位、稳定度、弥散系数、阈值等可检查元数据
GET  /api/sources               虚构排放源
GET  /api/meteorology           虚构气象情景
POST /api/plume/grid            采样网格浓度（烟羽/背景/总量分开）
POST /api/plume/points          任意经纬度点浓度（核对用）
GET  /api/plume/wind-check      风向↔地图坐标换算检查
POST /api/plume/rise            Holland 抬升高程明细
GET  /api/checks                解析核对用例结果
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .checks import run_all_checks
from .config import settings
from .dispersion import (
    STABILITY_CLASSES,
    STABILITY_DESCRIPTIONS,
    parameterization_metadata,
)
from .gaussian import CalmWindError, PlumeInputError
from .geometry import wind_transform_check
from .plume_rise import holland_plume_rise
from .repository import get_repository
from .schemas import (
    PlumeGridRequest,
    PlumeGridResponse,
    PlumePointRequest,
    PlumePointResponse,
    PlumeRiseInput,
)
from .services import DISCLAIMER, run_grid, run_points

app = FastAPI(
    title="离线高斯烟羽情景教学应用 API",
    version="1.0.0",
    description="平坦地形、稳态风、显式参数化的高斯烟羽模型；仅供教学。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CalmWindError)
async def calm_wind_handler(_request, exc: CalmWindError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=422,
        content={
            "error": "calm_wind",
            "message": str(exc),
            "action": "静风条件下定常烟羽模型不适用；请提高风速或改用静风扩散模型。",
        },
    )


@app.exception_handler(PlumeInputError)
async def plume_input_handler(_request, exc: PlumeInputError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=422,
        content={"error": "invalid_input", "message": str(exc)},
    )


@app.get("/api/health")
def health():
    repo = get_repository()
    return {"status": "ok", "repository": repo.backend, "disclaimer": DISCLAIMER}


@app.get("/api/meta")
def meta():
    return {
        "units": {
            "emission_rate": "g/s",
            "concentration": "μg/m³",
            "wind_speed": "m/s",
            "distance": "m",
            "temperature": "K",
            "pressure": "hPa",
            "conversion": "g → μg 系数 1e6",
        },
        "wind_convention": {
            "wind_from_deg": "气象学风向：风从哪个方向吹来，0=北,90=东,180=南,270=西",
            "transport_bearing": "(wind_from_deg + 180) mod 360",
            "check_endpoint": "/api/plume/wind-check",
        },
        "crs": {
            "map": "EPSG:4326 经纬度",
            "computation": "以源为原点的局部等距圆柱平面（东E/北N，米）",
            "flat_earth_advisory_m": settings.flat_earth_advisory_m,
        },
        "calm_wind": {
            "default_threshold_ms": settings.default_calm_threshold_ms,
            "behavior": "低于阈值返回 422 calm_wind，拒绝硬算",
        },
        "teaching_threshold": {
            "request_field": "threshold_ug_m3",
            "default_ug_m3": 50.0,
            "purpose": "课堂自定义浓度阈值，统计烟羽贡献/总浓度的超阈采样面积",
            "teaching_only": True,
            "legal_note": "不是法定环境质量限值，不得用于达标判定或事故预警",
            "method": (
                "按网格实际米制间距，以单元四角节点均值严格大于阈值计数；"
                "面积=超阈单元数×dx×dy；非等值线插值面积，不代表真实暴露面积"
            ),
            "fields": ["plume（烟羽贡献）", "total（总浓度=烟羽+背景）"],
        },
        "stability_classes": [
            {"class": s, **STABILITY_DESCRIPTIONS[s]} for s in STABILITY_CLASSES
        ],
        "parameterizations": {
            "default": "briggs_rural",
            "briggs_rural": parameterization_metadata(),
            "power_law": {
                "formula": "sigma_y = ay*x^py; sigma_z = az*x^pz",
                "defaults": {"ay": 0.22, "py": 1.0, "az": 0.16, "pz": 1.0},
                "purpose": "解析核对用，便于手算峰值位置",
            },
        },
        "plume_rise": {
            "formula": (
                "Δh = vs*d/u * (1.5 + 2.68e-3 * P[hPa] * (Ts-Ta)/Ts * d)"
            ),
            "default_enabled": False,
        },
        "grid_limits": {
            "max_points_per_axis": settings.grid_max_points_per_axis,
            "min_spacing_m": settings.grid_min_spacing_m,
            "max_half_extent_m": settings.grid_max_half_extent_m,
        },
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/sources")
def list_sources():
    return get_repository().list_sources()


@app.get("/api/sources/{source_id}")
def get_source(source_id: int):
    row = get_repository().get_source(source_id)
    if row is None:
        raise HTTPException(404, "排放源不存在")
    return row


@app.get("/api/meteorology")
def list_meteorology():
    return get_repository().list_meteorology()


@app.get("/api/meteorology/{met_id}")
def get_meteorology(met_id: int):
    row = get_repository().get_meteorology(met_id)
    if row is None:
        raise HTTPException(404, "气象情景不存在")
    return row


@app.post("/api/plume/grid", response_model=PlumeGridResponse)
def plume_grid(req: PlumeGridRequest):
    return run_grid(req)


@app.post("/api/plume/points", response_model=PlumePointResponse)
def plume_points(req: PlumePointRequest):
    return PlumePointResponse(points=run_points(req))


@app.get("/api/plume/wind-check")
def plume_wind_check(wind_from_deg: float):
    if not 0.0 <= wind_from_deg < 360.0:
        raise HTTPException(422, "风向须在 [0, 360)")
    return wind_transform_check(wind_from_deg)


@app.post("/api/plume/rise")
def plume_rise(payload: dict):
    try:
        detail = holland_plume_rise(
            exit_velocity_ms=float(payload["exit_velocity_ms"]),
            stack_diameter_m=float(payload["stack_diameter_m"]),
            wind_speed_ms=float(payload["wind_speed_ms"]),
            stack_temp_k=float(payload["stack_temp_k"]),
            ambient_temp_k=float(payload["ambient_temp_k"]),
            pressure_hpa=float(payload["pressure_hpa"]),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise HTTPException(422, f"抬升参数无效: {exc}")
    return detail


@app.get("/api/checks")
def checks():
    return run_all_checks()
