-- 离线高斯烟羽教学应用：PostgreSQL/PostGIS 初始化
-- 全部为虚构数据，仅用于课堂演示。
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS emission_source (
    id                 SERIAL PRIMARY KEY,
    name               TEXT NOT NULL,
    pollutant          TEXT NOT NULL DEFAULT 'SO2',
    location           geometry(Point, 4326) NOT NULL,
    stack_height_m     DOUBLE PRECISION NOT NULL CHECK (stack_height_m >= 0),
    emission_rate_g_s  DOUBLE PRECISION NOT NULL CHECK (emission_rate_g_s >= 0),
    stack_diameter_m   DOUBLE PRECISION NOT NULL DEFAULT 0.8,
    exit_velocity_ms   DOUBLE PRECISION NOT NULL DEFAULT 15.0,
    stack_temp_k       DOUBLE PRECISION NOT NULL CHECK (stack_temp_k > 0),
    is_fictional       BOOLEAN NOT NULL DEFAULT TRUE,
    note               TEXT DEFAULT '虚构教学数据，不代表真实设施'
);

CREATE TABLE IF NOT EXISTS meteorology_scenario (
    id                        SERIAL PRIMARY KEY,
    name                      TEXT NOT NULL,
    wind_from_deg             DOUBLE PRECISION NOT NULL
        CHECK (wind_from_deg >= 0 AND wind_from_deg < 360),
    wind_speed_ms             DOUBLE PRECISION NOT NULL CHECK (wind_speed_ms >= 0),
    stability_class           CHAR(1) NOT NULL
        CHECK (stability_class IN ('A','B','C','D','E','F')),
    ambient_temp_k            DOUBLE PRECISION NOT NULL CHECK (ambient_temp_k > 0),
    pressure_hpa              DOUBLE PRECISION NOT NULL CHECK (pressure_hpa > 0),
    background_conc_ug_m3     DOUBLE PRECISION NOT NULL
        CHECK (background_conc_ug_m3 >= 0),
    is_fictional              BOOLEAN NOT NULL DEFAULT TRUE,
    note                      TEXT DEFAULT '虚构教学气象情景'
);

CREATE INDEX IF NOT EXISTS idx_emission_source_geom
    ON emission_source USING GIST (location);

-- 幂等灌入虚构数据
INSERT INTO emission_source
    (id, name, pollutant, location, stack_height_m, emission_rate_g_s,
     stack_diameter_m, exit_velocity_ms, stack_temp_k)
SELECT * FROM (VALUES
    (1, '虚构·华北示范热电厂 #1', 'SO2',
        ST_SetSRID(ST_MakePoint(116.40, 39.90), 4326), 120.0, 50.0, 4.0, 18.0, 410.0),
    (2, '虚构·滨江化工厂工艺加热炉', 'NOx',
        ST_SetSRID(ST_MakePoint(119.80, 31.30), 4326), 45.0, 8.0, 1.2, 15.0, 395.0),
    (3, '虚构·西部水泥厂窑尾排气筒', 'PM10',
        ST_SetSRID(ST_MakePoint(103.85, 36.05), 4326), 80.0, 12.0, 2.2, 14.0, 380.0)
) AS v(id, name, pollutant, geom, h, q, d, vs, ts)
WHERE NOT EXISTS (SELECT 1 FROM emission_source);

SELECT setval(
    pg_get_serial_sequence('emission_source', 'id'),
    (SELECT MAX(id) FROM emission_source)
);

INSERT INTO meteorology_scenario
    (id, name, wind_from_deg, wind_speed_ms, stability_class,
     ambient_temp_k, pressure_hpa, background_conc_ug_m3)
SELECT * FROM (VALUES
    (1, '白天·中性大风（D）',  270.0, 6.0, 'D', 293.15, 1013.0, 15.0),
    (2, '晴天午后·不稳定（B）', 180.0, 3.0, 'B', 303.15, 1010.0,  8.0),
    (3, '夜间晴空·稳定（F）',   45.0, 2.0, 'F', 283.15, 1018.0, 30.0),
    (4, '静风情景（应被模型拒绝）', 90.0, 0.3, 'F', 285.15, 1016.0, 25.0),
    (5, '弱风·弱不稳定（C）', 315.0, 2.5, 'C', 298.15, 1012.0, 12.0)
) AS v(id, name, wf, u, sc, ta, p, bg)
WHERE NOT EXISTS (SELECT 1 FROM meteorology_scenario);

SELECT setval(
    pg_get_serial_sequence('meteorology_scenario', 'id'),
    (SELECT MAX(id) FROM meteorology_scenario)
);
