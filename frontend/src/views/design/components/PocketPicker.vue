<template>
  <div class="pocket-picker" data-testid="pocket-picker">
    <a-steps :current="currentStep" size="small" class="pocket-stepper" data-testid="pocket-stepper">
      <a-step :title="t('design.pocket.project')" />
      <a-step :title="t('design.pocket.target')" />
      <a-step :title="t('design.pocket.protein')" />
      <a-step :title="t('design.pocket.structure')" />
      <a-step :title="t('design.pocket.pocket')" />
    </a-steps>

    <a-spin :spinning="loadingProjects">
      <a-row :gutter="16">
        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.project')">
            <a-select
              v-model:value="selectedProject"
              show-search
              option-filter-prop="label"
              :placeholder="t('design.pocket.projectPlaceholder')"
              data-testid="pocket-project"
              @change="handleProjectChange"
            >
              <a-select-option
                v-for="project in projects"
                :key="project.id"
                :value="project.id"
                :label="project.name"
              >
                {{ project.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.target')">
            <a-select
              v-model:value="selectedTarget"
              :disabled="!selectedProject"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingTargets"
              data-testid="pocket-target"
              @change="handleTargetChange"
            >
              <a-select-option v-for="target in targets" :key="target.id" :value="target.id">
                {{ target.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.protein')">
            <a-select
              v-model:value="selectedProtein"
              :disabled="!selectedTarget"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingProteins"
              data-testid="pocket-protein"
              @change="handleProteinChange"
            >
              <a-select-option v-for="protein in proteins" :key="protein.id" :value="protein.id">
                {{ protein.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.structure')">
            <a-select
              v-model:value="selectedStructure"
              :disabled="!selectedProtein"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingStructures"
              data-testid="pocket-structure"
              @change="handleStructureChange"
            >
              <a-select-option
                v-for="(structure, index) in structures"
                :key="structure.id"
                :value="structure.id"
              >
                {{ structureLabel(structure, index) }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.pocket')">
            <a-select
              v-model:value="selectedPocket"
              :disabled="!selectedStructure"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingPockets"
              data-testid="pocket-pocket"
              @change="handlePocketChange"
            >
              <a-select-option v-for="pocket in pockets" :key="pocket.id" :value="pocket.id">
                {{ pocketLabel(pocket) }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 上游缺结构：就地预测结构 -->
      <section v-if="selectedProtein && !structures.length" class="relay-panel" data-testid="pocket-missing-structure">
        <div class="relay-title">{{ t('design.upstream.missingStructure') }}</div>
        <StructurePredictForm
          :protein-id="selectedProtein"
          @submitted="snapshotStructures"
          @completed="handleStructurePredicted"
          @error="onRelayError"
        />
      </section>

      <!-- 上游缺已选口袋：就地预测 / 选定 -->
      <section v-else-if="selectedStructure && !pockets.length" class="relay-panel" data-testid="pocket-missing-pocket">
        <div class="relay-title">{{ t('design.upstream.missingPocket') }}</div>
        <PocketPredictPanel
          :structure-id="selectedStructure"
          @selected="handleRelayPocketSelected"
          @predicted="onRelayPredicted"
        />
      </section>

      <a-alert v-if="error" type="warning" show-icon :message="error" />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  listDesignProjects,
  listProjectTargets,
  listProteinStructures,
  listStructurePockets,
  loadTargetProteins,
} from '@/api/design'
import StructurePredictForm from '@/components/design/StructurePredictForm.vue'
import PocketPredictPanel from '@/components/design/PocketPredictPanel.vue'
import { selectNewlyAdded } from '@/domain/design/pipeline'
import type {
  PocketSummary,
  ProteinDetail,
  ProteinStructureDetail,
  TargetSummary,
} from '@/types/targets'
import type { ResearchProject } from '@/types/projects'
import type { DesignPocketSelection } from '@/types/design'

const props = defineProps<{
  modelValue: DesignPocketSelection | null
  defaultProjectId?: string
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: DesignPocketSelection | null): void
}>()

const { t } = useI18n()

const projects = ref<ResearchProject[]>([])
const targets = ref<TargetSummary[]>([])
const proteins = ref<ProteinDetail[]>([])
const structures = ref<ProteinStructureDetail[]>([])
const pockets = ref<PocketSummary[]>([])

const selectedProject = ref<string | undefined>(props.modelValue?.projectId)
const selectedTarget = ref<string | undefined>(props.modelValue?.targetId)
const selectedProtein = ref<string | undefined>(props.modelValue?.proteinId)
const selectedStructure = ref<string | undefined>(props.modelValue?.structureId)
const selectedPocket = ref<string | undefined>(props.modelValue?.pocketId)
const structureSnapshot = ref<string[]>([])

const loadingProjects = ref(false)
const loadingTargets = ref(false)
const loadingProteins = ref(false)
const loadingStructures = ref(false)
const loadingPockets = ref(false)
const error = ref('')

const currentStep = computed(() => {
  if (!selectedProject.value) return 0
  if (!selectedTarget.value) return 1
  if (!selectedProtein.value) return 2
  if (!selectedStructure.value) return 3
  if (!selectedPocket.value) return 4
  return 5
})

function structureLabel(structure: ProteinStructureDetail, index: number): string {
  return structure.source_type ? `${structure.source_type} · ${index + 1}` : `#${index + 1}`
}

function pocketLabel(pocket: PocketSummary): string {
  const rank = pocket.rank === null ? '-' : `#${pocket.rank}`
  const score = pocket.score === null ? '' : ` · ${pocket.score.toFixed(3)}`
  return `${rank}${score}`
}

function clearBelow(level: 'target' | 'protein' | 'structure' | 'pocket'): void {
  if (level === 'target') {
    targets.value = []
    selectedTarget.value = undefined
  }
  if (level === 'target' || level === 'protein') {
    proteins.value = []
    selectedProtein.value = undefined
  }
  if (level !== 'pocket') {
    structures.value = []
    selectedStructure.value = undefined
  }
  pockets.value = []
  selectedPocket.value = undefined
  emit('update:modelValue', null)
}

function emitPocketSelection(pocket: PocketSummary): void {
  if (
    !selectedProject.value ||
    !selectedTarget.value ||
    !selectedProtein.value ||
    !selectedStructure.value
  ) {
    emit('update:modelValue', null)
    return
  }
  emit('update:modelValue', {
    projectId: selectedProject.value,
    targetId: selectedTarget.value,
    proteinId: selectedProtein.value,
    structureId: selectedStructure.value,
    pocketId: pocket.id,
    pocketLabel: pocketLabel(pocket),
    score: pocket.score,
  })
}

async function loadProjects(): Promise<void> {
  loadingProjects.value = true
  error.value = ''
  try {
    projects.value = await listDesignProjects()
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingProjects.value = false
  }
}

async function handleProjectChange(value: unknown): Promise<void> {
  clearBelow('target')
  if (typeof value !== 'string') {
    return
  }
  loadingTargets.value = true
  try {
    targets.value = await listProjectTargets(value)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingTargets.value = false
  }
}

async function handleTargetChange(value: unknown): Promise<void> {
  clearBelow('protein')
  if (typeof value !== 'string') {
    return
  }
  loadingProteins.value = true
  try {
    proteins.value = await loadTargetProteins(value)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingProteins.value = false
  }
}

async function handleProteinChange(value: unknown): Promise<void> {
  clearBelow('structure')
  selectedStructure.value = undefined
  structures.value = []
  if (typeof value !== 'string') {
    return
  }
  loadingStructures.value = true
  try {
    structures.value = await listProteinStructures(value)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingStructures.value = false
  }
}

async function loadPocketsForStructure(structureId: string): Promise<void> {
  loadingPockets.value = true
  pockets.value = []
  selectedPocket.value = undefined
  try {
    const all = await listStructurePockets(structureId)
    pockets.value = all.filter(pocket => pocket.selected)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingPockets.value = false
  }
}

async function handleStructureChange(value: unknown): Promise<void> {
  clearBelow('pocket')
  selectedPocket.value = undefined
  pockets.value = []
  if (typeof value !== 'string') {
    return
  }
  await loadPocketsForStructure(value)
}

function snapshotStructures(): void {
  structureSnapshot.value = structures.value.map(structure => structure.id)
}

async function handleStructurePredicted(): Promise<void> {
  if (!selectedProtein.value) return
  loadingStructures.value = true
  try {
    const fresh = await listProteinStructures(selectedProtein.value)
    structures.value = fresh
    const added = selectNewlyAdded(structureSnapshot.value, fresh)
    if (added) {
      selectedStructure.value = added.id
      await loadPocketsForStructure(added.id)
    }
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingStructures.value = false
  }
}

async function handleRelayPocketSelected(pocket: PocketSummary): Promise<void> {
  if (!selectedStructure.value) return
  try {
    const all = await listStructurePockets(selectedStructure.value)
    pockets.value = all.filter(item => item.selected)
    const chosen = pockets.value.find(item => item.id === pocket.id) ?? pockets.value[0]
    if (chosen) {
      selectedPocket.value = chosen.id
      emitPocketSelection(chosen)
    }
  } catch {
    error.value = t('design.pocket.loadFailed')
  }
}

function onRelayPredicted(): void {
  error.value = ''
}

function onRelayError(message: string): void {
  error.value = message || t('design.pocket.loadFailed')
}

function handlePocketChange(value: unknown): void {
  if (typeof value !== 'string') {
    emit('update:modelValue', null)
    return
  }
  const pocket = pockets.value.find(item => item.id === value)
  if (!pocket) {
    emit('update:modelValue', null)
    return
  }
  emitPocketSelection(pocket)
}

onMounted(async () => {
  await loadProjects()
  if (!selectedProject.value && props.defaultProjectId) {
    selectedProject.value = props.defaultProjectId
    await handleProjectChange(props.defaultProjectId)
  }
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.pocket-stepper {
  margin-bottom: @spacing-lg;

  :deep(.ant-steps-item-title) {
    font-size: @font-size-xs;
    white-space: nowrap;
  }
}

.relay-panel {
  margin-top: @spacing-md;
  padding: @spacing-md;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-md;
  background: @accent-color-light;
}

.relay-title {
  margin-bottom: @spacing-sm;
  color: @accent-color;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
}

.pocket-picker__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: @warning-color;
}
</style>
