<template>
  <div class="pocket-picker" data-testid="pocket-picker">
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
            <p v-if="selectedStructure && !loadingPockets && !pockets.length" class="pocket-picker__hint">
              {{ t('design.pocket.noSelectedPockets') }}
            </p>
          </a-form-item>
        </a-col>
      </a-row>

      <a-alert v-if="error" type="warning" show-icon :message="error" />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    listDesignProjects,
    listProjectTargets,
    listProteinStructures,
    listStructurePockets,
    loadTargetProteins,
  } from '@/api/design'
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

  const loadingProjects = ref(false)
  const loadingTargets = ref(false)
  const loadingProteins = ref(false)
  const loadingStructures = ref(false)
  const loadingPockets = ref(false)
  const error = ref('')

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

  async function handleStructureChange(value: unknown): Promise<void> {
    clearBelow('pocket')
    selectedPocket.value = undefined
    pockets.value = []
    if (typeof value !== 'string') {
      return
    }
    loadingPockets.value = true
    try {
      const all = await listStructurePockets(value)
      pockets.value = all.filter((pocket) => pocket.selected)
    } catch {
      error.value = t('design.pocket.loadFailed')
    } finally {
      loadingPockets.value = false
    }
  }

  function handlePocketChange(value: unknown): void {
    if (typeof value !== 'string') {
      emit('update:modelValue', null)
      return
    }
    const pocket = pockets.value.find((item) => item.id === value)
    if (!pocket || !selectedProject.value || !selectedTarget.value || !selectedProtein.value || !selectedStructure.value) {
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

  onMounted(() => {
    void loadProjects()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .pocket-picker__hint {
    margin: 8px 0 0;
    font-size: 12px;
    color: @warning-color;
  }
</style>
