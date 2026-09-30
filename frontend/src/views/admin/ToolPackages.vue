<template>
  <div class="admin-tool-packages">
    <AppPageHeader :title="t('admin.toolPackages')" :subtitle="t('admin.toolPackagesSubtitle')">
      <template #actions>
        <a-button type="primary" @click="openCreateModal">
          <PlusOutlined />
          登记模型交付包
        </a-button>
      </template>
    </AppPageHeader>

    <a-alert
      class="contract-alert"
      type="info"
      show-icon
      message="第一步：登记并校验模型交付物"
      description="交付包包含运行环境、模型适配器和标准 Artifact 契约。发布交付包不会自动创建可运行工具；校验并发布后，请在详情中创建平台工具。"
    />

    <a-card>
      <a-table
        :columns="columns"
        :data-source="packages"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'package'">
            <div class="package-cell">
              <strong>{{ record.name }}</strong>
              <span>{{ record.slug }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'version'">
            <a-space size="small" wrap>
              <a-tag>{{ record.current_version?.version || '-' }}</a-tag>
              <a-tag :color="record.current_version?.is_signed ? 'green' : 'orange'">
                {{ record.current_version?.is_signed ? '已签名' : '未签名' }}
              </a-tag>
              <a-tag :color="validationColor(record.current_version?.validation_status)">
                {{ record.current_version?.validation_status || 'unknown' }}
              </a-tag>
            </a-space>
          </template>
          <template v-else-if="column.key === 'contract'">
            <div class="contract-cell">
              <span>{{ contractSummary(record) }}</span>
              <small>{{ variantSummary(record) }}</small>
            </div>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'published' ? 'green' : 'default'">
              {{ record.status }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space size="small">
              <a-button size="small" @click="openDetail(record)">
                详情/校验
              </a-button>
              <a-button
                size="small"
                :disabled="record.status === 'published' || !record.current_version?.is_signed"
                @click="handlePublish(record)"
              >
                发布
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="createModalOpen"
      title="登记模型交付包"
      :confirm-loading="saving"
      width="760px"
      @ok="handleCreatePackage"
      @cancel="resetCreateModal"
    >
      <a-alert
        class="modal-alert"
        type="success"
        show-icon
        message="平台契约固定，模型侧 adapter 适配"
        description="manifest 中声明标准 Artifact 输入/输出、runtime 与 variants；不要再为新工具维护旧语义映射。"
      />
      <a-form layout="vertical">
        <a-form-item label="注册方式">
          <a-radio-group v-model:value="registrationEditor" button-style="solid">
            <a-radio-button value="guided">向导生成</a-radio-button>
            <a-radio-button value="json">粘贴 JSON</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <template v-if="registrationEditor === 'guided'">
          <a-alert
            class="guided-hint"
            type="info"
            show-icon
            message="填写模型基本信息和运行资源，平台会生成 v2 manifest"
            description="镜像 digest、权重清单和 fallback 包仍需填写真实值，避免发布不可复现的运行环境。"
          />
          <a-row :gutter="16">
            <a-col :span="14">
              <a-form-item label="工具名称" required>
                <a-input v-model:value="guidedDraft.name" placeholder="例如：Pocket Prediction" />
              </a-form-item>
            </a-col>
            <a-col :span="10">
              <a-form-item label="Slug" required>
                <a-input v-model:value="guidedDraft.slug" placeholder="pocket-prediction" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="版本" required>
                <a-input v-model:value="guidedDraft.version" placeholder="1.0.0" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="加速器">
                <a-select v-model:value="guidedDraft.accelerator">
                  <a-select-option value="cpu">CPU</a-select-option>
                  <a-select-option value="nvidia_cuda">NVIDIA CUDA</a-select-option>
                  <a-select-option value="haiguang_dcu">海光 DCU</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="简介">
            <a-textarea v-model:value="guidedDraft.description" :rows="2" placeholder="工具用途和适用场景" />
          </a-form-item>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="输入 Artifact" required>
                <a-input v-model:value="guidedDraft.inputName" addon-before="内部名称" />
                <a-input
                  v-model:value="guidedDraft.inputTitle"
                  addon-before="显示名称"
                  class="stacked-input"
                  placeholder="例如：靶标蛋白结构"
                />
                <a-select v-model:value="guidedDraft.inputType" class="stacked-input">
                  <a-select-option v-for="type in standardArtifactTypes" :key="type" :value="type">
                    {{ standardArtifactTypeLabel(type) }} · {{ type }}
                  </a-select-option>
                </a-select>
                <a-textarea
                  v-model:value="guidedDraft.inputDescription"
                  class="stacked-input"
                  :rows="2"
                  placeholder="输入文件的用途和格式要求"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="输出 Artifact" required>
                <a-input v-model:value="guidedDraft.outputName" addon-before="名称" />
                <a-select v-model:value="guidedDraft.outputType" class="stacked-input">
                  <a-select-option v-for="type in standardArtifactTypes" :key="type" :value="type">
                    {{ standardArtifactTypeLabel(type) }} · {{ type }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="科学参数">
            <ToolParameterSchemaEditor
              v-model:model-value="guidedDraft.parametersSchema"
              :allow-file-fields="false"
              @validity-change="setPackageParameterSchemaValidity"
            />
          </a-form-item>
          <a-row :gutter="16">
            <a-col :span="14">
              <a-form-item label="容器镜像" required>
                <a-input v-model:value="guidedDraft.image" placeholder="registry.example.com/model:1.0.0" />
              </a-form-item>
            </a-col>
            <a-col :span="10">
              <a-form-item label="Python">
                <a-input v-model:value="guidedDraft.python" placeholder="3.11" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="镜像 digest" required>
            <a-input v-model:value="guidedDraft.imageDigest" placeholder="sha256 加 64 位十六进制摘要" />
          </a-form-item>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="CPU 核数">
                <a-input-number v-model:value="guidedDraft.cpu" :min="0.1" :step="0.5" style="width: 100%" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="内存（MB）">
                <a-input-number v-model:value="guidedDraft.memoryMb" :min="128" :step="128" style="width: 100%" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="Entry point">
            <a-input v-model:value="guidedDraft.entrypoint" placeholder="python -m adapter" />
          </a-form-item>
          <a-collapse ghost>
            <a-collapse-panel key="runtime" header="高级运行时字段（发布前必填）">
              <a-form-item label="Fallback 包 URI" required>
                <a-input v-model:value="guidedDraft.fallbackUri" placeholder="s3://bucket/runtime.venv.tar.gz" />
              </a-form-item>
              <a-form-item label="Fallback SHA256" required>
                <a-input v-model:value="guidedDraft.fallbackSha256" />
              </a-form-item>
              <a-form-item label="权重清单 URI" required>
                <a-input v-model:value="guidedDraft.weightsUri" placeholder="s3://bucket/weights/manifest.json" />
              </a-form-item>
              <a-form-item label="权重清单 SHA256" required>
                <a-input v-model:value="guidedDraft.weightsSha256" />
              </a-form-item>
            </a-collapse-panel>
          </a-collapse>
        </template>

        <a-form-item v-else label="Tool Package manifest JSON">
          <a-textarea
            v-model:value="manifestText"
            :rows="16"
            placeholder='{"api_version":"aidd.sciminer/tool-package.v2","kind":"ToolPackage","metadata":{"slug":"model-standard","name":"Model Standard","version":"1.0.0"}}'
          />
        </a-form-item>
        <a-form-item label="签名（可选，发布前必需）">
          <a-input v-model:value="signatureText" placeholder="cosign:sha256:..." />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="detailDrawerOpen"
      title="Tool Package 详情与校验"
      width="860px"
      destroy-on-close
    >
      <a-skeleton v-if="detailLoading" active :paragraph="{ rows: 10 }" />
      <template v-else-if="selectedPackage">
        <section class="detail-section">
          <h3>版本详情</h3>
          <a-descriptions bordered size="small" :column="1">
            <a-descriptions-item label="Package">
              {{ selectedPackage.name }} / {{ selectedPackage.slug }}
            </a-descriptions-item>
            <a-descriptions-item label="版本">
              {{ selectedPackage.current_version?.version || '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="Manifest Digest">
              {{ selectedPackage.current_version?.manifest_digest || '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="状态">
              {{ selectedPackage.status }}
            </a-descriptions-item>
          </a-descriptions>
          <p class="next-step-hint">
            {{ selectedPackage.status === 'published'
              ? '交付包已发布，可以创建平台工具并配置分类与执行方式。'
              : '完成签名、校验并发布交付包后，即可创建平台工具。' }}
          </p>
          <router-link
            v-if="selectedPackage.status === 'published'"
            :to="{ path: '/admin/tools/create', query: { mode: 'package', package_id: selectedPackage.id } }"
          >
            <a-button type="primary">创建平台工具</a-button>
          </router-link>
          <a-button v-else type="primary" disabled>创建平台工具</a-button>
        </section>

        <section class="detail-section">
          <h3>签名与发布状态</h3>
          <a-alert
            show-icon
            :type="publishReadinessType"
            :message="publishReadinessMessage"
          />
        </section>

        <section class="detail-section">
          <h3>校验结果</h3>
          <a-alert
            v-if="validationErrors.length"
            type="error"
            show-icon
            message="validation_errors"
            :description="validationErrors.join('；')"
          />
          <a-alert v-else type="success" show-icon message="当前版本无校验错误" />
        </section>

        <section class="detail-section">
          <h3>标准 Artifact 契约</h3>
          <div class="artifact-contract-grid">
            <article>
              <strong>输入槽</strong>
              <span v-for="slot in artifactInputs" :key="String(slot.name || slot.type)">
                {{ slot.name || '-' }} · {{ slot.type || '-' }}
              </span>
              <small v-if="!artifactInputs.length">未声明输入槽</small>
            </article>
            <article>
              <strong>输出槽</strong>
              <span v-for="slot in artifactOutputs" :key="String(slot.name || slot.type)">
                {{ slot.name || '-' }} · {{ slot.type || '-' }} ·
                {{ slot.cardinality || 'one' }}
              </span>
              <small v-if="!artifactOutputs.length">未声明输出槽</small>
            </article>
          </div>
        </section>

        <section class="detail-section">
          <h3>Manifest 预览</h3>
          <pre class="manifest-viewer">{{ formattedSelectedManifest }}</pre>
        </section>

        <section class="detail-section legacy-migration-entry">
          <h3>旧工具迁移入口</h3>
          <p>旧语义映射工具应迁移为 Tool Package v2 后再作为新模型部署主路径。</p>
          <router-link to="/admin/tools">打开旧工具管理</router-link>
        </section>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { PlusOutlined } from '@ant-design/icons-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ToolParameterSchemaEditor from '@/components/tools/ToolParameterSchemaEditor.vue'
  import {
    createToolPackage,
    getToolPackage,
    listToolPackages,
    publishToolPackage
  } from '@/api/tool-packages'
  import {
    formatToolPackageManifest,
    getToolPackageArtifactSlots,
    getToolPackageContractSummary,
    getToolPackagePublishReadiness,
    getToolPackageValidationColor,
    getToolPackageValidationErrors,
    getToolPackageVariantSummary
  } from '@/domain/tool-packages'
  import {
    buildToolPackageManifest,
    createToolPackageGuidedDraft
  } from '@/domain/tool-packages/manifest'
  import { getStandardArtifactTypeLabelKey } from '@/domain/tools/standard-artifact-inputs'
  import type { ToolPackage } from '@/types/tool-packages'
  import { validateParameterSchema } from '@/domain/tools/parameter-schema'
  import { WORKFLOW_ARTIFACT_SEMANTIC_TYPES } from '@/workflow/semantic-types'

  const { t } = useI18n()
  const loading = ref(false)
  const saving = ref(false)
  const detailLoading = ref(false)
  const createModalOpen = ref(false)
  const detailDrawerOpen = ref(false)
  const packages = ref<ToolPackage[]>([])
  const selectedPackage = ref<ToolPackage | null>(null)
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const manifestText = ref('')
  const signatureText = ref('')
  const registrationEditor = ref<'guided' | 'json'>('guided')
  const guidedDraft = ref(createToolPackageGuidedDraft())
  const packageParameterSchemaValid = ref(true)
  const standardArtifactTypes = WORKFLOW_ARTIFACT_SEMANTIC_TYPES.filter(type => type.includes('@'))

  const columns = [
    { title: 'Tool Package', key: 'package' },
    { title: '版本/校验', key: 'version', width: 230 },
    { title: '标准 Artifact 契约', key: 'contract' },
    { title: '状态', key: 'status', width: 110 },
    { title: '操作', key: 'actions', width: 110 }
  ]

  const pagination = computed(() => ({
    current: page.value,
    pageSize: pageSize.value,
    total: total.value,
    showSizeChanger: true
  }))

  const formattedSelectedManifest = computed(() =>
    formatToolPackageManifest(selectedPackage.value)
  )
  const validationErrors = computed(() => getToolPackageValidationErrors(selectedPackage.value))
  const artifactInputs = computed(() => getToolPackageArtifactSlots(selectedPackage.value, 'inputs'))
  const artifactOutputs = computed(() => getToolPackageArtifactSlots(selectedPackage.value, 'outputs'))
  const publishReadiness = computed(() => getToolPackagePublishReadiness(selectedPackage.value))
  const publishReadinessType = computed(() => publishReadiness.value.type)
  const publishReadinessMessage = computed(() => publishReadiness.value.message)

  async function loadPackages() {
    loading.value = true
    try {
      const response = await listToolPackages({ page: page.value, page_size: pageSize.value })
      packages.value = response.data.items
      total.value = response.data.total
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'Tool Package 加载失败')
    } finally {
      loading.value = false
    }
  }

  function handleTableChange(nextPagination: { current?: number; pageSize?: number }) {
    page.value = nextPagination.current ?? 1
    pageSize.value = nextPagination.pageSize ?? pageSize.value
    void loadPackages()
  }

  function openCreateModal() {
    createModalOpen.value = true
  }

  function resetCreateModal() {
    createModalOpen.value = false
    manifestText.value = ''
    signatureText.value = ''
    registrationEditor.value = 'guided'
    guidedDraft.value = createToolPackageGuidedDraft()
    packageParameterSchemaValid.value = true
  }

  function setPackageParameterSchemaValidity(valid: boolean) {
    packageParameterSchemaValid.value = valid
  }

  function standardArtifactTypeLabel(type: string): string {
    const key = getStandardArtifactTypeLabelKey(type)
    return key ? t(key) : type
  }

  async function handleCreatePackage() {
    let manifest: Record<string, unknown>
    if (registrationEditor.value === 'guided') {
      const schemaErrors = validateParameterSchema(guidedDraft.value.parametersSchema, {
        allowLegacyUiTypes: false,
      })
      if (!packageParameterSchemaValid.value || schemaErrors.length > 0) {
        message.error(schemaErrors[0] || '请先修正科学参数 Schema')
        return
      }
      manifest = buildToolPackageManifest(guidedDraft.value)
    } else {
      try {
        manifest = JSON.parse(manifestText.value) as Record<string, unknown>
      } catch {
        message.error('manifest JSON 格式不正确')
        return
      }
    }

    saving.value = true
    try {
      const response = await createToolPackage({
        manifest,
        signature: signatureText.value.trim() || null
      })
      message.success('模型交付包已登记')
      resetCreateModal()
      page.value = 1
      await loadPackages()
      await openDetail(response.data)
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'Tool Package 注册失败')
    } finally {
      saving.value = false
    }
  }

  async function handlePublish(item: ToolPackage) {
    try {
      const response = await publishToolPackage(item.id)
      packages.value = packages.value.map(current => current.id === item.id ? response.data : current)
      message.success('Tool Package 已发布')
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'Tool Package 发布失败')
    }
  }

  async function openDetail(item: ToolPackage) {
    selectedPackage.value = item
    detailDrawerOpen.value = true
    detailLoading.value = true
    try {
      const response = await getToolPackage(item.id)
      selectedPackage.value = response.data
      packages.value = packages.value.map(current =>
        current.id === item.id ? response.data : current
      )
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'Tool Package 详情加载失败')
    } finally {
      detailLoading.value = false
    }
  }

  const validationColor = getToolPackageValidationColor
  const contractSummary = getToolPackageContractSummary
  const variantSummary = getToolPackageVariantSummary

  onMounted(() => {
    void loadPackages()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .admin-tool-packages {
    display: grid;
    gap: @spacing-lg;
  }

  .contract-alert,
  .modal-alert,
  .guided-hint {
    margin-bottom: @spacing-sm;
  }

  .stacked-input {
    margin-top: @spacing-xs;
  }

  .package-cell strong,
  .package-cell span,
  .contract-cell span,
  .contract-cell small {
    display: block;
  }

  .package-cell span,
  .contract-cell small {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .detail-section {
    display: grid;
    gap: @spacing-sm;
    margin-bottom: @spacing-lg;

    h3 {
      margin: 0;
      color: @text-primary;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
    }

    p {
      margin: 0;
      color: @text-secondary;
      line-height: @line-height-base;
    }
  }

  .artifact-contract-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: @spacing-md;

    article {
      display: grid;
      gap: 4px;
      padding: @spacing-md;
      border: 1px solid @border-color;
      border-radius: @border-radius-md;
      background: @bg-surface;
    }

    strong {
      color: @text-primary;
    }

    span,
    small {
      color: @text-secondary;
      font-size: @font-size-sm;
      word-break: break-word;
    }
  }

  .manifest-viewer {
    max-height: 360px;
    margin: 0;
    padding: @spacing-md;
    overflow: auto;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-surface;
    color: @text-primary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .legacy-migration-entry a {
    color: @accent-color;
    font-weight: @font-weight-medium;
  }
</style>
