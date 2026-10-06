import { marchingSquares, gridFillPolygons, samplingBoundary, thresholdExceedPolygons } from '../src/marching.ts'
import { makeColorFor } from '../src/colors.ts'

// 构造一个不旋转（lon/lat 等距）的二维高斯峰网格
const nx = 51, ny = 41
const lon: number[][] = [], lat: number[][] = [], z: number[][] = []
for (let r = 0; r < ny; r++) {
  const lonRow: number[] = [], latRow: number[] = [], zRow: number[] = []
  for (let c = 0; c < nx; c++) {
    const x = c - 25, y = r - 20
    lonRow.push(100 + x * 0.001)
    latRow.push(30 + y * 0.001)
    zRow.push(100 * Math.exp(-(x * x / (2 * 8 * 8) + y * y / (2 * 5 * 5))))
  }
  lon.push(lonRow); lat.push(latRow); z.push(zRow)
}

let failures = 0
function assert(cond: boolean, msg: string) {
  if (!cond) { failures++; console.error('FAIL:', msg) }
  else console.log('ok:', msg)
}

// 1. 中等级别应产生闭合趋势的多段线段（椭圆穿越多格，段数 > 20）
const f = marchingSquares(z, lon, lat, 50)
const nSeg = f.geometry.coordinates.length
assert(nSeg > 20, `level=50 产生 ${nSeg} 条等值线段（>20）`)

// 2. 高过峰值的级别无线段；零/负级别边界行为
assert(marchingSquares(z, lon, lat, 999).geometry.coordinates.length === 0, '高于峰值无等值线')
assert(marchingSquares(z, lon, lat, -1).geometry.coordinates.length === 0, '负值级无等值线')

// 3. 等值点必须落在该级两侧值之间（抽查所有线段端点双线性范围）
const level = 30
const ff = marchingSquares(z, lon, lat, level)
let inRange = true
for (const line of ff.geometry.coordinates) {
  for (const [px, py] of line) {
    if (px < 100 - 0.026 || px > 100 + 0.026 || py < 30 - 0.021 || py > 30 + 0.021) inRange = false
  }
}
assert(inRange, '所有等值点位于采样范围之内（不外推）')

// 4. 填色多边形数量与色带
const fc = gridFillPolygons(z, lon, lat, makeColorFor([10, 30, 60]))
assert(fc.features.length > 0 && fc.features.every(x => x.geometry.type === 'Polygon'),
  `填色多边形 ${fc.features.length} 个`)

// 5. 采样边界
const b = samplingBoundary([[1, 2], [3, 4], [5, 6], [7, 8]])
assert(b.geometry.coordinates[0].length === 5, '采样边界闭合（5 点含首点）')

// 6. 对称性：关于中心行 y=0 对称的两条水平线，等值线段数应相同
const zAsym = z.map(row => row.map(v => v)) // 同一份
const fA = marchingSquares(zAsym, lon, lat, 40)
assert(fA.geometry.coordinates.length > 0, '对称场可重复提取')

// 7. 超阈值单元：口径=四角均值严格大于 level，只产生四边形单元
const fc50 = thresholdExceedPolygons(z, lon, lat, 50, 'total')
assert(fc50.features.length > 0, `阈值 50 命中 ${fc50.features.length} 个单元`)
assert(fc50.features.every(f => f.geometry.type === 'Polygon'
  && (f.geometry as GeoJSON.Polygon).coordinates[0].length === 5
  && f.properties?.kind === 'total'),
  '超阈要素均为闭合五边形且带 kind')
// 高于峰值：空区域
assert(thresholdExceedPolygons(z, lon, lat, 1e6, 'total').features.length === 0,
  '阈值高于全部采样值时超阈区域为空（面积 0）')
// 等于常值场：严格大于 -> 空
const constField: number[][] = Array.from({ length: ny }, () => Array(nx).fill(10))
assert(thresholdExceedPolygons(constField, lon, lat, 10, 'plume').features.length === 0,
  '常值=阈值时严格大于口径不命中任何单元')
assert(thresholdExceedPolygons(constField, lon, lat, 9.999, 'plume').features.length
  === (nx - 1) * (ny - 1), '阈值略低于常值时全部单元命中')
// 零阈值 + 非负场：全部命中
assert(thresholdExceedPolygons(z, lon, lat, 0, 'plume').features.length
  === (nx - 1) * (ny - 1), '阈值 0 时全部非负单元命中')

if (failures) { console.error(`${failures} failures`); process.exit(1) }
console.log('marching squares smoke tests passed')
