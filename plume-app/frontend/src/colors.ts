/** 教学用离散色带（参考 ColorBrewer YlOrRd），按等值级分档。 */

const BANDS = [
  '#ffffcc',
  '#ffeda0',
  '#fed976',
  '#feb24c',
  '#fd8d3c',
  '#fc4e2a',
  '#e31a1c',
  '#b10026',
]

export function makeColorFor(levels: number[]): (v: number) => string {
  if (levels.length === 0) return () => withAlpha(BANDS[0])
  return (v: number) => {
    let i = 0
    while (i < levels.length && v > levels[i]) i++
    const idx = Math.min(i, BANDS.length - 1)
    return withAlpha(BANDS[idx])
  }
}

function withAlpha(hex: string, alpha = 0.62): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

export function legendStops(levels: number[]): { level: number; color: string }[] {
  return levels.map((level, i) => ({
    level,
    color: withAlpha(BANDS[Math.min(i, BANDS.length - 1)], 0.85),
  }))
}
