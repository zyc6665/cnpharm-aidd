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
      description="交付包包含运行环境、模型适配器和标准 Artifact 契约。发布不会自动创建可运行工具；管理员可从详情注册 K8s 候选版本。平台不构建模型镜像。"
    />

    <a-card>
      <a-table
        :scroll="{ x: 'max-content' }"
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
          <a-form-item label="输入 Artifact" required>
            <div v-for="(item, index) in guidedDraft.inputs" :key="'input-' + index" class="artifact-row">
              <a-input v-model:value="item.name" placeholder="内部名称，如 receptor" style="width: 180px" />
              <a-select v-model:value="item.type" style="width: 230px">
                <a-select-option v-for="type in standardArtifactTypes" :key="type" :value="type" :title="type">
                  {{ standardArtifactTypeLabel(type) }}
                </a-select-option>
              </a-select>
              <a-checkbox v-model:checked="item.required">必填</a-checkbox>
              <a-button type="text" danger @click="guidedDraft.inputs.splice(index, 1)">删除</a-button>
            </div>
            <a-button type="dashed" block @click="guidedDraft.inputs.push(createGuidedInput())">+ 添加输入</a-button>
          </a-form-item>

          <a-form-item label="输出 Artifact" required>
            <div v-for="(item, index) in guidedDraft.outputs" :key="'output-' + index" class="artifact-row">
              <a-input v-model:value="item.name" placeholder="内部名称，如 ligands" style="width: 180px" />
              <a-select v-model:value="item.type" style="width: 230px">
                <a-select-option v-for="type in standardArtifactTypes" :key="type" :value="type" :title="type">
                  {{ standardArtifactTypeLabel(type) }}
                </a-select-option>
              </a-select>
              <a-select v-model:value="item.cardinality" style="width: 100px">
                <a-select-option value="one">单值</a-select-option>
                <a-select-option value="many">多值</a-select-option>
              </a-select>
              <a-checkbox v-model:checked="item.required">必填</a-checkbox>
              <a-button type="text" danger @click="guidedDraft.outputs.splice(index, 1)">删除</a-button>
            </div>
            <a-button type="dashed" block @click="guidedDraft.outputs.push(createGuidedOutput())">+ 添加输出</a-button>
          </a-form-item>
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
            placeholder='{"api_version":"aidd.sciminer/tool-package","kind":"ToolPackage","metadata":{"slug":"model-standard","name":"Model Standard","version":"1.0.0"}}'
          />
        </a-form-item>
        <a-form-item label="签名（可选，发布前必需）">
          <a-input v-model:value="signatureText" placeholder="cosign:sha256:..." />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="kubernetesRegistrationModalOpen"
      title="注册 Kubernetes 候选版本"
      :confirm-loading="kubernetesRegistrationSaving"
      :ok-button-props="{ disabled: !canSubmitKubernetesRegistration }"
      width="680px"
      @ok="handleRegisterKubernetesVersion"
    >
      <a-alert
        v-if="kubernetesOptions"
        class="modal-alert"
        type="info"
        show-icon
        :message="`镜像：${kubernetesOptions.image || '未声明'}`"
        :description="`Image digest：${kubernetesOptions.image_digest || '缺失'}；Manifest digest：${kubernetesOptions.manifest_digest}`"
      />
      <a-form layout="vertical">
        <a-form-item label="运行变体" required>
          <a-select
            v-model:value="registrationVariantName"
            :options="registrationVariantOptions"
            @change="handleRegistrationVariantChange"
          />
        </a-form-item>
        <a-form-item label="平台资源档位" required>
          <a-select v-model:value="registrationResourceProfile" :options="resourceProfileOptions" />
        </a-form-item>
        <a-form-item label="ToolVersion 版本号" required>
          <a-input v-model:value="registrationToolVersion" :maxlength="50" />
        </a-form-item>
        <a-alert
          v-if="kubernetesOptions?.existing_tool"
          class="modal-alert"
          type="warning"
          show-icon
          :message="`将为 ${kubernetesOptions.existing_tool.slug} 添加版本`"
          description="不会修改 Tool.current_version_id；已在运行的 SSH 版本保持不变。"
        />
        <a-form-item v-else label="新工具分类" required>
          <a-select
            v-model:value="registrationCategoryId"
            :options="categoryOptions"
            placeholder="选择分类"
          />
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
              ? '已发布的交付包可以继续注册 Kubernetes 候选版本。'
              : '完成签名、校验并发布交付包后，即可注册 Kubernetes 候选版本。' }}
          </p>
        </section>

        <section v-if="selectedPackage.status === 'published'" class="detail-section">
          <h3>Kubernetes 候选版本</h3>
          <a-alert
            show-icon
            type="info"
            message="注册只创建 inactive ToolVersion，不会切换现有 SSH 当前版本。"
            description="新建的平台工具保持草稿状态。候选版本需通过成功的真实 smoke 后才能提升；原 SSH 版本保留，可用于回切。"
          />
          <a-alert
            class="modal-alert"
            show-icon
            type="warning"
            message="真实 Smoke 的基础设施前置条件"
            description="执行前确认 K8s Worker、MinIO 已部署，且 Registry 镜像可被节点拉取。输入文件需先上传到平台，或绑定已有 ArtifactVersion。"
          />
          <a-alert
            v-if="kubernetesOptionsError"
            show-icon
            type="warning"
            message="Kubernetes 注册选项暂不可用"
            :description="kubernetesOptionsError"
          />
          <a-alert
            v-if="kubernetesOptions && !canRegisterKubernetesPackage(kubernetesOptions)"
            show-icon
            type="warning"
            message="该 Package 暂不满足 Kubernetes 注册条件"
            description="需要声明 k8s_job executor、有效的 sha256 镜像摘要、可用变体和平台登记的资源档位。"
          />
          <a-space wrap>
            <a-button
              type="primary"
              :loading="kubernetesOptionsLoading"
              :disabled="!canOpenKubernetesRegistration"
              @click="openKubernetesRegistration"
            >
              注册 K8s 候选版本
            </a-button>
            <a-button
              :loading="kubernetesOptionsLoading"
              @click="loadKubernetesRegistrationOptions"
            >
              刷新注册选项
            </a-button>
          </a-space>
          <template v-if="kubernetesOptions?.existing_tool">
            <p class="next-step-hint">
              平台工具：{{ kubernetesOptions.existing_tool.name }}（{{ kubernetesOptions.existing_tool.status }}）
              · 当前版本：{{ kubernetesOptions.existing_tool.current_version_id || '未设置' }}
            </p>
            <a-table
              :scroll="{ x: 'max-content' }"
              v-if="kubernetesOptions.tool_versions.length"
              class="tool-version-table"
              size="small"
              :columns="toolVersionColumns"
              :data-source="kubernetesOptions.tool_versions"
              :pagination="false"
              row-key="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'version'">
                  <a-space size="small" wrap>
                    <span>{{ record.version }}</span>
                    <a-tag v-if="isCurrentVersion(record.id)" color="blue">当前</a-tag>
                    <a-tag v-else-if="record.is_active" color="green">已激活</a-tag>
                    <a-tag v-if="record.deprecated" color="default">已废弃</a-tag>
                  </a-space>
                </template>
                <template v-else-if="column.key === 'executor'">
                  {{ record.executor_type || '未知' }}
                </template>
                <template v-else-if="column.key === 'smoke'">
                  <a-tag :color="getSmokeStatusColor(record.smoke_status, record.executor_type)">
                    {{ getSmokeStatusLabel(record.smoke_status, record.executor_type) }}
                  </a-tag>
                  <small v-if="record.smoke_task_id" class="smoke-task-id">
                    {{ record.smoke_task_id }}
                  </small>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-space size="small">
                    <a-button
                      v-if="canSmokeKubernetesToolVersion(record)"
                      size="small"
                      :loading="smokeVersionId === record.id"
                      @click="openSmokeModal(record)"
                    >
                      Smoke
                    </a-button>
                    <a-popconfirm
                      v-if="canPromoteKubernetesToolVersion(record, kubernetesOptions?.existing_tool?.current_version_id)"
                      :title="`将 ${record.version} 切换为当前版本？`"
                      ok-text="确认切换"
                      cancel-text="取消"
                      @confirm="handlePromoteToolVersion(record)"
                    >
                      <a-button
                        size="small"
                        type="link"
                        :loading="promotionVersionId === record.id"
                      >
                        {{ record.is_active ? '回切' : '提升' }}
                      </a-button>
                    </a-popconfirm>
                    <span
                      v-if="!canSmokeKubernetesToolVersion(record) && !canPromoteKubernetesToolVersion(record, kubernetesOptions?.existing_tool?.current_version_id)"
                      class="muted-action"
                    >
                      {{ isCurrentVersion(record.id) ? '当前版本' : '不可操作' }}
                    </span>
                  </a-space>
                </template>
              </template>
            </a-table>
            <AppEmptyState
              v-else
              size="compact"
              :title="t('admin.toolVersionsEmptyTitle')"
              :description="t('admin.toolVersionsEmptyHint')"
            />
          </template>
          <AppEmptyState
            v-else-if="kubernetesOptions && !kubernetesOptionsLoading"
            size="compact"
            :title="t('admin.toolVersionsCandidateTitle')"
            :description="t('admin.toolVersionsCandidateHint')"
          />
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

    <a-modal
      v-model:open="smokeModalOpen"
      title="执行候选版本 Smoke"
      :confirm-loading="smokeSubmitting"
      :ok-button-props="{ disabled: !parsedSmokeInput }"
      width="680px"
      @ok="handleSubmitSmoke"
    >
      <a-alert
        class="modal-alert"
        show-icon
        type="info"
        :message="`候选版本：${selectedSmokeVersion?.version || '-'}`"
        description="填写 TaskInput JSON。文件需先上传到平台，并在 file_ids、input_bindings 或 standard_input_uploads 中提供对应 ID。"
      />
      <a-form-item label="Smoke 输入 JSON" required>
        <a-textarea v-model:value="smokeInputText" :rows="14" />
      </a-form-item>
      <a-alert
        v-if="!parsedSmokeInput"
        show-icon
        type="error"
        message="请输入有效的 JSON 对象"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { PlusOutlined } from '@ant-design/icons-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import ToolParameterSchemaEditor from '@/components/tools/ToolParameterSchemaEditor.vue'
  import {
    createToolPackage,
    getKubernetesRegistrationOptions,
    getToolPackage,
    listToolPackages,
    publishToolPackage,
    registerKubernetesToolVersion
  } from '@/api/tool-packages'
  import {
    adminGetToolCategories,
    promoteToolVersion,
    smokeToolVersion
  } from '@/api/tools'
  import {
    canPromoteKubernetesToolVersion,
    canRegisterKubernetesPackage,
    canSmokeKubernetesToolVersion,
    createDefaultKubernetesToolVersion,
    formatToolPackageManifest,
    getToolPackageArtifactSlots,
    getToolPackageContractSummary,
    getToolPackagePublishReadiness,
    getToolPackageValidationColor,
    getToolPackageValidationErrors,
    getKubernetesRegistrationVariants,
    getToolPackageVariantSummary,
    parseKubernetesSmokeInput
  } from '@/domain/tool-packages'
  import {
    buildToolPackageManifest,
    createGuidedInput,
    createGuidedOutput,
    createToolPackageGuidedDraft
  } from '@/domain/tool-packages/manifest'
  import { getStandardArtifactTypeLabelKey } from '@/domain/tools/standard-artifact-inputs'
  import type {
    KubernetesToolVersionSummary,
    KubernetesRegistrationOptions,
    ToolPackage
  } from '@/types/tool-packages'
  import type { Category } from '@/types/models'
  import { validateParameterSchema } from '@/domain/tools/parameter-schema'
  import { WORKFLOW_ARTIFACT_SEMANTIC_TYPES } from '@/workflow/semantic-types'

  const { t } = useI18n()
  const loading = ref(false)
  const saving = ref(false)
  const detailLoading = ref(false)
  const createModalOpen = ref(false)
  const detailDrawerOpen = ref(false)
  const kubernetesOptionsLoading = ref(false)
  const kubernetesOptionsError = ref('')
  const kubernetesRegistrationModalOpen = ref(false)
  const kubernetesRegistrationSaving = ref(false)
  const smokeModalOpen = ref(false)
  const smokeSubmitting = ref(false)
  const smokeVersionId = ref<string | null>(null)
  const promotionVersionId = ref<string | null>(null)
  const packages = ref<ToolPackage[]>([])
  const selectedPackage = ref<ToolPackage | null>(null)
  const selectedSmokeVersion = ref<KubernetesToolVersionSummary | null>(null)
  const kubernetesOptions = ref<KubernetesRegistrationOptions | null>(null)
  const categories = ref<Category[]>([])
  const registrationVariantName = ref('')
  const registrationResourceProfile = ref('')
  const registrationToolVersion = ref('')
  const registrationCategoryId = ref<string | undefined>()
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const manifestText = ref('')
  const signatureText = ref('')
  const smokeInputText = ref(JSON.stringify({
    params: {},
    file_ids: [],
    input_bindings: {},
    standard_input_uploads: {}
  }, null, 2))
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

  const toolVersionColumns = [
    { title: '版本', key: 'version', width: 240 },
    { title: '执行器', key: 'executor', width: 100 },
    { title: 'Smoke', key: 'smoke', width: 130 },
    { title: '操作', key: 'actions', width: 170 }
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
  const parsedSmokeInput = computed(() => parseKubernetesSmokeInput(smokeInputText.value))
  const validationErrors = computed(() => getToolPackageValidationErrors(selectedPackage.value))
  const artifactInputs = computed(() => getToolPackageArtifactSlots(selectedPackage.value, 'inputs'))
  const artifactOutputs = computed(() => getToolPackageArtifactSlots(selectedPackage.value, 'outputs'))
  const publishReadiness = computed(() => getToolPackagePublishReadiness(selectedPackage.value))
  const publishReadinessType = computed(() => publishReadiness.value.type)
  const publishReadinessMessage = computed(() => publishReadiness.value.message)
  const canOpenKubernetesRegistration = computed(() =>
    Boolean(
      selectedPackage.value?.status === 'published' &&
      canRegisterKubernetesPackage(kubernetesOptions.value)
    )
  )
  const canSubmitKubernetesRegistration = computed(() =>
    Boolean(
      canOpenKubernetesRegistration.value &&
      registrationVariantName.value &&
      registrationResourceProfile.value &&
      registrationToolVersion.value.trim() &&
      (kubernetesOptions.value?.existing_tool || registrationCategoryId.value)
    )
  )
  const registrationVariantOptions = computed(() =>
    getKubernetesRegistrationVariants(kubernetesOptions.value).map(variant => ({
      label: `${variant.name} · ${variant.accelerator}`,
      value: variant.name
    }))
  )
  const resourceProfileOptions = computed(() =>
    (kubernetesOptions.value?.resource_profiles || []).map(profile => ({
      label: profile,
      value: profile
    }))
  )
  const categoryOptions = computed(() =>
    categories.value
      .filter(category => category.is_enabled !== false)
      .map(category => ({ label: category.name, value: category.id }))
  )

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
      const inputs = guidedDraft.value.inputs
        .map(item => ({ ...item, name: item.name.trim() }))
        .filter(item => item.name)
      const outputs = guidedDraft.value.outputs
        .map(item => ({ ...item, name: item.name.trim() }))
        .filter(item => item.name)
      if (!inputs.length || !outputs.length) {
        message.error('请至少填写一个输入和一个输出')
        return
      }
      if (new Set(inputs.map(item => item.name)).size !== inputs.length ||
          new Set(outputs.map(item => item.name)).size !== outputs.length) {
        message.error('输入或输出名称不能重复')
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
    kubernetesOptions.value = null
    kubernetesOptionsError.value = ''
    detailDrawerOpen.value = true
    detailLoading.value = true
    try {
      const response = await getToolPackage(item.id)
      selectedPackage.value = response.data
      packages.value = packages.value.map(current =>
        current.id === item.id ? response.data : current
      )
      if (response.data.status === 'published') {
        await loadKubernetesRegistrationOptions()
      }
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'Tool Package 详情加载失败')
    } finally {
      detailLoading.value = false
    }
  }

  async function loadKubernetesRegistrationOptions() {
    const packageId = selectedPackage.value?.id
    if (!packageId || selectedPackage.value?.status !== 'published') return

    kubernetesOptionsLoading.value = true
    kubernetesOptionsError.value = ''
    try {
      const response = await getKubernetesRegistrationOptions(packageId)
      kubernetesOptions.value = response.data
    } catch (cause) {
      kubernetesOptionsError.value = cause instanceof Error
        ? cause.message
        : '无法加载 K8s 注册选项'
    } finally {
      kubernetesOptionsLoading.value = false
    }
  }

  async function openKubernetesRegistration() {
    if (!kubernetesOptions.value) await loadKubernetesRegistrationOptions()
    const options = kubernetesOptions.value
    if (!options || !canRegisterKubernetesPackage(options)) {
      message.error('该 Package 未满足 K8s executor、镜像摘要或平台资源档位要求')
      return
    }

    if (categories.value.length === 0) {
      try {
        const response = await adminGetToolCategories()
        categories.value = response.data
      } catch (cause) {
        message.error(cause instanceof Error ? cause.message : '工具分类加载失败')
        return
      }
    }

    const firstVariant = getKubernetesRegistrationVariants(options)[0]
    registrationVariantName.value = firstVariant?.name || ''
    registrationResourceProfile.value = selectDefaultResourceProfile(
      firstVariant?.accelerator,
      options.resource_profiles
    )
    registrationToolVersion.value = createDefaultKubernetesToolVersion(
      options.package_version,
      firstVariant?.name || 'default'
    )
    registrationCategoryId.value = categoryOptions.value[0]?.value
    kubernetesRegistrationModalOpen.value = true
  }

  function handleRegistrationVariantChange(value: string) {
    registrationVariantName.value = value
    const variant = kubernetesOptions.value?.variants.find(item => item.name === value)
    registrationToolVersion.value = createDefaultKubernetesToolVersion(
      kubernetesOptions.value?.package_version || '1.0.0',
      value
    )
    registrationResourceProfile.value = selectDefaultResourceProfile(
      variant?.accelerator,
      kubernetesOptions.value?.resource_profiles || []
    )
  }

  function selectDefaultResourceProfile(
    accelerator: string | undefined,
    profiles: string[]
  ): string {
    const preferredPrefix = accelerator?.toLowerCase().includes('cpu') ? 'cpu-' : 'gpu-'
    return profiles.find(profile => profile.startsWith(preferredPrefix)) || profiles[0] || ''
  }

  async function handleRegisterKubernetesVersion() {
    const pkg = selectedPackage.value
    const options = kubernetesOptions.value
    if (!pkg || !options || !canSubmitKubernetesRegistration.value) return

    kubernetesRegistrationSaving.value = true
    try {
      const response = await registerKubernetesToolVersion(pkg.id, {
        package_version_id: options.package_version_id,
        target_tool_id: options.existing_tool?.id || null,
        category_id: options.existing_tool ? null : registrationCategoryId.value,
        tool_version: registrationToolVersion.value.trim(),
        variant_name: registrationVariantName.value,
        resource_profile: registrationResourceProfile.value
      })
      kubernetesRegistrationModalOpen.value = false
      message.success(`候选版本 ${response.data.version.version} 已注册，当前版本未切换`)
      await loadKubernetesRegistrationOptions()
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'K8s 候选版本注册失败')
    } finally {
      kubernetesRegistrationSaving.value = false
    }
  }

  function isCurrentVersion(versionId: string): boolean {
    return kubernetesOptions.value?.existing_tool?.current_version_id === versionId
  }

  function getSmokeStatusLabel(status: string | null, executorType: string | null): string {
    if (executorType !== 'k8s_job') return '不适用'
    if (!status) return '未执行'
    return {
      PENDING: '排队中',
      RUNNING: '运行中',
      SUCCESS: '通过',
      FAILURE: '失败',
      CANCELED: '已取消'
    }[status] || status
  }

  function getSmokeStatusColor(status: string | null, executorType: string | null): string {
    if (executorType !== 'k8s_job' || !status) return 'default'
    return {
      PENDING: 'processing',
      RUNNING: 'processing',
      SUCCESS: 'success',
      FAILURE: 'error',
      CANCELED: 'warning'
    }[status] || 'default'
  }

  function openSmokeModal(version: KubernetesToolVersionSummary) {
    selectedSmokeVersion.value = version
    smokeInputText.value = JSON.stringify({
      params: {},
      file_ids: [],
      input_bindings: {},
      standard_input_uploads: {}
    }, null, 2)
    smokeModalOpen.value = true
  }

  async function handleSubmitSmoke() {
    const toolId = kubernetesOptions.value?.existing_tool?.id
    const version = selectedSmokeVersion.value
    const input = parsedSmokeInput.value
    if (!toolId || !version || !input) {
      message.error('Smoke 输入必须是有效的 JSON 对象')
      return
    }

    smokeSubmitting.value = true
    smokeVersionId.value = version.id
    try {
      const response = await smokeToolVersion(toolId, version.id, input)
      smokeModalOpen.value = false
      message.success(`Smoke 任务已提交：${response.data.task_id}`)
      await loadKubernetesRegistrationOptions()
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : 'Smoke 任务提交失败')
    } finally {
      smokeSubmitting.value = false
      smokeVersionId.value = null
    }
  }

  async function handlePromoteToolVersion(version: KubernetesToolVersionSummary) {
    const toolId = kubernetesOptions.value?.existing_tool?.id
    if (!toolId) return

    promotionVersionId.value = version.id
    try {
      await promoteToolVersion(toolId, version.id)
      message.success(`版本 ${version.version} 已设为当前版本`)
      await loadKubernetesRegistrationOptions()
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '版本切换失败')
    } finally {
      promotionVersionId.value = null
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

  .artifact-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
</style>
