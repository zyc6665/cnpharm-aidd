<template>
  <section class="aidd-agent-panel">
    <div class="agent-control-panel">
      <div class="agent-panel-head">
        <div>
          <span class="agent-kicker">{{ t('workflow.agent.kicker') }}</span>
          <h2>{{ t('workflow.agent.title') }}</h2>
          <p>{{ t('workflow.agent.subtitle') }}</p>
        </div>
        <a-tag color="blue">{{ t('workflow.agent.autoRouting') }}</a-tag>
      </div>

      <a-alert
        class="agent-project-alert"
        type="info"
        show-icon
        :message="t('workflow.agent.projectRequired')"
        :description="t('workflow.agent.projectRequiredDescription')"
      />

      <a-form class="agent-form" layout="vertical">
        <a-form-item :label="t('workflow.agent.projectLabel')">
          <a-select
            v-model:value="selectedProjectId"
            :loading="loadingProjects"
            :options="projectOptions"
            :placeholder="t('workflow.agent.projectPlaceholder')"
          />
        </a-form-item>

        <a-form-item :label="t('workflow.agent.messageLabel')">
          <a-textarea
            v-model:value="runMessage"
            :placeholder="t('workflow.agent.messagePlaceholder')"
            :auto-size="{ minRows: 4, maxRows: 6 }"
            :maxlength="500"
            show-count
          />
        </a-form-item>

        <div class="agent-submit-row">
          <a-form-item class="agent-file-field" :label="t('workflow.agent.inputFiles')">
            <a-upload
              v-model:file-list="agentFileUploads"
              accept=".pdb,.ent,.cif,.sdf,.csv"
              :before-upload="beforeUpload"
              :multiple="true"
            >
              <a-button>
                <UploadOutlined />
                {{ t('workflow.agent.selectInputFiles') }}
              </a-button>
            </a-upload>
            <p class="agent-file-hint">{{ t('workflow.agent.fileAutoDetectHint') }}</p>
          </a-form-item>

          <div class="agent-actions">
            <a-button
              type="primary"
              size="large"
              :loading="draftSubmitting"
              @click="generateWorkflowDraft"
            >
              <ApartmentOutlined />
              {{ t('workflow.agent.generateDraft') }}
            </a-button>
          </div>
        </div>
      </a-form>
    </div>

    <div class="agent-runtime-panel">
      <div class="runtime-header">
        <div>
          <span class="agent-kicker">{{ t('workflow.agent.draftWorkspace') }}</span>
          <h3>{{ t('workflow.agent.draftOnlyTitle') }}</h3>
        </div>
      </div>

      <p class="draft-only-description">
        {{ t('workflow.agent.draftOnlyDescription') }}
      </p>

      <div class="capability-strip">
        <span v-for="item in capabilityOptions" :key="item.key" class="capability-chip">
          <span class="capability-dot" />
          <span class="capability-copy">
            <strong>{{ item.title }}</strong>
            <small>{{ item.description }}</small>
          </span>
        </span>
      </div>

      <a-empty
        v-if="projectOptions.length === 0 && !loadingProjects"
        class="agent-empty"
        :description="t('workflow.agent.noProjects')"
      />
      <a-tag v-else-if="selectedProjectName" color="green">
        {{ t('workflow.agent.selectedProject', { name: selectedProjectName }) }}
      </a-tag>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { UploadFile } from 'ant-design-vue'
  import { ApartmentOutlined, UploadOutlined } from '@ant-design/icons-vue'
  import { createAiddWorkflowDraft } from '@/api/agents'
  import { uploadFile } from '@/api/files'
  import { listProjects } from '@/api/projects'
  import { useUserStore } from '@/stores'
  import type { AiddAgentRunCreateParams, AiddWorkflowDraft } from '@/types/models'
  import type { ResearchProject } from '@/types/projects'

  const emit = defineEmits<{
    draftGenerated: [draft: AiddWorkflowDraft, projectId: string]
  }>()

  const router = useRouter()
  const { t } = useI18n()
  const userStore = useUserStore()

  const runMessage = ref('')
  const agentFileUploads = ref<UploadFile[]>([])
  const projects = ref<ResearchProject[]>([])
  const selectedProjectId = ref<string | undefined>()
  const loadingProjects = ref(false)
  const draftSubmitting = ref(false)

  const capabilityOptions = computed(() => {
    return [
      {
        key: 'pocket_exploration',
        title: t('workflow.steps.pocketExploration.title'),
        description: t('workflow.steps.pocketExploration.description')
      },
      {
        key: 'molecule_generation',
        title: t('workflow.steps.moleculeGenerationOrVirtualScreening.title'),
        description: t('workflow.steps.moleculeGenerationOrVirtualScreening.description')
      },
      {
        key: 'binding_evaluation',
        title: t('workflow.steps.molecularDockingAndAffinityPrediction.title'),
        description: t('workflow.steps.molecularDockingAndAffinityPrediction.description')
      },
      {
        key: 'property_prediction',
        title: t('workflow.steps.propertyPrediction.title'),
        description: t('workflow.steps.propertyPrediction.description')
      }
    ]
  })

  const projectOptions = computed(() => {
    return projects.value
      .filter(project => project.status !== 'archived')
      .map(project => ({
        value: project.id,
        label: project.name
      }))
  })

  const selectedProjectName = computed(() => {
    return projects.value.find(project => project.id === selectedProjectId.value)?.name
  })

  function beforeUpload() {
    return false
  }

  async function loadProjects() {
    if (!userStore.isLoggedIn) {
      projects.value = []
      selectedProjectId.value = undefined
      return
    }

    loadingProjects.value = true
    try {
      const response = await listProjects()
      projects.value = response.data.items
      const firstProject = projectOptions.value[0]
      if (!selectedProjectId.value && firstProject) {
        selectedProjectId.value = firstProject.value
      }
    } finally {
      loadingProjects.value = false
    }
  }

  async function prepareAgentRequest(): Promise<AiddAgentRunCreateParams | null> {
    if (!userStore.isLoggedIn) {
      message.warning(t('workflow.agent.loginRequired'))
      router.push('/login')
      return null
    }

    if (!selectedProjectId.value) {
      message.warning(t('workflow.agent.projectRequiredWarning'))
      return null
    }

    const selectedFiles = agentFileUploads.value.filter(item => Boolean(item.originFileObj))
    if (selectedFiles.length === 0) {
      message.warning(t('workflow.agent.uploadRequired'))
      return null
    }

    const uploadedFileIds: string[] = []
    for (const uploadItem of selectedFiles) {
      const uploaded = await uploadFile(uploadItem.originFileObj as File)
      uploadedFileIds.push(uploaded.data.id.toString())
    }

    return {
      message: runMessage.value.trim() || t('workflow.agent.defaultMessage'),
      input_file_ids: uploadedFileIds
    }
  }

  async function generateWorkflowDraft() {
    draftSubmitting.value = true
    try {
      const request = await prepareAgentRequest()
      if (!request || !selectedProjectId.value) {
        return
      }

      const response = await createAiddWorkflowDraft(request)
      emit('draftGenerated', response.data, selectedProjectId.value)
      message.success(t('workflow.agent.draftGenerated'))
    } finally {
      draftSubmitting.value = false
    }
  }

  watch(
    () => [userStore.isLoggedIn, userStore.user?.id] as const,
    () => {
      void loadProjects()
    }
  )

  onMounted(() => {
    void loadProjects()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .aidd-agent-panel {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(340px, 0.7fr);
    gap: @spacing-lg;
    margin-bottom: 0;
  }

  .agent-control-panel,
  .agent-runtime-panel {
    min-width: 0;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-lg;
    background: @bg-elevated;
    box-shadow: @shadow-sm;
  }

  .agent-control-panel {
    padding: @spacing-xl;
  }

  .agent-runtime-panel {
    padding: @spacing-lg;
  }

  .agent-panel-head,
  .runtime-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .agent-panel-head h2,
  .runtime-header h3 {
    margin: 0;
    color: @text-color-light-primary;
    font-weight: 800;
  }

  .agent-panel-head p,
  .draft-only-description {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    line-height: 1.7;
  }

  .agent-kicker {
    display: block;
    margin-bottom: @spacing-xs;
    color: @primary-color;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .agent-project-alert {
    margin-bottom: @spacing-md;
  }

  .agent-form {
    margin-top: @spacing-lg;
  }

  .agent-submit-row {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: @spacing-lg;
  }

  .agent-file-field {
    flex: 1;
    margin-bottom: 0;
  }

  .agent-file-hint {
    margin: @spacing-xs 0 0;
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

  .agent-actions {
    display: flex;
    gap: @spacing-sm;
    margin-bottom: @spacing-sm;
  }

  .capability-strip {
    display: grid;
    gap: @spacing-sm;
    margin: @spacing-lg 0;
  }

  .capability-chip {
    display: flex;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    background: @bg-light-secondary;
  }

  .capability-dot {
    width: 8px;
    height: 8px;
    margin-top: 7px;
    border-radius: 50%;
    background: @primary-color;
  }

  .capability-copy {
    display: grid;
    gap: 2px;
  }

  .capability-copy strong {
    color: @text-color-light-primary;
  }

  .capability-copy small {
    color: @text-color-light-secondary;
    line-height: 1.5;
  }

  .agent-empty {
    margin-top: @spacing-lg;
  }

  @media (max-width: 1080px) {
    .aidd-agent-panel {
      grid-template-columns: 1fr;
    }

    .agent-submit-row {
      align-items: stretch;
      flex-direction: column;
    }

    .agent-actions,
    .agent-actions :deep(.ant-btn) {
      width: 100%;
    }
  }
</style>
