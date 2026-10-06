export type StabilityClass = 'A' | 'B' | 'C' | 'D' | 'E' | 'F'

export interface SourceInput {
  name: string
  lon: number
  lat: number
  stack_height_m: number
  emission_rate_g_s: number
  stack_diameter_m: number
  exit_velocity_ms: number
  stack_temp_k: number
  pollutant: string
}

export interface MeteorologyInput {
  name?: string
  wind_from_deg: number
  wind_speed_ms: number
  stability_class: StabilityClass
  ambient_temp_k: number
  pressure_hpa: number
  background_conc_ug_m3: number
}

export interface GridSpec {
  downwind_extent_m: number
  crosswind_extent_m: number
  upwind_extent_m: number
  nx: number
  ny: number
}

export interface SourceRow extends SourceInput {
  id: number
}

export interface MetRow extends MeteorologyInput {
  id: number
  name: string
}

export interface PlumeGridResponse {
  source_lonlat: [number, number]
  crs_note: string
  grid: {
    nx: number
    ny: number
    x_edges_m: number[]
    y_edges_m: number[]
    lon_grid: number[][]
    lat_grid: number[][]
    spacing_downwind_m: number
    spacing_crosswind_m: number
    corners_lonlat: [number, number][]
    sampling_extent_lonlat: Record<string, number>
    flat_earth_warning: boolean
    resolution_disclaimer: string
  }
  plume_field_ug_m3: number[][]
  background_conc_ug_m3: number
  total_conc_ug_m3: number[][]
  iso_levels_ug_m3: number[]
  effective_stack_height_m: number
  plume_rise_delta_h_m: number
  wind: {
    wind_from_deg: number
    transport_bearing_deg: number
    downwind_unit_E_N: [number, number]
    crosswind_unit_E_N: [number, number]
    dot_product_check: number
    norm_check: number
    interpretation: string
    wind_speed_ms: number
    stability_class: string
  }
  source_term: Record<string, any>
  diagnostics: Record<string, any>
  validity: Record<string, any>
  disclaimer: string
}

export interface PlumeGridRequest {
  source: SourceInput
  meteorology: MeteorologyInput
  grid: GridSpec
  plume_rise: { use_plume_rise: boolean }
  source_override?: Record<string, number | null>
  met_override?: Record<string, number | string | null>
  parameterization: 'briggs_rural' | 'power_law'
  power_law?: { ay: number; py: number; az: number; pz: number } | null
  calm_threshold_ms: number
}

export interface CheckResult {
  id: string
  title: string
  description: string
  passed: boolean
  expected: string
  actual: string
  tolerance?: number
  extra?: Record<string, any>
}

export interface ChecksReport {
  title: string
  all_passed: boolean
  n_passed: number
  n_total: number
  results: CheckResult[]
  note: string
}

export interface ApiError {
  error: string
  message: string
  action?: string
}
