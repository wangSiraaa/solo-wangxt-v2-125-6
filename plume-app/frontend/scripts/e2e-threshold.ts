import { chromium } from 'playwright'

const errors: string[] = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1680, height: 1000 } })
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)

const layerCounts = async () =>
  page.evaluate(() => {
    // @ts-ignore
    const map = (window as any).__map
    return {
      total: map.getSource('thr-total')._data.features.length,
      plume: map.getSource('thr-plume')._data.features.length,
    }
  })

// 1. 默认阈值 30：两套超阈图层都有要素；面板表格出现
const initial = await layerCounts()
console.log('初始阈值30 超阈单元 total/plume:', initial)
if (!(initial.total > 0 && initial.plume > 0)) { console.log('FAIL: 默认阈值应命中'); process.exit(1) }
const thrTitle = await page.locator('.thrinfo b').first().textContent()
console.log('地图统计块标题:', thrTitle?.trim())

// 2. 阈值拉到 500（高于全部采样值）：超阈区域为空
const thr = page.locator('input[data-test="threshold"]')
await thr.fill('500')
await thr.dispatchEvent('input')
await thr.dispatchEvent('change')
await page.waitForTimeout(1200)
const none = await layerCounts()
console.log('阈值500 超阈单元:', none)
if (none.total !== 0 || none.plume !== 0) { console.log('FAIL: 高阈值面积应为0'); process.exit(1) }
const zeros = await page.locator('.thr-tbl td').allInnerTexts()
console.log('统计表格行:', zeros.slice(0, 8).join(' | '))

// 3. 背景只影响总浓度：阈值 30，bg=0 与 bg=100 时烟羽超阈面积不变、总浓度增大
async function setBg(v: string) {
  const bg = page.locator('input[data-test="background"]')
  await bg.fill(v)
  await bg.dispatchEvent('input')
}
async function rowAreas() {
  return page.evaluate(() => {
    const map = (window as any).__map
    return {
      plume: map.getSource('thr-plume')._data.features.length,
      total: map.getSource('thr-total')._data.features.length,
    }
  })
}
await thr.fill('30'); await thr.dispatchEvent('input'); await thr.dispatchEvent('change')
await page.waitForTimeout(1000)
await setBg('0')
await page.getByRole('button', { name: /运行/ }).click()
await page.waitForTimeout(1200)
const bg0 = await rowAreas()
await setBg('100')
await page.getByRole('button', { name: /运行/ }).click()
await page.waitForTimeout(1200)
const bg100 = await rowAreas()
console.log('bg=0  超阈单元 plume/total:', bg0)
console.log('bg=100 超阈单元 plume/total:', bg100)
if (bg0.plume !== bg100.plume) { console.log('FAIL: 背景变化不应影响烟羽贡献统计'); process.exit(1) }
if (!(bg100.total > bg0.total)) { console.log('FAIL: 背景升高应增大总浓度超阈面积'); process.exit(1) }

// 总单元数（41-1)*(31-1)=1200 at coarse grid; default fine grid 121x81 -> 9600 cells
const frameCells = await page.evaluate(() => {
  // @ts-ignore
  const map = (window as any).__map
  return map.getSource('thr-total')._data.features.length
})
// bg=100, threshold=30 -> 所有单元命中
const allCells = 40 * 30 // 当前网格是默认 121x81? 实际默认 nx=121,ny=81
console.log('bg=100 命中总单元数:', frameCells, ' (应=120*80=9600)')
if (frameCells !== 120 * 80) { console.log('FAIL: 高背景应覆盖全部单元'); process.exit(1) }

// 4. 切换粗细网格：源项/气象不回写，统计按各自网格重算（单元数与面积口径变化）
await setBg('15')
async function setGrid(nx: string, ny: string) {
  const inputs = page.locator('input[data-test="nx"]')
  await inputs.fill(nx); await inputs.dispatchEvent('input')
  const y = page.locator('input[data-test="ny"]')
  await y.fill(ny); await y.dispatchEvent('input')
  await page.getByRole('button', { name: /运行/ }).click()
  await page.waitForTimeout(1200)
}
await setGrid('41', '31')
const coarse = await layerCounts()
const coarseSpacing = await page.locator('.mapinfo .muted').first().textContent()
await setGrid('121', '81')
const fine = await layerCounts()
const fineSpacing = await page.locator('.mapinfo .muted').first().textContent()
console.log('粗网格(41x31) 超阈单元:', coarse, coarseSpacing?.trim())
console.log('细网格(121x81) 超阈单元:', fine, fineSpacing?.trim())
// 全框单元数：粗=40*30=1200；细=120*80=9600
if (coarse.total > 1200 || fine.total > 9600) { console.log('FAIL: 超阈单元数超出网格单元总数'); process.exit(1) }

// 源项与气象未被回写：仍是默认情景 u=6、H=120、背景 15
const windVal = await page.locator('input[data-test="windspeed"]').inputValue()
const hVal = await page.locator('input[data-test="height"]').inputValue()
const bgVal = await page.locator('input[data-test="background"]').inputValue()
console.log('切网格后输入仍为 u/H/bg:', windVal, hVal, bgVal)
if (windVal !== '6' || hVal !== '120' || bgVal !== '15') { console.log('FAIL: 源项/气象被回写'); process.exit(1) }

// 5. 关闭阈值：统计块与图层消失
await page.locator('.threshold-box input[type="checkbox"]').uncheck()
await page.waitForTimeout(1000)
const thrBlock = await page.locator('.thrinfo').count()
const afterOff = await layerCounts().catch(() => null)
console.log('停用阈值后统计块数量:', thrBlock, '图层:', afterOff)
if (thrBlock !== 0) { console.log('FAIL: 停用阈值后统计块应消失'); process.exit(1) }

await page.screenshot({ path: '/tmp/plume-threshold-off.png' })

// 6. 重新启用，静风情景下不出现统计（模型拒绝）
await page.locator('.threshold-box input[type="checkbox"]').check()
await page.waitForTimeout(1200)
await page.locator('.panel select').nth(1).selectOption({ label: '静风情景（应被模型拒绝）' })
await page.waitForTimeout(800)
const calmThr = await page.locator('.thrinfo').count()
console.log('静风时统计块数量（应0）:', calmThr)
if (calmThr !== 0) { console.log('FAIL: 静风下不应有阈值统计'); process.exit(1) }

if (errors.length) { console.log('--- JS ERRORS ---'); errors.forEach((e) => console.log(e)); process.exit(1) }
console.log('ALL THRESHOLD E2E CHECKS PASSED')
await browser.close()
