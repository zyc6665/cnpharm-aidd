<template>
  <a-drawer
    :open="open"
    :width="'min(960px, 96vw)'"
    placement="right"
    :title="t('design.results.compare.title')"
    :body-style="{ padding: '16px 20px 32px' }"
    @close="close"
  >
    <div class="compare" data-testid="molecule-compare-drawer">
      <p v-if="!molecules.length" class="compare__empty">
        {{ t('design.results.compare.empty') }}
      </p>

      <div v-else class="compare__scroll">
        <table class="compare-table">
          <thead>
            <tr>
              <th class="compare-table__label">{{ t('design.results.compare.property') }}</th>
              <th
                v-for="molecule in molecules"
                :key="molecule.key"
                class="compare-table__molecule"
                data-testid="molecule-compare-column"
                :data-index="molecule.index"
              >
                {{ t('design.results.moleculeIndex', { index: molecule.index }) }}
                <span v-if="isFavorite(molecule)" class="compare-table__mark" data-testid="molecule-compare-favorite">
                  ★
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th class="compare-table__label">{{ t('design.results.structureColumn') }}</th>
              <td v-for="molecule in molecules" :key="molecule.key">
                <div class="compare__structure">
                  <Smiles2DCell
                    v-if="molecule.smiles"
                    :smiles="molecule.smiles"
                    :width="180"
                    :height="130"
                  />
                  <span v-else class="compare__sequence">{{ molecule.sequence || '-' }}</span>
                </div>
              </td>
            </tr>

            <tr>
              <th class="compare-table__label">{{ t('design.results.compare.smiles') }}</th>
              <td v-for="molecule in molecules" :key="molecule.key">
                <div class="compare__smiles">
                  <code :title="molecule.smiles || molecule.sequence">
                    {{ molecule.smiles || molecule.sequence || '-' }}
                  </code>
                  <a-button
                    v-if="molecule.smiles || molecule.sequence"
                    type="text"
                    size="small"
                    :aria-label="t('design.results.compare.copy')"
                    data-testid="molecule-compare-copy"
                    @click="copySmiles(molecule.smiles || molecule.sequence)"
                  >
                    <CopyOutlined />
                  </a-button>
                </div>
              </td>
            </tr>


            <tr>
              <th class="compare-table__label">{{ t('design.results.compare.violations') }}</th>
              <td
                v-for="molecule in molecules"
                :key="molecule.key"
                data-testid="molecule-compare-violations"
                :data-violations="molecule.violations"
              >
                <a-tag v-if="molecule.violations !== null" :color="molecule.violations === 0 ? 'success' : molecule.violations === 1 ? 'warning' : 'error'">
                  {{ molecule.violations === 0 ? t('design.results.ro5PassBadge') : t('design.results.ro5ViolationsBadge', { count: molecule.violations }) }}
                </a-tag>
                <span v-else class="compare__na">-</span>
              </td>
            </tr>

            <tr v-for="row in metricRows" :key="row.key">
              <th class="compare-table__label" :title="row.label">{{ row.label }}</th>
              <td
                v-for="molecule in molecules"
                :key="`${molecule.key}-${row.key}`"
                :class="toneClass(metricFor(molecule, row.key)?.tone)"
                :data-tone="metricFor(molecule, row.key)?.tone ?? undefined"
                :data-testid="`molecule-compare-metric-${row.key}`"
              >
                {{ metricFor(molecule, row.key)?.value ?? t('design.results.compare.noValue') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </a-drawer>
</template>

<script lang="ts">
  import type { MetricTone } from '@/domain/molecules/druglikeness'

  export interface CompareMetric {
    key: string
    label: string
    value: string
    tone: MetricTone | null
  }

  export interface CompareMolecule {
    key: string
    index: number
    smiles: string
    sequence: string
    violations: number | null
    /** 已收藏（喜欢）标记，仅用于标题星标。 */
    favorite?: boolean
    metrics: CompareMetric[]
  }
</script>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { CopyOutlined } from '@ant-design/icons-vue'
  import { copyToClipboard } from '@/utils/clipboard'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'

  const props = withDefaults(
    defineProps<{
      open?: boolean
      molecules?: CompareMolecule[]
    }>(),
    { open: false, molecules: () => [] }
  )

  const emit = defineEmits<{ (event: 'update:open', value: boolean): void }>()

  const { t } = useI18n()

  /** 属性行按首次出现顺序对齐：先出现的分子决定了行顺序，缺失的属性显示「-」。 */
  const metricRows = computed(() => {
    const rows: Array<{ key: string; label: string }> = []
    const seen = new Set<string>()
    props.molecules.forEach(molecule => {
      molecule.metrics.forEach(metric => {
        if (seen.has(metric.key)) return
        seen.add(metric.key)
        rows.push({ key: metric.key, label: metric.label })
      })
    })
    return rows
  })

  function metricFor(molecule: CompareMolecule, key: string): CompareMetric | undefined {
    return molecule.metrics.find(metric => metric.key === key)
  }

  function toneClass(tone: MetricTone | null | undefined): string {
    return tone ? `tone tone--${tone}` : ''
  }

  function isFavorite(molecule: CompareMolecule): boolean {
    return molecule.favorite === true
  }

  function close(): void {
    emit('update:open', false)
  }

  async function copySmiles(text: string): Promise<void> {
    if (!text) return
    try {
      await copyToClipboard(text)
      message.success(t('common.copySuccess'))
    } catch {
      message.warning(t('design.results.copyFailed'))
    }
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .compare {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .compare__empty {
    margin: 48px 0;
    color: @text-tertiary;
    text-align: center;
  }

  .compare__scroll {
    overflow-x: auto;
  }

  .compare-table {
    width: 100%;
    border-collapse: collapse;
    font-size: @font-size-sm;
  }

  .compare-table th,
  .compare-table td {
    padding: 8px 10px;
    border-bottom: 1px solid @border-color;
    text-align: left;
    vertical-align: middle;
    word-break: break-all;
    overflow-wrap: anywhere;
  }

  .compare-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: @surface-sunken;
    color: @text-secondary;
    font-weight: @font-weight-medium;
    white-space: nowrap;
  }

  .compare-table__label {
    width: 132px;
    color: @text-secondary;
    font-weight: 500;
    white-space: nowrap;
    word-break: normal;
  }

  .compare-table__molecule {
    width: 220px;
    min-width: 200px;
    max-width: 260px;
  }

  .compare-table__mark {
    margin-left: 4px;
    color: @warning-color;
  }

  .compare__structure {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 130px;
    min-width: 160px;
  }

  .compare__sequence {
    font-family: @font-family-mono;
    font-size: 12px;
    color: @text-secondary;
    word-break: break-all;
  }

  .compare__smiles {
    display: flex;
    align-items: flex-start;
    gap: 4px;
    min-width: 150px;
  }

  .compare__smiles code {
    flex: 1 1 auto;
    min-width: 0;
    overflow-wrap: anywhere;
    color: @text-primary;
    font-family: @font-family-mono;
    font-size: 12px;
  }

  .compare__na {
    color: @text-tertiary;
  }

  /* 阈值语义色：与结果表格 / 详情面板同一套绿-琥珀-红口径 */
  .tone {
    font-weight: 600;
  }

  .tone--good {
    color: @success-color;
    background: fade(@success-color, 12%);
  }

  .tone--warn {
    color: @warning-color;
    background: fade(@warning-color, 14%);
  }

  .tone--bad {
    color: @error-color;
    background: fade(@error-color, 12%);
  }
</style>
