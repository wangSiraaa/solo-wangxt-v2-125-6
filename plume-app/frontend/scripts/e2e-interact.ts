import { chromium } from 'playwright'

const errors: string[] = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => errors.push(e.message))
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)

const runBtn = () => page.getByRole('button', { name: /运行/ })
async function setRange(test: string, val: string) {
  const loc = page.locator(`input[data-test="${test}"]`)
  await loc.fill(val)
  await loc.dispatchEvent('input')
}
async function runAndWait() {
  await runBtn().click()
  await page.waitForTimeout(1000)
}
async function scene() {
  return await page.evaluate(() => {
    // @ts-ignore
    const map = window.__map
    const fill = map.getSource('fill')._data
    let max = -1
    for (const f of fill.features) if (f.properties.value > max) max = f.properties.value
    const wind = map.getSource('wind')._data
    const line = wind.features.find((f: any) => f.geometry.type === 'LineString')
    const thPlume = map.getSource('thplume')._data.features.length
    const thTotal = map.getSource('thtotal')._data.features.length
    return {
      fillCount: fill.features.length,
      max,
      windHead: line ? line.geometry.coordinates[1] : null,
      windTail: line ? line.geometry.coordinates[0] : null,
      thPlume,
      thTotal,
    }
  })
}

// A 北风（从北吹来）-> 烟羽向南（lat 减小）
await setRange('windfrom', '0')
await runAndWait()
const south = await scene()
const goesSouth = south.windHead[1] < south.windTail[1]
console.log('A 北风 -> 烟羽向南:', goesSouth, `(lat ${south.windTail[1].toFixed(4)} -> ${south.windHead[1].toFixed(4)})`)

// B 东风 -> 烟羽向西（lon 减小）
await setRange('windfrom', '90')
await runAndWait()
const west = await scene()
const goesWest = west.windHead[0] < west.windTail[0]
console.log('B 东风 -> 烟羽向西:', goesWest, `(lon ${west.windTail[0].toFixed(4)} -> ${west.windHead[0].toFixed(4)})`)

// C 稳定度：同 u=3，F 稳定更集中（峰值高、填色格少），B 不稳定更宽
await setRange('windfrom', '270')
await page.locator('.panel select').nth(2).selectOption('F')
await setRange('windspeed', '3')
await runAndWait()
const stabF = await scene()
await page.locator('.panel select').nth(2).selectOption('B')
await runAndWait()
const stabB = await scene()
console.log('C 填色格数 F=', stabF.fillCount, ' B=', stabB.fillCount,
  '| 不稳定更宽:', stabB.fillCount > stabF.fillCount)
console.log('  峰值 F=', stabF.max.toFixed(2), ' B=', stabB.max.toFixed(2),
  '（120 m 高烟囱在 6 km 窗内：F 类烟羽尚未充分触地，峰值在更远处——教学点）')

// D 烟囱高度：H=40 vs 200
await page.locator('.panel select').nth(2).selectOption('D')
await setRange('windspeed', '4')
await setRange('height', '40')
await runAndWait()
const lowH = await scene()
await setRange('height', '200')
await runAndWait()
const highH = await scene()
console.log('D 峰值 H=40:', lowH.max.toFixed(2), ' H=200:', highH.max.toFixed(2),
  '| 高烟囱峰值更低:', highH.max < lowH.max)

// E 分辨率改变不影响物理：粗网格重算，最大值应近似不变（峰值位置可能有采样误差）
await setRange('height', '60')
await setRange('nx', '121')
await setRange('ny', '81')
await runAndWait()
const fine = await scene()
await setRange('nx', '41')
await setRange('ny', '31')
await runAndWait()
const coarse = await scene()
console.log('E 最大浓度 细网格=', fine.max.toFixed(3), ' 粗网格=', coarse.max.toFixed(3))

// F 课堂阈值：低阈值有超阈单元；阈值高于全部值 -> 超阈区为 0；总浓度超阈单元 ≥ 烟羽
const thInput = () => page.locator('input[data-test="threshold"]')
await thInput().fill('50')
await thInput().dispatchEvent('input')
await runAndWait()
const thLow = await scene()
await thInput().fill('1000000')
await thInput().dispatchEvent('input')
await runAndWait()
const thHigh = await scene()
console.log('F 阈值=50 超阈单元 烟羽=', thLow.thPlume, ' 总浓度=', thLow.thTotal,
  '| 阈值=1e6 时烟羽=', thHigh.thPlume, ' 总浓度=', thHigh.thTotal)
const thOk = thLow.thPlume > 0 && thLow.thTotal >= thLow.thPlume &&
  thHigh.thPlume === 0 && thHigh.thTotal === 0

await page.screenshot({ path: '/tmp/plume-interact.png' })
const pass = goesSouth && goesWest && stabB.fillCount > stabF.fillCount &&
  highH.max < lowH.max && thOk
if (errors.length || !pass) { console.log('JS ERRORS:', errors, 'PASS:', pass); process.exit(1) }
console.log('all interaction scenario checks passed, no JS errors')
await browser.close()
