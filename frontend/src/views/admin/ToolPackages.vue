<template>
  <div class="admin-tool-packages">
    <AppPageHeader :title="t('admin.toolPackages')" :subtitle="t('admin.toolPackagesSubtitle')">
      <template #actions>
        <a-button type="primary" @click="openCreateModal">
          <PlusOutlined />
          注册 Tool Package v2
        </a-button>
      </template>
    </AppPageHeader>

    <a-alert
      class="contract-alert"
      type="info"
      show-icon
      message="新模型部署主路径：Tool Package v2"
      description="在模型侧 adapter 中适配原始输入输出，平台只识别标准 Artifact 输入/输出槽；旧语义映射仅作为历史工具兼容路径。"
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
      title="注册 Tool Package v2"
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
        <a-form-item label="Tool Package manifest JSON">
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
  import {
    createToolPackage,
    getToolPackage,
    listToolPackages,
    publishToolPackage
  } from '@/api/tool-packages'
  import type { ToolPackage } from '@/types/tool-packages'

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

  const selectedManifest = computed(() => selectedPackage.value?.current_version?.manifest ?? {})
  const formattedSelectedManifest = computed(() =>
    JSON.stringify(selectedManifest.value, null, 2)
  )
  const validationErrors = computed(
    () => selectedPackage.value?.current_version?.validation_errors ?? []
  )
  const artifactInputs = computed(() => artifactSlots('inputs'))
  const artifactOutputs = computed(() => artifactSlots('outputs'))
  const publishReadinessType = computed(() => {
    if (selectedPackage.value?.status === 'published') return 'success'
    if (!selectedPackage.value?.current_version?.is_signed) return 'warning'
    if (selectedPackage.value?.current_version?.validation_status !== 'valid') return 'error'
    return 'info'
  })
  const publishReadinessMessage = computed(() => {
    const version = selectedPackage.value?.current_version
    if (!version) return '当前 Package 没有版本，不能发布'
    if (selectedPackage.value?.status === 'published') return '已发布，可被平台运行时选择'
    if (version.validation_status !== 'valid') return '当前版本未通过契约校验，不能发布'
    if (!version.is_signed || !version.signature) return '当前版本缺少签名，发布前必须补签名'
    return '当前版本已签名且校验通过，可以发布'
  })

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
  }

  async function handleCreatePackage() {
    let manifest: Record<string, unknown>
    try {
      manifest = JSON.parse(manifestText.value) as Record<string, unknown>
    } catch {
      message.error('manifest JSON 格式不正确')
      return
    }

    saving.value = true
    try {
      await createToolPackage({
        manifest,
        signature: signatureText.value.trim() || null
      })
      message.success('Tool Package 已注册')
      resetCreateModal()
      page.value = 1
      await loadPackages()
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

  function validationColor(status?: string): string {
    if (status === 'valid') return 'green'
    if (status === 'invalid') return 'red'
    return 'default'
  }

  function contractSummary(item: ToolPackage): string {
    const artifacts = asRecord(item.current_version?.manifest.artifacts)
    const inputs = Array.isArray(artifacts?.inputs) ? artifacts.inputs.length : 0
    const outputs = Array.isArray(artifacts?.outputs) ? artifacts.outputs.length : 0
    return `${inputs} 输入 / ${outputs} 输出`
  }

  function variantSummary(item: ToolPackage): string {
    const variants = item.current_version?.manifest.variants
    if (!Array.isArray(variants)) return '无 variants'
    return variants
      .map(variant => asRecord(variant)?.accelerator)
      .filter(Boolean)
      .join(' · ') || `${variants.length} variants`
  }

  function asRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null
  }

  function artifactSlots(kind: 'inputs' | 'outputs'): Record<string, unknown>[] {
    const artifacts = asRecord(selectedManifest.value.artifacts)
    const slots = artifacts?.[kind]
    return Array.isArray(slots)
      ? slots
          .map(slot => asRecord(slot))
          .filter((slot): slot is Record<string, unknown> => Boolean(slot))
      : []
  }

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
  .modal-alert {
    margin-bottom: @spacing-sm;
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
