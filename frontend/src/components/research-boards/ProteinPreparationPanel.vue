<template>
  <aside class="protein-preparation-panel" data-testid="protein-preparation-panel">
    <header>
      <ThunderboltOutlined />
      <span>蛋白制备</span>
    </header>

    <p class="target-name">{{ artifactName }}</p>

    <form data-testid="protein-preparation-submit" @submit.prevent="submit">
      <label for="protein-preparation-ph">pH</label>
      <input
        id="protein-preparation-ph"
        v-model.number="ph"
        data-testid="protein-preparation-ph"
        type="number"
        min="0"
        max="14"
        step="0.1"
        :disabled="disabled || loading"
      />

      <label class="checkbox-row">
        <input v-model="removeWater" type="checkbox" :disabled="disabled || loading" />
        <span>去水</span>
      </label>
      <label class="checkbox-row">
        <input v-model="keepMetals" type="checkbox" :disabled="disabled || loading" />
        <span>保留金属</span>
      </label>
      <label class="checkbox-row">
        <input v-model="keepCofactors" type="checkbox" :disabled="disabled || loading" />
        <span>保留辅因子</span>
      </label>
      <label class="checkbox-row">
        <input v-model="removeNonTargetLigands" type="checkbox" :disabled="disabled || loading" />
        <span>移除非目标配体</span>
      </label>

      <div class="output-group" aria-label="输出格式">
        <span>输出</span>
        <label class="checkbox-row">
          <input v-model="preparedPdb" type="checkbox" disabled />
          <span>Prepared PDB</span>
        </label>
        <label class="checkbox-row">
          <input v-model="receptorPdbqt" type="checkbox" :disabled="disabled || loading" />
          <span>Receptor PDBQT</span>
        </label>
      </div>

      <button type="submit" :disabled="disabled || loading || !canSubmit">
        {{ loading ? '制备中...' : '创建制备节点' }}
      </button>
    </form>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import type { ProteinPreparationOptions } from '@/api/protein-preparation'

const props = withDefaults(defineProps<{
  artifactName: string
  disabled?: boolean
  loading?: boolean
}>(), { disabled: false, loading: false })

const emit = defineEmits<{
  (event: 'submit', value: ProteinPreparationOptions): void
}>()

const ph = ref(7.4)
const removeWater = ref(true)
const keepMetals = ref(true)
const keepCofactors = ref(true)
const removeNonTargetLigands = ref(true)
const preparedPdb = ref(true)
const receptorPdbqt = ref(true)
const canSubmit = computed(() => Number.isFinite(ph.value) && ph.value >= 0 && ph.value <= 14)

watch(
  () => props.artifactName,
  () => {
    ph.value = 7.4
    removeWater.value = true
    keepMetals.value = true
    keepCofactors.value = true
    removeNonTargetLigands.value = true
    preparedPdb.value = true
    receptorPdbqt.value = true
  }
)

function submit() {
  if (!canSubmit.value || props.disabled || props.loading) return
  emit('submit', {
    ph: Number(ph.value),
    remove_water: removeWater.value,
    keep_metals: keepMetals.value,
    keep_cofactors: keepCofactors.value,
    remove_non_target_ligands: removeNonTargetLigands.value,
    output_formats: receptorPdbqt.value ? ['prepared_pdb', 'receptor_pdbqt'] : ['prepared_pdb'],
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.protein-preparation-panel {
  width: 260px;
  padding: @spacing-sm;
  border-left: 1px solid @border-color;
  background: @bg-surface;
}

.protein-preparation-panel header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: @spacing-sm;
  color: @text-primary;
  font-weight: 600;
}

.target-name {
  margin: 0 0 @spacing-sm;
  color: @text-secondary;
  font-size: @font-size-xs;
  overflow-wrap: anywhere;
}

.protein-preparation-panel form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.protein-preparation-panel label,
.output-group > span {
  color: @text-secondary;
  font-size: @font-size-xs;
}

.protein-preparation-panel input[type='number'] {
  height: 32px;
  padding: 0 8px;
  border: 1px solid @border-color;
  border-radius: @border-radius-sm;
  background: @bg-elevated;
  color: @text-primary;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.output-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: @spacing-xs;
}

.protein-preparation-panel button {
  min-height: 32px;
  border: 1px solid @accent-color;
  border-radius: @border-radius-sm;
  background: @accent-color;
  color: #fff;
  cursor: pointer;
}

.protein-preparation-panel button:disabled,
.protein-preparation-panel input:disabled {
  opacity: .5;
  cursor: not-allowed;
}
</style>
