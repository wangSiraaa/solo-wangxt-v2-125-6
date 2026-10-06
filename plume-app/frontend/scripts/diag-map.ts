import { chromium } from 'playwright'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', e.message))
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(3000)

const diag = await page.evaluate(() => {
  const map = (window as any).__map
  const c = map.getCanvas()
  const b = map.getBounds()
  // 取中心像素颜色
  const gl = map.painter.context.gl
  const w = c.width, h = c.height
  const px = new Uint8Array(4)
  gl.readPixels(w / 2, h / 2, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px)
  const px2 = new Uint8Array(4)
  gl.readPixels(100, 100, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px2)
  return {
    canvasCss: { w: c.clientWidth, h: c.clientHeight },
    canvasPx: { w, h },
    bounds: {
      w: b.getWest(), e: b.getEast(), s: b.getSouth(), n: b.getNorth(),
    },
    loaded: map.loaded(),
    centerPxRGBA: Array.from(px),
    cornerPxRGBA: Array.from(px2),
    layers: map.getLayersOrder(),
    containerRect: document.getElementById('map')!.getBoundingClientRect(),
    mapComputed: (() => {
      const el = document.getElementById('map')!
      const cs = getComputedStyle(el)
      return {
        position: cs.position, height: cs.height, inset: cs.inset,
        top: cs.top, bottom: cs.bottom, display: cs.display,
        className: el.className,
        inlineStyle: el.getAttribute('style'),
      }
    })(),
    wrapRect: document.querySelector('.map-wrap')!.getBoundingClientRect(),
    wrapComputed: (() => {
      const cs = getComputedStyle(document.querySelector('.map-wrap')!)
      return { position: cs.position, height: cs.height, minHeight: cs.minHeight }
    })(),
    layoutGrid: (() => {
      const el = document.querySelector('.layout') as HTMLElement
      const cs = getComputedStyle(el)
      return {
        gridTemplateRows: cs.gridTemplateRows,
        height: cs.height,
        clientH: el.clientHeight,
      }
    })(),
  }
})
console.log(JSON.stringify(diag, null, 2))
await browser.close()
