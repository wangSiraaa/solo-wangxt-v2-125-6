import { chromium } from 'playwright'

const errors: string[] = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('console', (m) => {
  if (m.type() === 'error') errors.push('console: ' + m.text())
})
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)

// 1. 地图容器与 canvas
const hasCanvas = await page.locator('#map canvas').count()
console.log('map canvases:', hasCanvas)

// 2. 顶栏、后端、运行按钮
const repo = await page.locator('.repo').textContent()
console.log('repo badge:', repo?.trim())

// 3. 结果面板关键数值
const maxText = await page.locator('.panel.right dl.kv dd b').first().textContent()
console.log('max plume contribution shown:', maxText?.trim())

// 4. MapLibre 内部数据源与图层要素数
const counts = await page.evaluate(() => {
  // @ts-ignore
  const map = (window as any).__map
  return map
    ? {
        fillFeatures: (map.getSource('fill')._data?.features || []).length,
        isoFeatures: (map.getSource('iso')._data?.features || []).length,
        boundaryFeatures: (map.getSource('boundary')._data?.features || []).length,
        windFeatures: (map.getSource('wind')._data?.features || []).length,
      }
    : null
})
console.log('map sources via global:', counts)

// 5. 核对页签
await page.getByRole('button', { name: '解析核对' }).click()
await page.waitForTimeout(800)
const checksSummary = await page.locator('.panel.right h2 .badge').first().textContent()
console.log('checks badge:', checksSummary?.trim())
const fails = await page.locator('.check-item.fail').count()
console.log('failed check items:', fails)

// 6. 风向换算页签
await page.getByRole('button', { name: '风向换算检查' }).click()
await page.waitForTimeout(400)
const bearing = await page.locator('table.meta-tbl tr td.mono').nth(1).textContent()
console.log('transport bearing cell:', bearing?.trim())

// 7. 切到静风情景：选择含“静风”的气象下拉
await page.locator('.panel select').nth(1).selectOption({ label: '静风情景（应被模型拒绝）' })
await page.waitForTimeout(500)
const calmNotice = await page.locator('.map-wrap .notice.err').count()
const calmBtnDisabled = await page.locator('button').filter({ hasText: '运行烟羽计算' }).isDisabled()
console.log('calm notice shown:', calmNotice, '| run disabled:', calmBtnDisabled)

// 8. 截图
await page.screenshot({ path: '/tmp/plume-calm.png' })

// 9. 回到正常情景 + 结果页截图
await page.locator('.panel select').nth(1).selectOption({ label: '白天·中性大风（D）' })
await page.getByRole('button', { name: '结果分解' }).click()
await page.waitForTimeout(2000)
await page.screenshot({ path: '/tmp/plume-normal.png' })

if (errors.length) {
  console.log('--- JS errors ---')
  errors.forEach((e) => console.log(e))
  process.exit(1)
}
console.log('no JS errors')
await browser.close()
