import { marchingSquares, gridFillPolygons, samplingBoundary, exceedanceCellPolygons } from '../src/marching.ts'
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

// 7. 超阈单元：高于全部值 -> 空；阈值越低单元越多；口径为四角均值严格大于
const exEmpty = exceedanceCellPolygons(z, lon, lat, 1e9, 'plume')
assert(exEmpty.features.length === 0, '阈值高于全部采样值时超阈区域为空（面积为 0）')

const ex50 = exceedanceCellPolygons(z, lon, lat, 50, 'plume')
const ex30 = exceedanceCellPolygons(z, lon, lat, 30, 'total')
assert(ex50.features.length > 0 && ex30.features.length > ex50.features.length,
  `超阈单元数随阈值降低而增多（50→${ex50.features.length}，30→${ex30.features.length}）`)

// 独立复算：与直接遍历四角均值计数一致
let manual = 0
for (let r = 0; r < ny - 1; r++) {
  for (let c = 0; c < nx - 1; c++) {
    const mean = (z[r][c] + z[r][c + 1] + z[r + 1][c] + z[r + 1][c + 1]) / 4
    if (mean > 50) manual++
  }
}
assert(ex50.features.length === manual,
  `超阈单元数 ${ex50.features.length} 与四角均值独立复算 ${manual} 一致`)

// 等于阈值的单元不超阈（严格大于）：构造全场恰好为 10 的网格
const zFlat = Array.from({ length: 5 }, () => Array.from({ length: 5 }, () => 10))
const lonFlat = zFlat[0].map((_, c) => c * 0.001)
const lonGrid = zFlat.map(() => [...lonFlat])
const latGrid = zFlat.map((row, r) => row.map(() => r * 0.001))
assert(exceedanceCellPolygons(zFlat, lonGrid, latGrid, 10, 'plume').features.length === 0,
  '单元均值恰好等于阈值不计为超阈（严格 >）')
assert(exceedanceCellPolygons(zFlat, lonGrid, latGrid, 9.999, 'plume').features.length === 16,
  '阈值略低于全场值时全部 16 个单元超阈')

if (failures) { console.error(`${failures} failures`); process.exit(1) }
console.log('marching squares smoke tests passed')
