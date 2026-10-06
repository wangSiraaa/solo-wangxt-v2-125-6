<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ControlPanel from './components/ControlPanel.vue'
import MapView from './components/MapView.vue'
import ResultPanel from './components/ResultPanel.vue'
import { api } from './api'
import { DEFAULT_FORM, type FormState } from './form'
import type {
  MetRow,
  PlumeGridResponse,
  SourceRow,
} from './types'
import { legendStops } from './colors'

const sources = ref<SourceRow[]>([])
const meteorology = ref<MetRow[]>([])
const form = ref<FormState>({ ...DEFAULT_FORM })
const result = ref<PlumeGridResponse | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)
const repo = ref<string>('…')
const showFill = ref(true)
const showIso = ref(true)
const showBg = ref(true)

const isCalm = computed(() => form.value.windSpeed < form.value.calmThreshold)

onMounted(async () => {
  try {
    const [h, s, m] = await Promise.all([
      api.health(),
      api.sources(),
      api.meteorology(),
    ])
    repo.value = h.repository
    sources.value = s
    meteorology.value = m
    applySource(s[0])
    applyMet(m[0])
    await run()
  } catch (e: any) {
    error.value = '初始化失败：' + e.message
  }
})

function applySource(s: SourceRow) {
  form.value = {
    ...form.value,
    sourceId: s.id,
    stackHeight: s.stack_height_m,
    emission: s.emission_rate_g_s,
    stackDia: s.stack_diameter_m,
    exitV: s.exit_velocity_ms,
    stackT: s.stack_temp_k,
  }
}

function applyMet(m: MetRow) {
  form.value = {
    ...form.value,
    metId: m.id,
    windFrom: m.wind_from_deg,
    windSpeed: m.wind_speed_ms,
    stability: m.stability_class,
    ambientT: m.ambient_temp_k,
    pressure: m.pressure_hpa,
    background: m.background_conc_ug_m3,
  }
}

function onSelectSource(id: number) {
  const s = sources.value.find((x) => x.id === id)
  if (s) {
    applySource(s)
    run()
  }
}
function onSelectMet(id: number) {
  const m = meteorology.value.find((x) => x.id === id)
  if (m) {
    applyMet(m)
    run()
  }
}

async function run() {
  if (isCalm.value) {
    result.value = null
    error.value =
      `静风（u=${form.value.windSpeed} m/s < 阈值 ${form.value.calmThreshold} m/s）：` +
      '定常高斯烟羽输运假设失效，模型拒绝硬算，不输出任何浓度场。'
    return
  }
  loading.value = true
  error.value = null
  const s = sources.value.find((x) => x.id === form.value.sourceId)!
  try {
    result.value = await api.plumeGrid({
      source: {
        name: s.name,
        lon: s.lon,
        lat: s.lat,
        stack_height_m: form.value.stackHeight,
        emission_rate_g_s: form.value.emission,
        stack_diameter_m: form.value.stackDia,
        exit_velocity_ms: form.value.exitV,
        stack_temp_k: form.value.stackT,
        pollutant: s.pollutant,
      },
      meteorology: {
        name: '界面情景',
        wind_from_deg: form.value.windFrom,
        wind_speed_ms: form.value.windSpeed,
        stability_class: form.value.stability,
        ambient_temp_k: form.value.ambientT,
        pressure_hpa: form.value.pressure,
        background_conc_ug_m3: form.value.background,
      },
      grid: {
        downwind_extent_m: form.value.downwindExtent,
        crosswind_extent_m: form.value.crosswindExtent,
        upwind_extent_m: form.value.upwindExtent,
        nx: form.value.nx,
        ny: form.value.ny,
      },
      plume_rise: { use_plume_rise: form.value.useRise },
      parameterization: form.value.parameterization,
      power_law:
        form.value.parameterization === 'power_law'
          ? { ay: form.value.ay, py: form.value.py, az: form.value.az, pz: form.value.pz }
          : null,
      calm_threshold_ms: form.value.calmThreshold,
    })
  } catch (e: any) {
    result.value = null
    if (e.apiError?.error === 'calm_wind') {
      error.value = e.apiError.message
    } else {
      error.value = e.message || '计算失败'
    }
  } finally {
    loading.value = false
  }
}

const stops = computed(() =>
  result.value ? legendStops(result.value.iso_levels_ug_m3) : [],
)
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <h1>离线高斯烟羽情景演示</h1>
      <span class="sub">平坦地形 · 稳态风 · 显式参数化 · 环境课程教学</span>
      <span class="spacer" />
      <span class="repo">数据后端：{{ repo === 'postgis' ? 'PostgreSQL/PostGIS' : '内存虚构数据（PostGIS 未连接时回退）' }}</span>
    </header>

    <ControlPanel
      :sources="sources"
      :meteorology="meteorology"
      v-model:form="form"
      :loading="loading"
      @select-source="onSelectSource"
      @select-met="onSelectMet"
      @run="run"
    />

    <div class="map-wrap">
      <MapView
        :result="result"
        :show-fill="showFill"
        :show-iso="showIso"
        :show-bg="showBg"
      />
      <div
        v-if="result && stops.length"
        class="legend"
        style="left:12px;bottom:12px"
      >
        <div>
          <b>烟羽贡献浓度</b>（μg/m³，不含背景）
        </div>
        <div class="bar">
          <span
            v-for="s in stops"
            :key="s.level"
            :style="{ flex: 1, background: s.color }"
          />
        </div>
        <div class="labels">
          <span>{{ stops[0].level }}</span>
          <span>{{ stops[stops.length - 1].level }}</span>
        </div>
        <div class="bgrow">
          <label class="toggle" style="margin:4px 0 2px">
            <input type="checkbox" v-model="showFill" /> 烟羽贡献等值区
          </label>
          <label class="toggle" style="margin:2px 0">
            <input type="checkbox" v-model="showIso" /> 烟羽贡献等值线
          </label>
          <label class="toggle" style="margin:2px 0">
            <input type="checkbox" v-model="showBg" />
            背景值叠加（均匀 {{ result.background_conc_ug_m3 }} μg/m³）
          </label>
          <div class="muted" style="font-size:10px;margin-top:2px">
            总浓度＝烟羽贡献＋背景值，见右侧结果分解与悬停读数
          </div>
        </div>
      </div>
      <div v-if="isCalm" class="notice err" style="position:absolute;top:12px;left:50%;transform:translateX(-50%);z-index:6;max-width:560px">
        {{ error }}
      </div>
      <div class="disclaimer-foot">
        教学模型：不得用于真实事故预警或法规达标判定
      </div>
    </div>

    <ResultPanel :result="result" :error="error" />
  </div>
</template>
