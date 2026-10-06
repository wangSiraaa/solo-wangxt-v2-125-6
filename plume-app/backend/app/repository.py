"""数据仓储：PostgreSQL/PostGIS 优先，缺省回退内存虚构数据。

表结构见 db/init.sql（PostGIS，geometry(Point,4326)，带 GIST 索引）。
运行时每个请求短连接；DATABASE_URL 未设置或连接失败时，
透明回退到 seed_data 内存数据，并在 /api/health 标明后端类型。
"""
from __future__ import annotations

from typing import Any

from .config import settings
from .seed_data import SEED_METEOROLOGY, SEED_SOURCES

_SOURCE_COLS = (
    "id", "name", "pollutant", "lon", "lat", "stack_height_m",
    "emission_rate_g_s", "stack_diameter_m", "exit_velocity_ms", "stack_temp_k",
)
_MET_COLS = (
    "id", "name", "wind_from_deg", "wind_speed_ms", "stability_class",
    "ambient_temp_k", "pressure_hpa", "background_conc_ug_m3",
)


class MemoryRepository:
    backend = "memory"

    def __init__(self) -> None:
        self.sources = [dict(s) for s in SEED_SOURCES]
        self.meteorology = [dict(m) for m in SEED_METEOROLOGY]

    def list_sources(self) -> list[dict]:
        return [dict(s) for s in self.sources]

    def get_source(self, source_id: int) -> dict | None:
        return next((dict(s) for s in self.sources if s["id"] == source_id), None)

    def list_meteorology(self) -> list[dict]:
        return [dict(m) for m in self.meteorology]

    def get_meteorology(self, met_id: int) -> dict | None:
        return next((dict(m) for m in self.meteorology if m["id"] == met_id), None)


class PostgisRepository:
    backend = "postgis"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg

        # 由调用方确保服务就绪；失败由 get_repository 的探测拦截
        return psycopg.connect(self.database_url, connect_timeout=3)

    @staticmethod
    def _rows(cur, columns: tuple[str, ...]) -> list[dict[str, Any]]:
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def list_sources(self) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, pollutant,
                       ST_X(location) AS lon, ST_Y(location) AS lat,
                       stack_height_m, emission_rate_g_s,
                       stack_diameter_m, exit_velocity_ms, stack_temp_k
                FROM emission_source ORDER BY id
                """
            )
            return self._rows(cur, _SOURCE_COLS)

    def get_source(self, source_id: int) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, pollutant,
                       ST_X(location) AS lon, ST_Y(location) AS lat,
                       stack_height_m, emission_rate_g_s,
                       stack_diameter_m, exit_velocity_ms, stack_temp_k
                FROM emission_source WHERE id = %s
                """,
                (source_id,),
            )
            rows = self._rows(cur, _SOURCE_COLS)
            return rows[0] if rows else None

    def list_meteorology(self) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(_MET_COLS)}
                FROM meteorology_scenario ORDER BY id
                """
            )
            return self._rows(cur, _MET_COLS)

    def get_meteorology(self, met_id: int) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(_MET_COLS)}
                FROM meteorology_scenario WHERE id = %s
                """,
                (met_id,),
            )
            rows = self._rows(cur, _MET_COLS)
            return rows[0] if rows else None


_repo: MemoryRepository | PostgisRepository | None = None


def get_repository() -> MemoryRepository | PostgisRepository:
    """惰性初始化：探测 PostGIS，失败回退内存仓储。"""
    global _repo
    if _repo is not None:
        return _repo
    if settings.database_url:
        candidate = PostgisRepository(settings.database_url)
        try:
            with candidate._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT PostGIS_version()")
                cur.fetchone()
            _repo = candidate
        except Exception as exc:  # 连接/扩展不可用 -> 回退
            print(f"[repository] PostGIS 不可用，回退内存仓储: {exc}")
            _repo = MemoryRepository()
    else:
        _repo = MemoryRepository()
    return _repo
