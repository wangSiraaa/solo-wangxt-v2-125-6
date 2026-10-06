"""运行期配置。

DATABASE_URL 指向 PostgreSQL/PostGIS 时使用数据库仓储；
未设置或连不上时自动回退到内置的虚构数据（内存仓储），
保证断网 / 无数据库环境下应用仍可完整运行。
"""
from __future__ import annotations

import os


class Settings:
    database_url: str | None = os.getenv("DATABASE_URL") or None
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    # 静风阈值默认值（m/s），低于该值模型拒绝硬算
    default_calm_threshold_ms: float = 1.0
    # 采样网格硬边界，防止前端请求过大矩阵
    grid_max_points_per_axis: int = 401
    grid_min_spacing_m: float = 2.0
    grid_max_half_extent_m: float = 50_000.0
    # 平面近似（等距圆柱投影）建议的最大尺度
    flat_earth_advisory_m: float = 30_000.0
    # Briggs 乡村系数建议适用距离
    briggs_valid_x_min_m: float = 100.0
    briggs_valid_x_max_m: float = 10_000.0


settings = Settings()
