# 离线高斯烟羽情景教学应用

环境课程演示：**烟囱高度、风速、稳定度如何影响地面浓度**。

- 前端：Vue 3 + Vite + MapLibre GL（自实现 marching squares 等值线/等值区）
- 后端：FastAPI + NumPy，**显式参数化**的稳态高斯烟羽模型
- 数据库：PostgreSQL + PostGIS（虚构排放源与气象情景）；
  **无数据库时自动回退内置内存虚构数据**，整套应用可完全离线运行

> ⚠️ 仅供课堂教学。基于平坦地形、稳态风、定常排放的解析模型，
> 不含地形、建筑物下洗、干湿沉降与化学反应。
> **结果不得用于真实事故预警或法规达标判定。**

## 1. 快速开始

### 方式 A：本地开发（无需数据库）

```bash
# 后端（需要 numpy/fastapi/uvicorn/psycopg/pytest/httpx）
cd backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173 （已配置 /api 代理到 8000）
```

打开 http://127.0.0.1:5173 。数据后端徽标显示“内存虚构数据”。

### 方式 B：Docker Compose（含 PostGIS）

```bash
docker compose up --build
# Web  http://localhost:8080
# API  http://localhost:8000/api/health （repository 应为 postgis）
```

数据库初始化脚本 `db/init.sql` 自动建表（`geometry(Point,4326)` + GIST 索引）
并灌入 3 个虚构排放源、5 个虚构气象情景。

### 离线底图

默认使用无注记浅灰底（等值面本身即为教学重点）。
若有本地瓦片服务，构建前端时传：

```bash
VITE_TILE_URL="http://localhost:8090/{z}/{x}/{y}.png" npm run build
# 或 docker compose build --build-arg VITE_TILE_URL=...
```

## 2. 模型

地面全反射高斯烟羽在 z=0 处：

```
C(x,y,0) = Q / (π·u·σy·σz) · exp(−y²/(2σy²)) · exp(−He²/(2σz²))
```

| 符号 | 含义 | 单位 |
|---|---|---|
| Q | 源排放率 | g/s |
| u | 风速（烟囱口高度） | m/s |
| He | 有效源高 = 烟囱高 + Δh | m |
| σy, σz | 横风向/垂直扩散系数 | m |
| x, y | 下风向/横风向距离 | m |
| C | 浓度（g→μg 乘 1e6） | **μg/m³** |

弥散系数（全部系数在 `backend/app/dispersion.py` 与 `GET /api/meta` 中可读）：

- **Briggs 乡村系数（默认）**，建议适用 x ≈ 100 m – 10 km，
  超出范围的栅格在诊断中计数提示；
- **幂律 σy=ay·x^py、σz=az·x^pz**，用于与解析结论对照。
- 烟气抬升可选 Holland (1953)：`Δh = vs·d/u·(1.5 + 2.68e-3·P·(Ts−Ta)/Ts·d)`，
  默认**关闭**，便于干净地核对烟囱高度影响。

## 3. 关键设计（对应课程约束）

1. **静风拒绝硬算**：`u < calm_threshold`（默认 1.0 m/s）时返回
   `422 calm_wind`，绝不执行除法，不产生无意义的巨大浓度。
   内置气象 #4（u=0.3 m/s）即用于演示此拦截。
2. **风向 ↔ 地图坐标可检查**：
   - `wind_from_deg` 是**气象来向角**（风从哪吹来）；
     烟羽输运方位角 = `(wind_from_deg + 180) mod 360`。
   - 局部平面 E（东）/N（北，米）与经纬度（EPSG:4326）之间
     用等距圆柱近似（建议尺度 ≤ 30 km，超出界面给警告）。
   - `GET /api/plume/wind-check?wind_from_deg=270` 返回输运方位角、
     下风向/横风向单位向量、正交性 d·c≈0 与 |d|=1 的核对值；
     前端有独立“风向换算检查”页签。
3. **浓度三部分严格分开**：`plume_field`（烟羽贡献）、
   `background_conc`（空间常数背景）、`total = plume + background` 分别返回；
   地图上烟羽热图与均匀背景层是**两个可独立开关的图层**。
4. **源项独立展示**：烟囱几何高、Δh、有效源高、Q、烟温等在右侧面板分项列出。
5. **网格分辨率只改变采样**：源/气象输入是独立对象，
   界面调整通过 override 合并、不改数据库；改 nx/ny 不改变任何物理输入，
   固定物理点的浓度与分辨率无关（见解析核对 #9）。
6. **地图展示采样范围**：虚线矩形是采样边界，角点经纬度随响应返回；
   右上角标注节点数与间距，等值线为网格内线性插值，**不外推、不暗示无限精度**。
7. **课堂自定义阈值统计（非法定限值）**：请求带 `threshold_ug_m3`
   时，响应中 `threshold_statistics` 分别对**烟羽贡献**与**总浓度**给出：
   超阈单元数、按**当前网格实际米制间距**计算的超阈面积
   （= 单元数 × dx × dy）、占采样框比例、以及 Briggs
   建议范围（0.1–10 km）外的格点数/越界超阈单元数。
   判定口径为每个网格单元**四角节点浓度均值严格大于阈值**；
   背景值为空间常数，**只改变总浓度统计**。
   该面积是离散采样估计，**不使用等值线插值精度、不代表真实暴露面积**，
   阈值也不是任何法规限值；静风时不产生统计（422），
   阈值高于全部采样值时面积为 0，切换粗细网格后统计按各自网格重算
   （源项与气象不被回写）。

## 4. 解析核对用例

`GET /api/checks`（前端“解析核对”页签），后端 `pytest` 复用同一组函数：

| 核对 | 内容 |
|---|---|
| 横风向对称性 | C(x,+y) = C(x,−y)（相对差 < 1e-10） |
| 横风向高斯比 | C(x,y)/C(x,0) = exp(−y²/(2σy²)) |
| 下风向衰减 | 中心线过峰值后单调递减 |
| **源高解析解** | 线性幂律下 x_peak = H/(√2·az)、C_max = 2Q·az/(π·e·u·ay·H²)：H 加倍 → x_peak 加倍、C_max 变 1/4 |
| 排放率线性 | Q 加倍 → C 加倍 |
| 单位核对 | 与公式手算逐项一致（g→μg ×1e6） |
| 旋转不变性 | 同一烟羽坐标点在任意风向下浓度相同（坐标换算闭环） |
| 静风拦截 | u=0.3 m/s 必须抛 CalmWindError |
| 分辨率无关 | 粗/细网格在同一物理格点浓度相同 |
| 背景分开 | total = plume + bg 处处成立 |

运行后端测试：

```bash
cd backend && python3 -m pytest tests/ -q     # 9 passed
```

前端工具：

```bash
cd frontend
npm run build                  # vue-tsc 类型检查 + vite 构建
npx tsx scripts/smoke-contours.ts   # marching squares 数值冒烟
npx tsx scripts/e2e.ts              # 需 Playwright Chromium：渲染/静风/核对
```

## 5. API 一览

```
GET  /api/health
GET  /api/meta                   单位约定/稳定度/Briggs 系数/静风阈值/课堂阈值口径
GET  /api/sources[/id]           虚构排放源（PostGIS 或内存）
GET  /api/meteorology[/id]       虚构气象情景
POST /api/plume/grid             采样网格浓度（烟羽/背景/总量分开 + 阈值超阈统计）
POST /api/plume/points           任意经纬度点求值（核对用）
GET  /api/plume/wind-check       风向↔坐标换算检查
POST /api/plume/rise             Holland 抬升明细
GET  /api/checks                 10 条解析核对
```

交互文档：http://localhost:8000/docs 。

## 6. 目录

```
backend/app/
  gaussian.py       高斯主公式 + CalmWindError（静风硬拦截）
  dispersion.py     Briggs/幂律弥散系数，显式系数与适用范围
  geometry.py       风向、E/N 平面、经纬度换算（含单位向量核对）
  plume_rise.py     Holland 抬升
  checks.py         10 条解析核对（API 与 pytest 共用）
  services.py       网格构造、override 合并、等值级、响应组装
  repository.py     PostGIS 仓储 / 内存回退
frontend/src/
  components/MapView.vue       MapLibre 图层（烟羽/等值线/背景/采样框/风矢）
  marching.ts                  marching squares（无第三方几何库）
db/init.sql        PostGIS 建表 + 虚构数据
```

## 7. 虚构数据

所有排放源（示范热电厂、化工厂加热炉、水泥厂排气筒）与气象情景
（中性大风、不稳定晴昼、稳定夜间、**静风**、弱风 C 类）
均为教学虚构，不对应任何真实设施。
