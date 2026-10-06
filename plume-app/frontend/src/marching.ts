/**
 * Marching Squares 等值线提取（教学用，显式、无第三方几何库）。
 *
 * 输入：规则网格值 z[row=y][col=x]，以及每个网格节点的经纬度 lon[row][col]、
 * lat[row][col]（烟羽网格随风向旋转，因此节点经纬度不是规则矩形）。
 * 输出：每个等值级的线段串 GeoJSON（MultiLineString）。
 *
 * 明确声明：这些等值线是**有限采样网格上的线性插值结果**，
 * 只表示采样矩形内的分布，不外推、不暗示无限精度。
 */

type Edge = 'bottom' | 'right' | 'top' | 'left'

/** marching-squares 情况表：code -> 穿越边对（鞍点 5、10 有两对）。 */
const TABLE: Record<number, [Edge, Edge][]> = {
  1: [['bottom', 'left']],
  2: [['bottom', 'right']],
  3: [['left', 'right']],
  4: [['top', 'right']],
  5: [
    ['bottom', 'top'],
    ['left', 'right'],
  ],
  6: [['bottom', 'top']],
  7: [['left', 'top']],
  8: [['left', 'top']],
  9: [['bottom', 'top']],
  10: [
    ['bottom', 'left'],
    ['top', 'right'],
  ],
  11: [['right', 'top']],
  12: [['left', 'right']],
  13: [['bottom', 'right']],
  14: [['bottom', 'left']],
}

export function marchingSquares(
  z: number[][],
  lon: number[][],
  lat: number[][],
  level: number,
): GeoJSON.Feature<GeoJSON.MultiLineString> {
  const ny = z.length
  const nx = z[0].length
  // MultiLineString 坐标 = 多条线 × 点序 × [lon,lat]
  const coordinates: number[][][] = []

  const at = (r: number, c: number) => z[r][c]

  // 单元 (r,c) 四条边上的 level 交点，线性插值到经纬度
  const edgePoint = (r: number, c: number, edge: Edge): [number, number] => {
    let v0: number, v1: number
    let lon0: number, lat0: number, lon1: number, lat1: number
    if (edge === 'bottom') {
      ;[v0, v1] = [at(r, c), at(r, c + 1)]
      ;[lon0, lat0] = [lon[r][c], lat[r][c]]
      ;[lon1, lat1] = [lon[r][c + 1], lat[r][c + 1]]
    } else if (edge === 'right') {
      ;[v0, v1] = [at(r, c + 1), at(r + 1, c + 1)]
      ;[lon0, lat0] = [lon[r][c + 1], lat[r][c + 1]]
      ;[lon1, lat1] = [lon[r + 1][c + 1], lat[r + 1][c + 1]]
    } else if (edge === 'top') {
      ;[v0, v1] = [at(r + 1, c), at(r + 1, c + 1)]
      ;[lon0, lat0] = [lon[r + 1][c], lat[r + 1][c]]
      ;[lon1, lat1] = [lon[r + 1][c + 1], lat[r + 1][c + 1]]
    } else {
      ;[v0, v1] = [at(r, c), at(r + 1, c)]
      ;[lon0, lat0] = [lon[r][c], lat[r][c]]
      ;[lon1, lat1] = [lon[r + 1][c], lat[r + 1][c]]
    }
    const t = (level - v0) / (v1 - v0)
    return [lon0 + (lon1 - lon0) * t, lat0 + (lat1 - lat0) * t]
  }

  for (let r = 0; r < ny - 1; r++) {
    for (let c = 0; c < nx - 1; c++) {
      // 角点顺序：左下、右下、右上、左上
      const v = [at(r, c), at(r, c + 1), at(r + 1, c + 1), at(r + 1, c)]
      let code = 0
      if (v[0] > level) code |= 1
      if (v[1] > level) code |= 2
      if (v[2] > level) code |= 4
      if (v[3] > level) code |= 8
      if (code === 0 || code === 15) continue
      for (const [eA, eB] of TABLE[code] || []) {
        const pA = edgePoint(r, c, eA)
        const pB = edgePoint(r, c, eB)
        coordinates.push([[...pA], [...pB]])
      }
    }
  }
  return {
    type: 'Feature',
    properties: { level },
    geometry: { type: 'MultiLineString', coordinates },
  }
}

/** 把节点网格输出为半透明填色栅格（每格一个四边形，按两对角节点均值着色）。 */
export function gridFillPolygons(
  z: number[][],
  lon: number[][],
  lat: number[][],
  colorFor: (v: number) => string,
  minValue = 0,
): GeoJSON.FeatureCollection {
  const ny = z.length
  const nx = z[0].length
  const features: GeoJSON.Feature[] = []
  for (let r = 0; r < ny - 1; r++) {
    for (let c = 0; c < nx - 1; c++) {
      const v = (z[r][c] + z[r + 1][c + 1]) / 2
      if (v <= minValue) continue
      const ring = [
        [lon[r][c], lat[r][c]],
        [lon[r][c + 1], lat[r][c + 1]],
        [lon[r + 1][c + 1], lat[r + 1][c + 1]],
        [lon[r + 1][c], lat[r + 1][c]],
        [lon[r][c], lat[r][c]],
      ]
      features.push({
        type: 'Feature',
        properties: { color: colorFor(v), value: v },
        geometry: { type: 'Polygon', coordinates: [ring] },
      })
    }
  }
  return { type: 'FeatureCollection', features }
}

/** 采样矩形边框（明示采样范围，而非暗示无限精度）。 */
export function samplingBoundary(
  corners: [number, number][],
): GeoJSON.Feature<GeoJSON.Polygon> {
  const ring = [...corners, corners[0]]
  return {
    type: 'Feature',
    properties: { kind: 'sampling-boundary' },
    geometry: { type: 'Polygon', coordinates: [ring] },
  }
}
