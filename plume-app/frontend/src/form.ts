export interface FormState {
  sourceId: number
  metId: number
  stackHeight: number
  emission: number
  stackDia: number
  exitV: number
  stackT: number
  windFrom: number
  windSpeed: number
  stability: 'A' | 'B' | 'C' | 'D' | 'E' | 'F'
  ambientT: number
  pressure: number
  background: number
  useRise: boolean
  parameterization: 'briggs_rural' | 'power_law'
  ay: number
  py: number
  az: number
  pz: number
  downwindExtent: number
  crosswindExtent: number
  upwindExtent: number
  nx: number
  ny: number
  calmThreshold: number
  /** 课堂自定义浓度阈值（μg/m³），仅教学统计，非法定限值 */
  threshold: number
}

export const DEFAULT_FORM: FormState = {
  sourceId: 1,
  metId: 1,
  stackHeight: 120,
  emission: 50,
  stackDia: 4,
  exitV: 18,
  stackT: 410,
  windFrom: 270,
  windSpeed: 6,
  stability: 'D',
  ambientT: 293.15,
  pressure: 1013,
  background: 15,
  useRise: false,
  parameterization: 'briggs_rural',
  ay: 0.22,
  py: 1,
  az: 0.16,
  pz: 1,
  downwindExtent: 6000,
  crosswindExtent: 2000,
  upwindExtent: 300,
  nx: 121,
  ny: 81,
  calmThreshold: 1,
  threshold: 50,
}
