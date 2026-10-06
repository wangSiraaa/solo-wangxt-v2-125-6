<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { ChecksReport, PlumeGridResponse } from '../types'
import { api } from '../api'
import { legendStops } from '../colors'

const props = defineProps<{
  result: PlumeGridResponse | null
  error: string | null
}>()

const tab = ref<'result' | 'wind' | 'checks'>('result')
const checks = ref<ChecksReport | null>(null)
const checksError = ref('')
const windInput = ref(270)
const windInfo = ref<any>(null)

async function loadChecks() {
  checksError.value = ''
  try {
    checks.value = await api.checks()
  } catch (e: any) {
    checksError.value = e.message
  }
}

async function loadWind() {
  try {
    windInfo.value = await api.windCheck(windInput.value)
  } catch (e: any) {
    windInfo.value = { error: e.message }
  }
}

watch(
  () => props.result?.wind.wind_from_deg,
  (v) => {
    if (typeof v === 'number') {
      windInput.value = v
      loadWind()
    }
  },
)

onMounted(() => {
  loadChecks()
  loadWind()
})

function fmt(v: number, d = 2) {
  if (!Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })
}
</script>

<template>
  <div class="panel right">
    <div class="tabs">
      <button :class="{ active: tab === 'result' }" @click="tab = 'result'">
        结果分解
      </button>
      <button :class="{ active: tab === 'wind' }" @click="tab = 'wind'">
        风向换算检查
      </button>
      <button :class="{ active: tab === 'checks' }" @click="tab = 'checks'">
        解析核对
      </button>
    </div>

    <template v-if="tab === 'result'">
      <div v-if="error" class="notice err">{{ error }}</div>
      <template v-else-if="result">
        <div class="section">
          <h2>浓度分解（μg/m³）</h2>
          <dl class="kv">
            <dt>烟羽贡献 最大值</dt>
            <dd><b>{{ fmt(result.diagnostics.max_plume_conc_ug_m3) }}</b></dd>
            <dt>背景浓度（空间常数）</dt>
            <dd>{{ fmt(result.background_conc_ug_m3) }}</dd>
            <dt>总浓度 最大值</dt>
            <dd>
              {{
                fmt(
                  Math.max(...result.total_conc_ug_m3.flat().filter(isFinite)),
                )
              }}
            </dd>
          </dl>
          <div class="muted" style="font-size:11px;margin-top:4px">
            总量 = 烟羽贡献 + 背景值；三者分别返回。
          </div>
        </div>

        <div class="section">
          <h2>课堂阈值超阈统计（教学口径，非法定限值）</h2>
          <template v-if="result.threshold_statistics">
            <div class="notice warn" style="font-size:11px">
              {{ result.threshold_statistics.not_a_legal_limit }}
            </div>
            <dl class="kv">
              <dt>自定义阈值</dt>
              <dd>{{ fmt(result.threshold_statistics.threshold_ug_m3) }} μg/m³</dd>
              <dt>网格间距（下风向/横风向）</dt>
              <dd>
                {{ fmt(result.threshold_statistics.method.spacing_downwind_m, 1) }} /
                {{ fmt(result.threshold_statistics.method.spacing_crosswind_m, 1) }} m
              </dd>
              <dt>采样框总面积</dt>
              <dd>{{ fmt(result.threshold_statistics.method.sampling_box_area_m2 / 1e6, 3) }} km²</dd>
            </dl>
            <table class="meta-tbl" style="margin-top:8px">
              <tr><th>口径</th><th>超阈单元</th><th>面积</th><th>占采样框</th></tr>
              <tr>
                <td><span class="sw sw-plume"></span>烟羽贡献</td>
                <td class="mono">{{ result.threshold_statistics.plume.n_exceedance_cells }}</td>
                <td class="mono">
                  {{ fmt(result.threshold_statistics.plume.exceedance_area_km2, 3) }} km²
                </td>
                <td class="mono">
                  {{ fmt(result.threshold_statistics.plume.fraction_of_sampling_box_percent, 1) }}%
                </td>
              </tr>
              <tr>
                <td><span class="sw sw-total"></span>总浓度</td>
                <td class="mono">{{ result.threshold_statistics.total.n_exceedance_cells }}</td>
                <td class="mono">
                  {{ fmt(result.threshold_statistics.total.exceedance_area_km2, 3) }} km²
                </td>
                <td class="mono">
                  {{ fmt(result.threshold_statistics.total.fraction_of_sampling_box_percent, 1) }}%
                </td>
              </tr>
            </table>
            <div v-if="result.threshold_statistics.plume.empty && result.threshold_statistics.total.empty"
              class="notice info" style="margin-top:8px">
              阈值高于采样框内全部浓度值：烟羽贡献与总浓度超阈面积均为 0
              （该分辨率下无超阈采样单元）。
            </div>
            <dl class="kv" style="margin-top:8px">
              <dt>建议范围外格点数</dt>
              <dd>
                <template v-if="result.threshold_statistics.recommended_range.applicable">
                  {{ result.threshold_statistics.recommended_range.n_nodes_out_of_range }}
                  <span class="muted">
                    （Briggs {{ result.threshold_statistics.recommended_range.briggs_valid_range_m[0] / 1000 }}–
                    {{ result.threshold_statistics.recommended_range.briggs_valid_range_m[1] / 1000 }} km）
                  </span>
                </template>
                <span v-else class="muted">不适用（幂律参数化）</span>
              </dd>
              <dt>烟羽超阈单元中越界</dt>
              <dd>
                {{ result.threshold_statistics.plume.n_exceedance_cells_out_of_recommended_range }}
              </dd>
              <dt>总浓度超阈单元中越界</dt>
              <dd>
                {{ result.threshold_statistics.total.n_exceedance_cells_out_of_recommended_range }}
              </dd>
            </dl>
            <div class="muted" style="font-size:11px;margin-top:6px;line-height:1.55">
              {{ result.threshold_statistics.background_effect_note }}<br />
              {{ result.threshold_statistics.method.interpolation_note }}
            </div>
          </template>
          <div v-else class="muted">暂无阈值统计（静风时模型不输出浓度场）。</div>
        </div>

        <div class="section">
          <h2>有效源高</h2>
          <dl class="kv">
            <dt>烟囱几何高度 H</dt>
            <dd>{{ fmt(result.source_term.stack_height_m, 1) }} m</dd>
            <dt>抬升 Δh</dt>
            <dd>{{ fmt(result.plume_rise_delta_h_m, 1) }} m</dd>
            <dt>有效源高 H_e</dt>
            <dd><b>{{ fmt(result.effective_stack_height_m, 1) }} m</b></dd>
          </dl>
        </div>

        <div class="section">
          <h2>峰值位置</h2>
          <dl class="kv">
            <dt>下风向 x_peak</dt>
            <dd>
              {{ fmt(result.diagnostics.max_location_downwind_crosswind_m[0], 0) }} m
            </dd>
            <dt>横风向 y</dt>
            <dd>
              {{ fmt(result.diagnostics.max_location_downwind_crosswind_m[1], 0) }} m
            </dd>
          </dl>
        </div>

        <div class="section">
          <h2>图例（等值级，μg/m³）</h2>
          <div
            v-for="s in legendStops(result.iso_levels_ug_m3)"
            :key="s.level"
            style="display:flex;align-items:center;gap:8px;margin:2px 0"
          >
            <span
              :style="{
                display: 'inline-block', width: '22px', height: '10px',
                background: s.color, border: '1px solid #ccc',
              }"
            />
            <span class="mono">≥ {{ fmt(s.level, s.level < 1 ? 2 : 1) }}</span>
          </div>
        </div>

        <div class="section">
          <h2>采样与适用范围提示</h2>
          <div class="notice info">
            {{ result.grid.resolution_disclaimer }}
          </div>
          <div v-if="result.grid.flat_earth_warning" class="notice warn">
            采样尺度超过 {{ 30 }} km，平面近似误差增大；本教学模型不替代正式投影计算。
          </div>
          <dl class="kv">
            <dt>Briggs 建议 x 区间</dt>
            <dd>
              {{ result.validity.briggs_valid_range_m[0] / 1000 }}–
              {{ result.validity.briggs_valid_range_m[1] / 1000 }} km
            </dd>
            <dt>越界/近源栅格数</dt>
            <dd>
              {{ result.diagnostics.n_out_of_briggs_range_cells }} /
              {{ result.diagnostics.n_near_source_cells_lt_100m }}
            </dd>
          </dl>
        </div>

        <div class="notice warn">{{ result.disclaimer }}</div>
      </template>
      <div v-else class="muted">调整参数后点击「运行烟羽计算」。</div>
    </template>

    <template v-if="tab === 'wind'">
      <div class="section">
        <h2>风向 ↔ 地图坐标换算检查</h2>
        <label class="field">
          <span class="lbl">气象来向角 wind_from_deg（°）<b>{{ windInput }}</b></span>
          <input type="range" min="0" max="359" step="1" v-model.number="windInput"
            @input="loadWind" />
        </label>
        <div v-if="windInfo && !windInfo.error" class="notice info">
          {{ windInfo.interpretation }}
        </div>
        <table v-if="windInfo && !windInfo.error" class="meta-tbl">
          <tr><th>量</th><th>值</th></tr>
          <tr><td>来向角</td><td class="mono">{{ windInfo.wind_from_deg }}°</td></tr>
          <tr><td>输运方位角</td><td class="mono">{{ windInfo.transport_bearing_deg }}°</td></tr>
          <tr><td>下风向单位向量 (E,N)</td>
            <td class="mono">{{ windInfo.downwind_unit_E_N.join(', ') }}</td></tr>
          <tr><td>横风向单位向量 (E,N)</td>
            <td class="mono">{{ windInfo.crosswind_unit_E_N.join(', ') }}</td></tr>
          <tr><td>正交性 d·c（应≈0）</td>
            <td class="mono">{{ windInfo.dot_product_check }}</td></tr>
          <tr><td>单位长度 |d|（应=1）</td>
            <td class="mono">{{ windInfo.norm_check }}</td></tr>
        </table>
        <div v-if="result" class="notice info" style="margin-top:10px">
          当前情景：{{ result.wind.interpretation }}；下风向 d =
          ({{ result.wind.downwind_unit_E_N.join(', ') }})
        </div>
        <div class="muted" style="font-size:11px;margin-top:8px">
          约定：wind_from_deg 为风“从哪吹来”，烟羽走向 = (风向+180) mod 360。
          地图为 EPSG:4326 经纬度，内部是以源为原点的局部东(E)-北(N)平面（米）。
        </div>
      </div>
    </template>

    <template v-if="tab === 'checks'">
      <div class="section">
        <h2>
          解析核对用例
          <span :class="['badge', checks?.all_passed ? 'ok' : 'bad']">
            {{ checks ? `${checks.n_passed}/${checks.n_total}` : '…' }}
          </span>
        </h2>
        <p class="muted" style="font-size:11px">{{ checks?.note }}</p>
        <div v-if="checksError" class="notice err">{{ checksError }}</div>
        <div
          v-for="c in checks?.results"
          :key="c.id"
          :class="['check-item', { fail: !c.passed }]"
        >
          <div class="t">
            <span>{{ c.passed ? '✅' : '❌' }}</span>{{ c.title }}
          </div>
          <div class="d">{{ c.description }}</div>
          <div class="cmp">
            期望 <span class="exp">{{ c.expected }}</span><br />
            实际 <span class="act">{{ c.actual }}</span>
          </div>
        </div>
        <button class="ghost" @click="loadChecks">重新运行核对</button>
      </div>
    </template>
  </div>
</template>
