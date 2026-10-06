<script setup lang="ts">
import { computed } from 'vue'
import type { MetRow, SourceRow } from '../types'
import type { FormState } from '../form'

const props = defineProps<{
  sources: SourceRow[]
  meteorology: MetRow[]
  form: FormState
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:form', v: FormState): void
  (e: 'select-source', id: number): void
  (e: 'select-met', id: number): void
  (e: 'run'): void
  (e: 'threshold-change', value: number): void
}>()

function patch(p: Partial<FormState>) {
  emit('update:form', { ...props.form, ...p })
}

function onThresholdToggle(enabled: boolean) {
  // 启用/停用阈值立即重算：停用则请求不带阈值字段，地图超阈层与统计消失
  // （先显式同步本组件 props，再交给下一个事件循环发起请求，避免读到旧值）
  emit('update:form', { ...props.form, thresholdEnabled: enabled })
  setTimeout(() => {
    if (props.form.windSpeed >= props.form.calmThreshold) emit('run')
  }, 0)
}

function onThresholdRelease(value: number) {
  // 滑块松开：把最终值交给父组件写回后重算（@input 已同步标签显示）
  emit('threshold-change', value)
}

const isCalm = computed(() => props.form.windSpeed < props.form.calmThreshold)
</script>

<template>
  <div class="panel">
    <div class="section">
      <h2>虚构情景（教学数据，非真实设施）</h2>
      <label class="field">
        <span class="lbl">排放源</span>
        <select
          class="num"
          :value="form.sourceId"
          @change="emit('select-source', Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="s in sources" :key="s.id" :value="s.id">
            {{ s.name }}（{{ s.pollutant }}，H={{ s.stack_height_m }} m）
          </option>
        </select>
      </label>
      <label class="field">
        <span class="lbl">气象情景</span>
        <select
          class="num"
          :value="form.metId"
          @change="emit('select-met', Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="m in meteorology" :key="m.id" :value="m.id">
            {{ m.name }}
          </option>
        </select>
      </label>
      <div class="muted" style="font-size:11px">
        下列调整只用于本次计算请求，不会写回数据库记录。
      </div>
    </div>

    <div class="section">
      <h2>① 源项</h2>
      <label class="field">
        <span class="lbl">烟囱高度 H（m）<b>{{ form.stackHeight }}</b></span>
        <input data-test="height" type="range" min="5" max="250" step="1" :value="form.stackHeight"
          @input="patch({ stackHeight: Number(($event.target as HTMLInputElement).value) })" />
      </label>
      <label class="field">
        <span class="lbl">排放率 Q（g/s）<b>{{ form.emission }}</b></span>
        <input data-test="emission" type="range" min="0" max="200" step="0.5" :value="form.emission"
          @input="patch({ emission: Number(($event.target as HTMLInputElement).value) })" />
      </label>
      <details class="params">
        <summary>抬升参数（Holland，默认关闭）</summary>
        <div class="toggle">
          <input type="checkbox" :checked="form.useRise"
            @change="patch({ useRise: ($event.target as HTMLInputElement).checked })" />
          叠加烟气抬升 Δh
        </div>
        <div class="row2">
          <label class="field"><span class="lbl">出口内径 d（m）</span>
            <input class="num" type="number" step="0.1" :value="form.stackDia"
              @input="patch({ stackDia: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label class="field"><span class="lbl">出口流速（m/s）</span>
            <input class="num" type="number" step="0.5" :value="form.exitV"
              @input="patch({ exitV: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label class="field"><span class="lbl">烟气温度（K）</span>
            <input class="num" type="number" step="1" :value="form.stackT"
              @input="patch({ stackT: Number(($event.target as HTMLInputElement).value) })" /></label>
        </div>
      </details>
    </div>

    <div class="section">
      <h2>② 气象（稳态风）</h2>
      <label class="field">
        <span class="lbl">风速 u（m/s）<b>{{ form.windSpeed }}</b></span>
        <input data-test="windspeed" type="range" min="0" max="12" step="0.1" :value="form.windSpeed"
          @input="patch({ windSpeed: Number(($event.target as HTMLInputElement).value) })" />
      </label>
      <div v-if="isCalm" class="notice err">
        静风：u={{ form.windSpeed }} m/s &lt; 阈值 {{ form.calmThreshold }} m/s。
        定常高斯烟羽不适用，模型将<b>拒绝计算</b>（不用近零风速除出巨大浓度）。
      </div>
      <label class="field">
        <span class="lbl">
          风向（气象来向角，0=北来风，顺时针）<b>{{ form.windFrom }}°</b>
        </span>
        <input data-test="windfrom" type="range" min="0" max="359" step="1" :value="form.windFrom"
          @input="patch({ windFrom: Number(($event.target as HTMLInputElement).value) })" />
      </label>
      <label class="field">
        <span class="lbl">Pasquill 稳定度</span>
        <select class="num" :value="form.stability"
          @change="patch({ stability: ($event.target as HTMLSelectElement).value as FormState['stability'] })">
          <option value="A">A 极不稳定</option>
          <option value="B">B 不稳定</option>
          <option value="C">C 弱不稳定</option>
          <option value="D">D 中性</option>
          <option value="E">E 较稳定</option>
          <option value="F">F 稳定</option>
        </select>
      </label>
      <div class="row2">
        <label class="field"><span class="lbl">环境温度（K）</span>
          <input class="num" type="number" step="0.1" :value="form.ambientT"
            @input="patch({ ambientT: Number(($event.target as HTMLInputElement).value) })" /></label>
        <label class="field"><span class="lbl">气压（hPa）</span>
          <input class="num" type="number" step="1" :value="form.pressure"
            @input="patch({ pressure: Number(($event.target as HTMLInputElement).value) })" /></label>
      </div>
      <label class="field">
        <span class="lbl">背景浓度（μg/m³，与烟羽分开计量）<b>{{ form.background }}</b></span>
        <input data-test="background" type="range" min="0" max="100" step="0.5" :value="form.background"
          @input="patch({ background: Number(($event.target as HTMLInputElement).value) })" />
      </label>
    </div>

    <div class="section">
      <h2>③ 弥散参数化（显式系数）</h2>
      <label class="field">
        <select class="num" :value="form.parameterization"
          @change="patch({ parameterization: ($event.target as HTMLSelectElement).value as any })">
          <option value="briggs_rural">Briggs 乡村系数（默认，建议 0.1–10 km）</option>
          <option value="power_law">幂律 σ=a·x^p（解析核对用）</option>
        </select>
      </label>
      <details v-if="form.parameterization === 'power_law'" class="params">
        <summary>幂律系数</summary>
        <div class="row2">
          <label class="field"><span class="lbl">ay</span>
            <input class="num" type="number" step="0.01" :value="form.ay"
              @input="patch({ ay: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label class="field"><span class="lbl">py</span>
            <input class="num" type="number" step="0.1" :value="form.py"
              @input="patch({ py: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label class="field"><span class="lbl">az</span>
            <input class="num" type="number" step="0.01" :value="form.az"
              @input="patch({ az: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label class="field"><span class="lbl">pz</span>
            <input class="num" type="number" step="0.1" :value="form.pz"
              @input="patch({ pz: Number(($event.target as HTMLInputElement).value) })" /></label>
        </div>
      </details>
    </div>

    <div class="section">
      <h2>④ 采样网格（只改变采样，不改变输入）</h2>
      <div class="row2">
        <label class="field"><span class="lbl">下风向范围（m）</span>
          <input class="num" type="number" step="100" :value="form.downwindExtent"
            @input="patch({ downwindExtent: Number(($event.target as HTMLInputElement).value) })" /></label>
        <label class="field"><span class="lbl">横风向范围（m）</span>
          <input class="num" type="number" step="100" :value="form.crosswindExtent"
            @input="patch({ crosswindExtent: Number(($event.target as HTMLInputElement).value) })" /></label>
        <label class="field"><span class="lbl">上风向延伸（m）</span>
          <input class="num" type="number" step="50" :value="form.upwindExtent"
            @input="patch({ upwindExtent: Number(($event.target as HTMLInputElement).value) })" /></label>
      </div>
      <label class="field">
        <span class="lbl">下风向格点数 nx <b>{{ form.nx }}</b></span>
        <input data-test="nx" type="range" min="21" max="201" step="10" :value="form.nx"
          @input="patch({ nx: Number(($event.target as HTMLInputElement).value) })" />
      </label>
      <label class="field">
        <span class="lbl">横风向格点数 ny <b>{{ form.ny }}</b></span>
        <input data-test="ny" type="range" min="11" max="121" step="2" :value="form.ny"
          @input="patch({ ny: Number(($event.target as HTMLInputElement).value) })" />
      </label>
      <label class="field"><span class="lbl">静风阈值（m/s）</span>
        <input class="num" type="number" min="0.1" max="5" step="0.1" :value="form.calmThreshold"
          @input="patch({ calmThreshold: Number(($event.target as HTMLInputElement).value) })" /></label>

      <div class="threshold-box">
        <label class="toggle">
          <input type="checkbox" :checked="form.thresholdEnabled"
            @change="onThresholdToggle(($event.target as HTMLInputElement).checked)" />
          启用课堂自定义浓度阈值
        </label>
        <label class="field" :class="{ disabled: !form.thresholdEnabled }">
          <span class="lbl">浓度阈值（μg/m³，<b>非法定限值</b>）<b>{{ form.concentrationThreshold }}</b></span>
          <input data-test="threshold" type="range" min="0" max="500" step="1"
            :value="form.concentrationThreshold" :disabled="!form.thresholdEnabled"
            @input="patch({ concentrationThreshold: Number(($event.target as HTMLInputElement).value) })"
            @change="onThresholdRelease(Number(($event.target as HTMLInputElement).value))" />
        </label>
        <div class="muted" style="font-size:10px;line-height:1.4">
          阈值仅用于教学统计：后端按当前网格实际米制间距，分别统计
          <b>烟羽贡献</b>与<b>总浓度</b>的超阈面积、占采样框比例与
          Briggs 建议范围外格点数；地图按整单元叠加（非等值线插值面积）。
          调整阈值松开滑块后自动重算；改变 nx/ny 只改采样，统计随各自网格重算，不回写源项与气象。
        </div>
      </div>

      <button @click="emit('run')" :disabled="loading || isCalm">
        {{ loading ? '计算中…' : '运行烟羽计算' }}
      </button>
      <span v-if="isCalm" class="badge bad">静风，已停用</span>
    </div>
  </div>
</template>
