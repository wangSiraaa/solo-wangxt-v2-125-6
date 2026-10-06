import { chromium } from 'playwright'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => { console.log('PAGEERROR:', e.message); process.exit(1) })
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)

const counts = async () =>
  page.evaluate(() => {
    // @ts-ignore
    const map = window.__map
    return {
      fill: map.getSource('fill')._data.features.length,
      bgval: map.getSource('bgval')._data.features.length,
      iso: map.getSource('iso')._data.features.length,
      bgVisible: map.getLayoutProperty('bgval-layer', 'visibility'),
    }
  })

// 默认：烟羽 + 背景均开
const on = await counts()
console.log('default:', on)
if (!(on.fill > 0 && on.bgval === 1 && on.iso > 0 && on.bgVisible === 'visible')) {
  console.log('UNEXPECTED default layers'); process.exit(1)
}

// 关闭背景叠加 -> 只剩烟羽
await page.getByText(/背景值叠加/).locator('input').uncheck()
await page.waitForTimeout(600)
const bgOff = await counts()
console.log('bg off:', bgOff)
if (bgOff.bgVisible !== 'none') { console.log('bg layer should be hidden'); process.exit(1) }

// 关闭烟羽填色
await page.getByText(/烟羽贡献等值区/).locator('input').uncheck()
await page.waitForTimeout(600)
const noFill = await counts()
console.log('fill off:', noFill)
if (noFill.fill !== 0) { console.log('fill should be empty'); process.exit(1) }

await page.getByText(/背景值叠加/).locator('input').check()
await page.waitForTimeout(800)
await page.screenshot({ path: '/tmp/plume-bgon.png' })

// 解析核对页
await page.getByRole('button', { name: '解析核对' }).click()
await page.waitForTimeout(600)
await page.screenshot({ path: '/tmp/plume-checks.png' })
console.log('layer toggle checks passed')
await browser.close()
