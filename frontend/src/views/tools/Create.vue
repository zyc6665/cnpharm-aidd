<template>
  <div class="tool-create-page">
    <div class="container">
      <AppPageHeader :title="isEdit ? t('tools.editTool') : t('tools.createTool')">
        <template #actions>
        <a-button @click="showGuide = true">
          模型接入教程
        </a-button>
        <a-button @click="goBack">
          <ArrowLeftOutlined />
          {{ t('common.back') }}
        </a-button>
        </template>
      </AppPageHeader>

      <a-drawer v-model:open="showGuide" title="模型接入教程" :width="560">
        <a-typography>
          <a-typography-title :level="5">1. 构建镜像</a-typography-title>
          <p>基于与集群匹配的 CUDA 基座；权重外置，通过 runtime.weights.mounts 只读挂载；入口读 <code>DRP_TASK_FILE</code>，写 <code>DRP_RESULT_FILE</code> 与 <code>/work/out</code>。</p>
          <a-typography-title :level="5">2. 编写 Tool Package v2</a-typography-title>
          <p>输入/输出用平台标准 Artifact 类型（如 protein_structure@1 / binding_pocket@1 / molecule_table@1 / ligand_structure@1 / run_report@1），参数用 parameters_schema。</p>
          <a-typography-title :level="5">3. 发布与冒烟</a-typography-title>
          <p>执行方式固定 k8s_job；填镜像 digest 与资源画像，校验 → 冒烟（K8s Job Succeeded、result.json 合法）→ 发布。已发布版本不可就地改，走“基于当前版本新建版本”。</p>
          <a-typography-title :level="5">4. 完整教程</a-typography-title>
          <p>见 <code>docs/28-模型接入教程（镜像构建与ToolPackage v2）.md</code></p>
        </a-typography>
      </a-drawer>

      <SkeletonDetail v-if="loading" />
        <a-card v-else class="form-card">
          <a-steps :current="activeStep - 1" size="small" class="tool-editor-steps">
            <a-step v-for="(label, index) in wizardSteps" :key="index" :title="label" />
          </a-steps>

          <a-form
            ref="formRef"
            class="tool-form"
            :model="formState"
            :rules="formRules"
            layout="vertical"
            @finish="handleSubmit"
          >
            <div v-show="activeStep === 1">
            <template v-if="showTemplateQuickStart">
              <a-divider orientation="left">药物研发工具模板</a-divider>

              <div class="drug-template-panel">
                <a-alert
                  type="info"
                  show-icon
                  message="从标准模板创建工具草稿"
                  description="模板会固定药物研发能力、标准输入输出、resource_profile 和 smoke test；Docker、Python、SSH、Kubernetes 等部署参数仍按下方执行器配置填写。"
                />
                <a-row :gutter="16" class="drug-template-row">
                  <a-col :span="14">
                    <a-form-item label="药物研发工具模板">
                      <a-select
                        v-model:value="selectedToolTemplateKey"
                        placeholder="选择 ADMET、构象生成、Vina、MD 等模板"
                        allow-clear
                        @change="handleToolTemplateChange"
                      >
                        <a-select-option
                          v-for="template in toolTemplates"
                          :key="template.template_key"
                          :value="template.template_key"
                        >
                          {{ template.name }} · {{ template.capability }}
                        </a-select-option>
                      </a-select>
                    </a-form-item>
                  </a-col>
                  <a-col :span="10">
                    <a-form-item label="资源画像">
                      <div class="drug-template-resource">
                        {{ selectedToolTemplateResourceText || '选择模板后显示资源需求' }}
                      </div>
                    </a-form-item>
                  </a-col>
                </a-row>
                <div v-if="selectedToolTemplate" class="drug-template-implementation">
                  <strong>推荐实现：{{ selectedToolTemplate.implementation.provider }}</strong>
                  <span>
                    {{ selectedToolTemplate.implementation.runtime }}
                    · 推荐执行器 {{ selectedToolTemplate.implementation.recommended_executor }}
                  </span>
                  <a
                    v-if="selectedToolTemplate.implementation.project_url"
                    :href="selectedToolTemplate.implementation.project_url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    查看项目
                  </a>
                  <span v-if="selectedToolTemplate.implementation.notes">
                    {{ selectedToolTemplate.implementation.notes }}
                  </span>
                </div>
                <a-space>
                  <a-button
                    type="primary"
                    html-type="button"
                    :disabled="!selectedToolTemplateKey"
                    :loading="creatingTemplateDraft"
                    @click="handleCreateTemplateDraft"
                  >
                    <PlusOutlined />
                    从模板创建草稿
                  </a-button>
                  <span class="form-extra">
                    创建草稿会直接复用下方当前执行器配置，不会发布工具。
                  </span>
                </a-space>
              </div>
            </template>

            <!-- 基本信息 -->
            <a-divider orientation="left">{{ t('tools.basicInfo') }}</a-divider>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.toolName')" name="name">
                  <a-input
                    v-model:value="formState.name"
                    :placeholder="t('tools.toolNamePlaceholder')"
                    :max-length="100"
                    show-count
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.toolSlug')" name="slug">
                  <a-input
                    v-model:value="formState.slug"
                    :placeholder="t('tools.toolSlugPlaceholder')"
                    :max-length="50"
                    show-count
                  />
                  <template #extra>
                    <span class="form-extra">{{ t('tools.slugHint') }}</span>
                  </template>
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('common.description')" name="description">
              <a-textarea
                v-model:value="formState.description"
                :placeholder="t('tools.descriptionPlaceholder')"
                :rows="4"
                :max-length="500"
                show-count
              />
            </a-form-item>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.category')" name="category_id">
                  <a-select
                    v-model:value="formState.category_id"
                    :placeholder="t('tools.selectCategory')"
                    allow-clear
                  >
                    <a-select-option v-for="cat in categories" :key="cat.id" :value="cat.id">
                      {{ cat.name }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.tags')" name="tag_ids">
                  <a-select
                    v-model:value="formState.tag_ids"
                    :placeholder="t('tools.selectTags')"
                    mode="multiple"
                    allow-clear
                  >
                    <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.id">
                      <a-tag :color="tag.color" size="small">{{ tag.name }}</a-tag>
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.icon')" name="icon">
                  <a-input
                    v-model:value="formState.icon"
                    :placeholder="t('tools.iconPlaceholder')"
                  />
                  <template #extra>
                    <span class="form-extra">{{ t('tools.iconHint') }}</span>
                  </template>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item :label="t('tools.iconUrl')" name="icon_url">
                  <a-input
                    v-model:value="formState.icon_url"
                    :placeholder="t('tools.iconUrlPlaceholder')"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            </div>
            <div v-show="activeStep === 2">
            <!-- 运行配置 -->
            <a-divider orientation="left">{{ t('tools.runConfig') }}</a-divider>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('tools.timeoutSec')" name="timeout_sec">
                  <a-input-number
                    v-model:value="formState.timeout_sec"
                    :min="60"
                    :max="86400"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('tools.isPublic')" name="is_public">
              <a-switch v-model:checked="formState.is_public" />
              <span class="switch-label">
                {{ formState.is_public ? t('tools.publicYes') : t('tools.publicNo') }}
              </span>
            </a-form-item>

            </div>
            <div v-show="activeStep === 5">
            <!-- 版本信息 -->
            <a-divider orientation="left">版本信息</a-divider>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item label="版本号" name="version">
                  <a-input
                    v-model:value="formState.version"
                    placeholder="例如：1.0.0"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="16">
                <a-form-item label="版本说明" name="notes">
                  <a-input
                    v-model:value="formState.notes"
                    placeholder="简要说明此版本的特点"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="更新日志" name="changelog">
              <a-textarea
                v-model:value="formState.changelog"
                placeholder="详细描述此版本的更新内容"
                :rows="3"
              />
            </a-form-item>

            <a-divider orientation="left">发布前校验</a-divider>
            <a-alert
              type="info"
              show-icon
              message="一键校验模型的发布条件"
              description="检查必填信息、镜像 digest 格式、资源档位、输入/输出契约与 Tool Package manifest（若存在）。校验通过后仍可保存，平台会在提交时再次校验。"
              style="margin-bottom: 12px"
            />
            <a-space direction="vertical" style="width: 100%">
              <a-button data-testid="tool-validate-button" :loading="validationRunning" @click="runValidation">
                {{ validationRunning ? '校验中…' : '一键校验' }}
              </a-button>
              <div v-if="validationChecks.length" class="validation-list" data-testid="tool-validation-results">
                <div
                  v-for="check in validationChecks"
                  :key="check.key"
                  class="validation-item"
                  :class="check.ok ? 'is-ok' : 'is-fail'"
                >
                  <span class="validation-mark">{{ check.ok ? '✓' : '✗' }}</span>
                  <span class="validation-label">{{ check.label }}</span>
                  <span v-if="check.detail" class="validation-detail">{{ check.detail }}</span>
                </div>
              </div>
            </a-space>

            </div>
            <div v-show="activeStep === 2">
            <!-- 执行方式（固定 k8s_job） -->
            <a-divider orientation="left">执行方式</a-divider>
            <a-alert
              class="tool-package-primary-path"
              type="info"
              show-icon
              message="执行方式：Kubernetes Job（k8s_job）"
              description="平台统一以 k8s_job 调度（GPU 通过 nvidia.com/gpu 申请）；主路径为 Tool Package v2，输入/输出使用平台标准 Artifact 输入/输出槽。"
            />

            <!-- Kubernetes Job 配置 -->
            <template v-if="formState.tool_type === 'k8s_job'">
              <a-divider orientation="left">Kubernetes Job 配置</a-divider>
              <a-alert
                type="info"
                show-icon
                message="受控集群执行"
                description="镜像和资源档位由工具版本声明；集群、Namespace、ServiceAccount 与凭据由平台执行环境统一管理。"
                class="executor-managed-alert"
              />
              <a-row :gutter="24">
                <a-col :span="16">
                  <a-form-item
                    label="镜像 digest"
                    name="k8s_image"
                    :rules="[{ required: true, message: '请输入不可变镜像引用' }, { pattern: /@sha256:[a-fA-F0-9]{64}$/, message: '镜像必须使用完整 SHA-256 digest' }]"
                  >
                    <a-input
                      v-model:value="formState.k8s_image"
                      placeholder="registry.example/model@sha256:64 位 digest"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item
                    label="资源档位"
                    name="k8s_resource_profile"
                    :rules="[{ required: true, message: '请输入资源档位' }]"
                  >
                    <a-input v-model:value="formState.k8s_resource_profile" placeholder="cpu-small / gpu-large" />
                  </a-form-item>
                </a-col>
              </a-row>
            </template>

            </div>
            <div v-show="activeStep === 3">
              <a-divider orientation="left">输入 / 输出契约</a-divider>
              <template v-if="hasContractManifest">
                <a-alert
                  type="info"
                  show-icon
                  message="来自 Tool Package v2 的 Artifact 契约"
                  description="在这里增删输入/输出槽，保存时会写回该版本的 manifest.artifacts。"
                  style="margin-bottom: 12px"
                />
                <div class="contract-block">
                  <div class="contract-block-title">输入（inputs）</div>
                  <div v-for="(item, index) in contractInputs" :key="'in' + index" class="contract-row">
                    <a-input v-model:value="item.name" placeholder="槽名称，如 receptor" style="width: 200px" />
                    <a-select v-model:value="item.type" style="width: 200px">
                      <a-select-option v-for="t in ARTIFACT_TYPES" :key="t" :value="t">{{ t }}</a-select-option>
                    </a-select>
                    <a-checkbox v-model:checked="item.required">必填</a-checkbox>
                    <a-button type="text" danger @click="contractInputs.splice(index, 1)">删除</a-button>
                  </div>
                  <a-button type="dashed" block @click="addContractInput">+ 添加输入槽</a-button>
                </div>
                <div class="contract-block" style="margin-top: 16px">
                  <div class="contract-block-title">输出（outputs）</div>
                  <div v-for="(item, index) in contractOutputs" :key="'out' + index" class="contract-row">
                    <a-input v-model:value="item.name" placeholder="槽名称，如 ligands" style="width: 180px" />
                    <a-select v-model:value="item.type" style="width: 180px">
                      <a-select-option v-for="t in ARTIFACT_TYPES" :key="t" :value="t">{{ t }}</a-select-option>
                    </a-select>
                    <a-select v-model:value="item.cardinality" style="width: 110px">
                      <a-select-option value="one">单值</a-select-option>
                      <a-select-option value="many">多值</a-select-option>
                    </a-select>
                    <a-checkbox v-model:checked="item.required">必填</a-checkbox>
                    <a-button type="text" danger @click="contractOutputs.splice(index, 1)">删除</a-button>
                  </div>
                  <a-button type="dashed" block @click="addContractOutput">+ 添加输出槽</a-button>
                </div>
              </template>
              <a-alert
                v-else
                type="warning"
                show-icon
                message="当前没有可编辑的 Tool Package 契约"
                description="手工注册工具的输入/输出契约由 Tool Package v2 manifest 声明；从「工具包」导入（带 package_id）或编辑已关联 manifest 的版本后，可在此增删 Artifact 槽。"
              />
            </div>
            <div v-show="activeStep === 4">
            <!-- 参数定义 -->
            <a-divider orientation="left">科学运行参数</a-divider>

            <a-form-item v-if="registrationMode !== 'package'" name="input_schema">
              <ToolParameterSchemaEditor
                v-model:model-value="inputParameterSchema"
                :allow-file-fields="true"
                @validity-change="setInputSchemaEditorValidity"
              />
            </a-form-item>
            <a-alert
              v-else
              type="info"
              show-icon
              message="运行参数来自 Tool Package v2"
              description="请在 Tool Package 管理中维护模型参数；平台资源和标准 Artifact 输入在独立契约中配置。"
            />

            <a-form-item v-if="registrationMode !== 'package'" label="输出参数 Schema" name="output_schema">
              <a-textarea
                v-model:value="formState.output_schema"
                placeholder='{"type": "object", "properties": {"result": {"type": "string"}}}'
                :rows="5"
              />
              <template #extra>
                <span class="form-extra">JSON Schema格式，定义工具的输出结果结构</span>
              </template>
            </a-form-item>

            <a-form-item :label="t('tools.documentationMarkdown')" name="documentation_markdown">
              <a-textarea
                v-model:value="formState.documentation_markdown"
                class="tool-documentation-editor"
                placeholder="## 模型介绍&#10;&#10;## 参数说明&#10;&#10;## 输出文件"
                :rows="10"
              />
              <template #extra>
                <span class="form-extra">{{ t('tools.documentationMarkdownHint') }}</span>
              </template>
            </a-form-item>

            </div>
            <a-form-item class="wizard-nav">
              <a-space size="middle">
                <a-button v-if="activeStep > 1" @click="activeStep -= 1">上一步</a-button>
                <a-button v-if="activeStep < 5" type="primary" @click="nextStep">下一步</a-button>
              </a-space>
            </a-form-item>
            <!-- 提交按钮 -->
            <a-form-item class="form-actions">
              <a-space size="middle">
                <a-button size="large" @click="goBack">
                  {{ t('common.cancel') }}
                </a-button>
                <a-button type="primary" size="large" html-type="submit" :loading="submitting">
                  <SaveOutlined />
                  {{ isEdit ? t('common.save') : t('common.create') }}
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import {
    ArrowLeftOutlined,
    DeleteOutlined,
    PlusOutlined,
    SaveOutlined
  } from '@ant-design/icons-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import ToolParameterSchemaEditor from '@/components/tools/ToolParameterSchemaEditor.vue'
  import StructuredKeyValueEditor from '@/components/tools/StructuredKeyValueEditor.vue'
  import StructuredStringListEditor from '@/components/tools/StructuredStringListEditor.vue'
  import { useToolCreateEditorState } from '@/composables/useToolCreateEditorState'
  import {
    buildToolAgentCapabilityEnablePatch,
    buildToolEditFormPatch,
    buildToolTemplateFormPatch,
    buildToolTemplateDraftPayload,
    createAgentCapabilityInputForm,
    createAgentCapabilityOutputForm,
    createToolCreateFormState,
    createToolCreateSubmission,
    formatToolTemplateResourceText,
    formatToolCreateSubmissionErrorMessage,
    buildToolVersionCreatePayload,
    resolveToolCreateSubmissionBlocker,
    createEmptyParameterSchema,
    validateParameterSchema,
    type ToolConfigFormPatch,
    type ToolCreateFormState
  } from '@/domain/tools'
  import type { ToolSchema } from '@/types/models'
  import type { ToolPackage } from '@/types/tool-packages'
  import { useToolsStore } from '@/stores'
  import { getToolPackage, validateToolPackage } from '@/api/tool-packages'
  import {
    createTool,
    createToolDraftFromTemplate,
    createToolVersion,
    getToolDetail,
    listToolTemplates,
    type ToolTemplateSummary,
    updateTool
  } from '@/api/tools'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const submitting = ref(false)
  const showGuide = ref(false)
  const activeStep = ref(1)
  const wizardSteps = ['基本信息', '镜像与运行', '输入/输出契约', '运行参数', '版本与发布']
  interface ValidationCheck { key: string; label: string; ok: boolean; detail?: string }
  const validationRunning = ref(false)
  const validationChecks = ref<ValidationCheck[]>([])

  function pushCheck(key: string, label: string, ok: boolean, detail?: string) {
    validationChecks.value.push({ key, label, ok, detail })
  }

  async function runValidation() {
    validationRunning.value = true
    validationChecks.value = []
    try {
      pushCheck('name', '模型名称', Boolean(formState.name && String(formState.name).trim()), '必填')
      pushCheck('slug', '模型标识（slug）', /^[a-z0-9][a-z0-9-]*$/.test(String(formState.slug || '')), '小写字母、数字与连字符')
      pushCheck('description', '模型简介', Boolean(formState.description && String(formState.description).trim()), '必填')
      pushCheck(
        'image',
        '镜像 digest',
        /@sha256:[a-fA-F0-9]{64}$/.test(String(formState.k8s_image || '')),
        '需为 registry/image@sha256:<64 位>'
      )
      pushCheck('resource', '资源档位', Boolean(formState.k8s_resource_profile), '必填')
      pushCheck('version', '版本号', /^\d+\.\d+\.\d+/.test(String(formState.version || '')), '建议语义化版本，如 1.0.0')

      if (hasContractManifest.value) {
        const inNames = contractInputs.value.map(i => String(i.name || '').trim())
        const outNames = contractOutputs.value.map(o => String(o.name || '').trim())
        const missing = [...inNames, ...outNames].some(n => !n)
        const dupIn = new Set(inNames).size !== inNames.length
        const dupOut = new Set(outNames).size !== outNames.length
        pushCheck('contract', '输入/输出契约', !missing && !dupIn && !dupOut,
          missing ? '存在空槽名称' : dupIn || dupOut ? '存在重复槽名称' : `${inNames.length} 个输入 / ${outNames.length} 个输出`)
      } else {
        pushCheck('contract', '输入/输出契约', true, '无 Tool Package manifest，跳过（提交时由后端校验）')
      }

      if (registrationMode.value !== 'package') {
        const schemaErrors = validateParameterSchema(inputParameterSchema.value)
        pushCheck('params', '运行参数 Schema', inputSchemaEditorValid.value && schemaErrors.length === 0,
          schemaErrors[0] || '参数 Schema 合法')
      }

      if (packageManifest.value) {
        try {
          const response = await validateToolPackage(packageManifest.value as Record<string, unknown>)
          const result = response.data
          pushCheck('manifest', 'Tool Package manifest 校验', result.isValid, result.errors.join('；') || '通过')
        } catch (error) {
          pushCheck('manifest', 'Tool Package manifest 校验', false, '调用校验接口失败，请确认后端已更新')
        }
      }
      syncContractToManifest()
    } finally {
      validationRunning.value = false
    }
  }
  const toolTemplates = ref<ToolTemplateSummary[]>([])
  const selectedToolTemplateKey = ref<string>()
  const creatingTemplateDraft = ref(false)
  const originalVersion = ref('')
  const originalChangelog = ref('')
  const originalNotes = ref('')
  const originalConfigSnapshot = ref('')
  const packageManifest = ref<Record<string, unknown> | null>(null)
  const ARTIFACT_TYPES = ['protein_structure', 'binding_pocket', 'molecule_table', 'ligand_structure', 'complex_structure', 'peptide_sequence', 'admet_table', 'affinity_table', 'md_trajectory', 'confidence_report', 'molecule_set', 'run_report']
  const contractInputs = ref<Array<Record<string, any>>>([])
  const contractOutputs = ref<Array<Record<string, any>>>([])
  const hasContractManifest = computed(() => Boolean((packageManifest.value as any)?.artifacts))
  function syncContractFromManifest() {
    const artifacts = (packageManifest.value as any)?.artifacts
    contractInputs.value = Array.isArray(artifacts?.inputs)
      ? artifacts.inputs.map((x: any) => ({ name: x?.name ?? '', type: x?.type ?? 'protein_structure', required: x?.required !== false }))
      : []
    contractOutputs.value = Array.isArray(artifacts?.outputs)
      ? artifacts.outputs.map((x: any) => ({ name: x?.name ?? '', type: x?.type ?? 'run_report', cardinality: x?.cardinality === 'many' ? 'many' : 'one', required: x?.required !== false }))
      : []
  }
  function syncContractToManifest() {
    if (!packageManifest.value) return
    const manifest = packageManifest.value as any
    const base = manifest.artifacts && typeof manifest.artifacts === 'object' ? manifest.artifacts : {}
    manifest.artifacts = {
      ...base,
      inputs: contractInputs.value.map(i => ({ ...i, name: String(i.name || '').trim(), type: i.type, required: i.required !== false })),
      outputs: contractOutputs.value.map(o => ({ ...o, name: String(o.name || '').trim(), type: o.type, cardinality: o.cardinality === 'many' ? 'many' : 'one', required: o.required !== false }))
    }
  }
  function addContractInput() { contractInputs.value.push({ name: '', type: 'protein_structure', required: true }) }
  function addContractOutput() { contractOutputs.value.push({ name: '', type: 'run_report', cardinality: 'one', required: true }) }
  watch([contractInputs, contractOutputs], syncContractToManifest, { deep: true })
  const packageLoading = ref(false)

  // 判断是编辑还是创建
  const isEdit = computed(() => route.name === 'AdminToolEdit' || route.name === 'ToolEdit')
  const toolId = computed(() => route.params.id as string)
  const registrationMode = computed(() => {
    const mode = route.query.mode
    return mode === 'template' || mode === 'package' ? mode : 'template'
  })
  const showTemplateQuickStart = computed(
    () => !isEdit.value && registrationMode.value !== 'package'
  )

  // 表单状态
  const formState = reactive<ToolCreateFormState>(createToolCreateFormState())
  const inputParameterSchema = computed<ToolSchema>({
    get() {
      try {
        const parsed: unknown = JSON.parse(formState.input_schema)
        if (
          parsed &&
          typeof parsed === 'object' &&
          !Array.isArray(parsed) &&
          (parsed as Record<string, unknown>).type === 'object'
        ) {
          const record = parsed as Record<string, unknown>
          return {
            ...record,
            properties: record.properties && typeof record.properties === 'object' && !Array.isArray(record.properties)
              ? record.properties
              : {},
          } as ToolSchema
        }
      } catch {
        return createEmptyParameterSchema()
      }
      return createEmptyParameterSchema()
    },
    set(schema) {
      formState.input_schema = JSON.stringify(schema, null, 2)
    },
  })
  const inputSchemaEditorValid = ref(true)

  const {
    dockerCommandItems,
    dockerEnvEntries,
    pythonArgumentItems,
    sshEnvEntries,
    sshOutputGlobItems,
    snapshot: editorStateSnapshot,
    applyPatch: applyEditorPatch,
  } = useToolCreateEditorState()
  const agentDefaultsText = ref('{}')

  const selectedToolTemplate = computed(() =>
    toolTemplates.value.find(template => template.template_key === selectedToolTemplateKey.value)
  )

  const selectedToolTemplateResourceText = computed(() => {
    return formatToolTemplateResourceText(selectedToolTemplate.value?.resource_profile)
  })

  const addAgentInput = () => {
    formState.agent_inputs.push(createAgentCapabilityInputForm())
  }

  const removeAgentInput = (index: number) => {
    formState.agent_inputs.splice(index, 1)
  }

  const addAgentOutput = () => {
    formState.agent_outputs.push(createAgentCapabilityOutputForm())
  }

  const removeAgentOutput = (index: number) => {
    formState.agent_outputs.splice(index, 1)
  }

  const loadToolTemplates = async () => {
    if (isEdit.value) {
      return
    }
    try {
      const response = await listToolTemplates()
      toolTemplates.value = response.data
    } catch {
      toolTemplates.value = []
    }
  }

  const handleToolTemplateChange = () => {
    const template = selectedToolTemplate.value
    if (!template) {
      return
    }

    const patch = buildToolTemplateFormPatch({
      currentToolType: formState.tool_type,
      template,
    })
    Object.assign(formState, patch.form)
    agentDefaultsText.value = patch.agentDefaultsText
  }

  const handleCreateTemplateDraft = async () => {
    if (!selectedToolTemplateKey.value) {
      message.error('请选择药物研发工具模板')
      return
    }
    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    creatingTemplateDraft.value = true
    try {
      const draftResponse = await createToolDraftFromTemplate(
        selectedToolTemplateKey.value,
        buildToolTemplateDraftPayload(formState, editorStateSnapshot())
      )
      message.success('工具模板草稿创建成功')
      const createdToolId = draftResponse.data.tool.id
      router.push(`/tools/${createdToolId}`)
    } catch {
      // 错误已在请求层处理
    } finally {
      creatingTemplateDraft.value = false
    }
  }

  const handleAgentCapabilityToggle = (checked: boolean | string | number) => {
    if (!checked) {
      return
    }

    Object.assign(formState, buildToolAgentCapabilityEnablePatch(formState))
  }

  const applyToolFormPatch = (patch: ToolConfigFormPatch) => {
    Object.assign(formState, patch.form)
    applyEditorPatch(patch.editor)
    agentDefaultsText.value = patch.agentDefaultsText
  }

  // 表单验证规则
  const formRules: Record<string, Rule[]> = {
    name: [
      { required: true, message: t('tools.nameRequired'), trigger: 'blur' },
      { min: 2, max: 100, message: t('tools.nameLength'), trigger: 'blur' }
    ],
    slug: [
      { required: true, message: t('tools.slugRequired'), trigger: 'blur' },
      { pattern: /^[a-z0-9-]+$/, message: t('tools.slugFormat'), trigger: 'blur' },
      { min: 2, max: 50, message: t('tools.slugLength'), trigger: 'blur' }
    ],
    description: [
      { max: 500, message: t('tools.descriptionLength'), trigger: 'blur' }
    ],
    version: [
      { required: true, message: '请输入版本号', trigger: 'blur' }
    ]
  }

  // 分步校验：进入下一步前先校验当前步骤的关键字段
  const stepFields: Record<number, string[]> = {
    1: ['name', 'slug', 'description'],
    2: ['k8s_image', 'k8s_resource_profile'],
    4: [],
    5: ['version']
  }

  const nextStep = async () => {
    const fields = stepFields[activeStep.value] ?? []
    if (fields.length && formRef.value) {
      try {
        await formRef.value.validateFields(fields)
      } catch {
        return
      }
    }
    if (activeStep.value < wizardSteps.length) {
      activeStep.value += 1
    }
  }

  function setInputSchemaEditorValidity(valid: boolean) {
    inputSchemaEditorValid.value = valid
  }

  const applyRegistrationMode = () => {
    if (isEdit.value) {
      return
    }
    if (registrationMode.value === 'package') {
      formState.tool_type = 'ssh_job'
    }
  }

  const loadToolPackage = async () => {
    if (isEdit.value || registrationMode.value !== 'package') return
    const packageId = String(route.query.package_id || '')
    if (!packageId) return
    packageLoading.value = true
    try {
      const response = await getToolPackage(packageId)
      const pkg = response.data as ToolPackage
      const version = pkg.current_version
      if (!version?.manifest) {
        message.error('Tool Package 当前没有可用 manifest')
        return
      }
      packageManifest.value = version.manifest
      syncContractFromManifest()
      formState.name = pkg.name
      formState.slug = pkg.slug
      formState.description = pkg.description || ''
      formState.version = version.version
      formState.notes = '由 Tool Package v2 导入'
      const variants = Array.isArray(version.manifest.variants)
        ? version.manifest.variants.filter(item => item && typeof item === 'object') as Array<Record<string, unknown>>
        : []
      const variant = variants[0]
      if (variant) {
        const entrypoint = Array.isArray(variant.entrypoint)
          ? variant.entrypoint.map(item => String(item)).join(' ')
          : ''
        if (entrypoint) {
          formState.ssh_entrypoint = entrypoint
        }
        const resources = variant.resources && typeof variant.resources === 'object'
          ? variant.resources as Record<string, unknown>
          : {}
        const gpuMemory = Number(resources.gpu_memory_mb)
        if (Number.isFinite(gpuMemory) && gpuMemory > 0) {
          formState.gpu_required = true
          formState.gpu_memory_mb = gpuMemory
        }
      }
    } catch {
      message.error('Tool Package 加载失败')
    } finally {
      packageLoading.value = false
    }
  }

  // 分类和标签
  const categories = computed(() => toolsStore.categories)
  const tags = computed(() => toolsStore.tags)

  // 加载工具详情（编辑模式）
  const loadToolDetail = async () => {
    if (!isEdit.value || !toolId.value) return

    loading.value = true
    try {
      const res = await getToolDetail(toolId.value)
      const tool = res.data
      const patch = buildToolEditFormPatch(tool)

      applyToolFormPatch(patch)
      originalVersion.value = patch.originalVersion
      originalChangelog.value = patch.originalChangelog
      originalNotes.value = patch.originalNotes
      originalConfigSnapshot.value = patch.originalConfigSnapshot
    } catch {
      message.error(t('tools.loadFailed'))
      router.push('/tools')
    } finally {
      loading.value = false
    }
  }

  // 提交表单
  const handleSubmit = async () => {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    if (registrationMode.value !== 'package') {
      const schemaErrors = validateParameterSchema(inputParameterSchema.value)
      if (!inputSchemaEditorValid.value || schemaErrors.length > 0) {
        message.error(schemaErrors[0] || '请先修正运行参数 Schema')
        return
      }
    }

    submitting.value = true
    try {
      syncContractToManifest()
      let submission: ReturnType<typeof createToolCreateSubmission>
      try {
        submission = createToolCreateSubmission({
          formState,
          editorState: editorStateSnapshot(),
          agentDefaultsText: agentDefaultsText.value,
          isEdit: isEdit.value,
          originalVersion: originalVersion.value,
          originalChangelog: originalChangelog.value,
          originalNotes: originalNotes.value,
          originalConfigSnapshot: originalConfigSnapshot.value,
          toolPackageManifest: packageManifest.value || undefined
        })
      } catch (error) {
        message.error(formatToolCreateSubmissionErrorMessage(error))
        return
      }

      const blocker = resolveToolCreateSubmissionBlocker({
        submission,
        version: formState.version,
        originalVersion: originalVersion.value,
      })
      if (blocker) {
        message.error(blocker)
        return
      }

      if (isEdit.value) {
        await updateTool(toolId.value, submission.data)
        if (submission.versionConfigChanged) {
          await createToolVersion(
            toolId.value,
            buildToolVersionCreatePayload(formState, submission.config)
          )
        }
        message.success(submission.versionConfigChanged ? '工具与版本更新成功' : t('tools.updateSuccess'))
      } else {
        const res = await createTool(submission.data)
        message.success(t('tools.createSuccess'))
        // 跳转到工具详情页
        router.push(`/tools/${res.data.id}`)
        return
      }

      router.push('/admin/tools')
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
  }

  const goBack = () => {
    router.back()
  }

  onMounted(async () => {
    applyRegistrationMode()
    // 加载分类和标签
    await Promise.all([
      toolsStore.fetchCategories(),
      toolsStore.fetchTags(),
      loadToolTemplates()
    ])

    // 编辑模式加载工具详情
    if (isEdit.value) {
      await loadToolDetail()
    } else {
      await loadToolPackage()
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-create-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .form-card {
    max-width: 900px;
    margin: 0 auto;
  }

  .form-extra {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

  .tool-package-primary-path {
    margin-bottom: @spacing-lg;
  }

  .drug-template-panel {
    display: grid;
    gap: @spacing-md;
    margin-bottom: @spacing-lg;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-color-light;
  }

  .drug-template-row {
    margin-top: @spacing-xs;
  }

  .drug-template-resource {
    min-height: 32px;
    padding: 5px 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .drug-template-implementation {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-xs @spacing-sm;
    padding: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-surface;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .drug-template-implementation strong {
    color: @text-color-light-primary;
  }

  .drug-template-implementation a {
    color: @primary-color;
  }

  .switch-label {
    margin-left: @spacing-sm;
    color: @text-color-light-secondary;
  }

  .agent-capability-block {
    margin-bottom: @spacing-lg;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
    background: @bg-color-light;
  }

  .agent-capability-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-sm;
    color: @text-color-light-primary;
    font-weight: @font-weight-medium;
  }

  .agent-capability-row + .agent-capability-row {
    margin-top: @spacing-sm;
  }

  .form-actions {
    margin-top: @spacing-xl;
    padding-top: @spacing-lg;
    border-top: 1px solid @border-color-light;
    text-align: center;
  }

  :deep(.ant-divider-inner-text) {
    font-weight: @font-weight-semibold;
    color: @text-color-light-primary;
  }

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
    }
  }

  @media (max-width: @screen-md) {
    :deep(.tool-form .ant-col-8),
    :deep(.tool-form .ant-col-12),
    :deep(.tool-form .ant-col-16) {
      flex: 0 0 100%;
      max-width: 100%;
    }
  }

  .contract-block {
    border: 1px solid @border-color;
    border-radius: 8px;
    padding: 12px;
  }

  .contract-block-title {
    font-size: @font-size-xs;
    color: @text-secondary;
    margin-bottom: 8px;
  }

  .contract-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  .validation-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .validation-item {
    display: flex;
    gap: 8px;
    align-items: baseline;
    font-size: @font-size-sm;

    &.is-ok .validation-mark {
      color: @success-color;
    }

    &.is-fail .validation-mark {
      color: @error-color;
    }
  }

  .validation-mark {
    font-weight: 600;
  }

  .validation-label {
    color: @text-primary;
    min-width: 160px;
  }

  .validation-detail {
    color: @text-secondary;
  }
</style>
