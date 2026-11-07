<template>
  <div class="model-editor">
    <div class="model-editor__topbar">
      <div>
        <button class="model-editor__back" @click="goBack">
          <ArrowLeftOutlined />
          返回模型工具
        </button>
        <h1 class="model-editor__title">
          {{ isEdit ? '编辑模型' : '新增模型' }}
          <span v-if="formState.name">· {{ formState.name }}</span>
        </h1>
        <p class="model-editor__subtitle">
          按 k8s_job 统一调度；输入/输出遵循平台标准 Artifact 契约
        </p>
      </div>
      <a-space>
        <a-button @click="goGuide">
          <ReadOutlined />
          模型接入教程
        </a-button>
        <a-button @click="goBack">返回</a-button>
      </a-space>
    </div>

    <div v-if="loading" class="model-editor__loading">
      <SkeletonDetail />
    </div>

    <div v-else class="model-editor__layout">
      <aside class="model-editor__steps">
        <button
          v-for="step in wizardSteps"
          :key="step.key"
          class="model-step"
          :class="{
            'is-active': activeStep === step.key,
            'is-done': activeStep > step.key,
          }"
          @click="activeStep = step.key"
        >
          <span class="model-step__index">
            <CheckOutlined v-if="activeStep > step.key" />
            <span v-else>{{ step.key }}</span>
          </span>
          <span class="model-step__copy">
            <strong>{{ step.title }}</strong>
            <small>{{ step.hint }}</small>
          </span>
        </button>

        <div class="model-step-help">
          <InfoCircleOutlined />
          <p>旧版 Docker / Python / SSH 工具类型与 Agent 语义映射已下线，新模型统一走 Tool Package v2 + k8s_job。</p>
        </div>
      </aside>

      <main class="model-editor__main">
        <a-form
          ref="formRef"
          :model="formState"
          :rules="formRules"
          layout="vertical"
          @finish="handleSubmit"
        >
          <section v-show="activeStep === 1" class="editor-card">
            <header class="editor-card__head">
              <div>
                <h2>基本信息</h2>
                <p>这些信息会展示在工具广场与任务选择器中。</p>
              </div>
              <a-tag color="blue">步骤 1 / 5</a-tag>
            </header>

            <a-row :gutter="[20, 0]">
              <a-col :xs="24" :md="12">
                <a-form-item label="模型名称" name="name">
                  <a-input
                    v-model:value="formState.name"
                    placeholder="例如：Pocket2Mol 分子生成"
                    :max-length="100"
                    show-count
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item label="模型标识（slug）" name="slug">
                  <a-input
                    v-model:value="formState.slug"
                    placeholder="pocket2mol-pocket-ligand-generation"
                    :max-length="50"
                    :disabled="isEdit"
                  />
                  <template #extra>
                    <span class="form-extra">发布后不可修改；小写字母、数字与连字符。</span>
                  </template>
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="模型描述" name="description">
              <a-textarea
                v-model:value="formState.description"
                placeholder="用一句话说明模型解决什么问题、适合什么场景"
                :rows="3"
                :max-length="500"
                show-count
              />
            </a-form-item>

            <a-row :gutter="[20, 0]">
              <a-col :xs="24" :md="12">
                <a-form-item label="模型能力族">
                  <a-select
                    v-model:value="formState.category_id"
                    placeholder="选择能力族"
                    allow-clear
                  >
                    <a-select-option
                      v-for="category in categories"
                      :key="category.id"
                      :value="category.id"
                    >
                      {{ category.name }}
                    </a-select-option>
                  </a-select>
                  <template #extra>
                    <span class="form-extra">能力族决定用户在哪个设计阶段看到该模型。</span>
                  </template>
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item label="标签">
                  <a-select
                    v-model:value="formState.tag_ids"
                    mode="multiple"
                    placeholder="选择标签"
                    allow-clear
                  >
                    <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.id">
                      {{ tag.name }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="[20, 0]">
              <a-col :xs="24" :md="12">
                <a-form-item label="图标">
                  <a-input v-model:value="formState.icon" placeholder="可选：emoji 或图标名" />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item label="图标地址">
                  <a-input v-model:value="formState.icon_url" placeholder="可选：https://..." />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="公开范围">
              <a-switch v-model:checked="formState.is_public" />
              <span class="switch-label">
                {{ formState.is_public ? '所有用户可见' : '仅管理员可见' }}
              </span>
            </a-form-item>
          </section>

          <section v-show="activeStep === 2" class="editor-card">
            <header class="editor-card__head">
              <div>
                <h2>镜像与运行</h2>
                <p>平台按 Kubernetes Job 执行，镜像必须是不可变 digest。</p>
              </div>
              <a-tag color="blue">步骤 2 / 5</a-tag>
            </header>

            <a-alert
              type="info"
              show-icon
              message="执行方式已固定为 k8s_job"
              description="不再提供 Docker / Python / SSH 工具类型。GPU、CPU、内存和超时由资源画像控制；集群与凭据由平台统一管理。"
              class="editor-alert"
            />

            <a-alert
              v-if="isLegacyTool"
              type="warning"
              show-icon
              message="当前模型仍使用旧版执行方式"
              description="此页只允许修改展示信息。请到「工具与模型 → 模型交付包」登记该模型的 Tool Package v2，并注册 K8s 候选版本。"
              class="editor-alert"
            >
              <template #action>
                <a-button size="small" @click="goPackages">去登记交付包</a-button>
              </template>
            </a-alert>

            <template v-if="!isLegacyTool">
              <a-form-item label="镜像 digest" name="k8s_image" :rules="k8sImageRules">
                <a-input
                  v-model:value="formState.k8s_image"
                  placeholder="10.202.2.228:30500/aidd/my-model@sha256:64位digest"
                />
                <template #extra>
                  <span class="form-extra">必须使用完整 sha256 digest；平台不会自动拉取 latest。</span>
                </template>
              </a-form-item>

              <a-row :gutter="[20, 0]">
                <a-col :xs="24" :md="12">
                  <a-form-item label="资源画像" name="k8s_resource_profile">
                    <a-input
                      v-model:value="formState.k8s_resource_profile"
                      placeholder="cpu-small / gpu-4c-16g"
                    />
                  </a-form-item>
                </a-col>
                <a-col :xs="24" :md="12">
                  <a-form-item label="超时时间（秒）" name="timeout_sec">
                    <a-input-number
                      v-model:value="formState.timeout_sec"
                      :min="60"
                      :max="86400"
                      style="width: 100%"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="[20, 0]">
                <a-col :xs="24" :md="12">
                  <a-form-item label="需要 GPU">
                    <a-switch v-model:checked="formState.gpu_required" />
                    <span class="switch-label">
                      {{ formState.gpu_required ? '申请 nvidia.com/gpu' : '仅 CPU' }}
                    </span>
                  </a-form-item>
                </a-col>
                <a-col v-if="formState.gpu_required" :xs="24" :md="12">
                  <a-form-item label="显存需求（MB）">
                    <a-input-number
                      v-model:value="formState.gpu_memory_mb"
                      :min="1024"
                      :step="1024"
                      style="width: 100%"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </template>
          </section>

          <section v-show="activeStep === 3" class="editor-card">
            <header class="editor-card__head">
              <div>
                <h2>输入 / 输出契约</h2>
                <p>契约来自模型交付包，模型编辑页只读展示，避免两套定义分叉。</p>
              </div>
              <a-tag :color="toolContract ? 'green' : 'orange'">
                {{ toolContract ? '已登记交付包' : '未登记交付包' }}
              </a-tag>
            </header>

            <a-alert
              v-if="!toolContract"
              type="warning"
              show-icon
              message="该模型还没有标准 Artifact 契约"
              description="请在「模型交付包」登记 Tool Package v2，平台会自动解析输入/输出槽位与参数 Schema。"
              class="editor-alert"
            >
              <template #action>
                <a-button size="small" @click="goPackages">去登记</a-button>
              </template>
            </a-alert>

            <div v-else class="contract-block">
              <div class="contract-block__head">
                <h3>输入（Artifact inputs）</h3>
                <span class="contract-pill">平台标准类型</span>
              </div>
              <div v-if="contractInputs.length === 0" class="contract-empty">未声明输入槽位</div>
              <div v-else class="contract-rows">
                <div v-for="slot in contractInputs" :key="slot.name" class="contract-row">
                  <div class="contract-row__main">
                    <strong>{{ slot.title || slot.name }}</strong>
                    <code>{{ slot.type }}</code>
                  </div>
                  <a-tag :color="slot.required === false ? 'default' : 'blue'">
                    {{ slot.required === false ? '可选' : '必填' }}
                  </a-tag>
                </div>
              </div>
            </div>

            <div v-if="toolContract" class="contract-block">
              <div class="contract-block__head">
                <h3>输出（Artifact outputs）</h3>
                <span class="contract-pill">平台标准类型</span>
              </div>
              <div v-if="contractOutputs.length === 0" class="contract-empty">未声明输出槽位</div>
              <div v-else class="contract-rows">
                <div v-for="slot in contractOutputs" :key="slot.name" class="contract-row">
                  <div class="contract-row__main">
                    <strong>{{ slot.title || slot.name }}</strong>
                    <code>{{ slot.type }}</code>
                  </div>
                  <a-tag :color="slot.required === false ? 'default' : 'blue'">
                    {{ slot.required === false ? '可选' : '必填' }}
                  </a-tag>
                </div>
              </div>
            </div>

            <p v-if="toolContract" class="contract-hint">
              输入/输出必须使用平台已支持的标准类型；发布新版本前平台会再次校验。
            </p>
          </section>

          <section v-show="activeStep === 4" class="editor-card">
            <header class="editor-card__head">
              <div>
                <h2>运行参数</h2>
                <p>定义用户提交任务时可调的科学参数，默认值与范围必须与镜像实现一致。</p>
              </div>
              <a-tag color="blue">步骤 4 / 5</a-tag>
            </header>

            <a-form-item name="input_schema">
              <ToolParameterSchemaEditor
                v-model:model-value="inputParameterSchema"
                :allow-file-fields="false"
                @validity-change="setInputSchemaEditorValidity"
              />
            </a-form-item>

            <a-form-item :label="t('tools.documentationMarkdown')" name="documentation_markdown">
              <a-textarea
                v-model:value="formState.documentation_markdown"
                class="tool-documentation-editor"
                placeholder="## 模型介绍&#10;&#10;## 参数说明&#10;&#10;## 输出文件"
                :rows="8"
              />
              <template #extra>
                <span class="form-extra">{{ t('tools.documentationMarkdownHint') }}</span>
              </template>
            </a-form-item>
          </section>

          <section v-show="activeStep === 5" class="editor-card">
            <header class="editor-card__head">
              <div>
                <h2>版本与发布</h2>
                <p>修改镜像、资源或参数会创建新版本；只改展示信息不会产生新版本。</p>
              </div>
              <a-tag color="blue">步骤 5 / 5</a-tag>
            </header>

            <a-row :gutter="[20, 0]">
              <a-col :xs="24" :md="8">
                <a-form-item label="版本号" name="version">
                  <a-input v-model:value="formState.version" placeholder="例如：1.1.0" />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="16">
                <a-form-item label="版本说明" name="notes">
                  <a-input v-model:value="formState.notes" placeholder="简要说明此版本特点" />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="更新日志" name="changelog">
              <a-textarea
                v-model:value="formState.changelog"
                placeholder="详细描述此版本新增、修复或变更内容"
                :rows="4"
              />
            </a-form-item>

            <a-alert
              v-if="isEdit && formState.version !== originalVersion"
              type="info"
              show-icon
              message="保存后会创建新版本"
              description="当前版本号已变更，平台会保留旧版本，并把新版本设为当前版本。"
            />
          </section>

          <footer class="editor-footer">
            <div class="editor-footer__left">
              <a-button v-if="activeStep > 1" @click="activeStep -= 1">上一步</a-button>
            </div>
            <div class="editor-footer__right">
              <a-button @click="goBack">取消</a-button>
              <a-button v-if="activeStep < 5" type="primary" @click="nextStep">
                下一步：{{ wizardSteps[activeStep]?.title }}
                <ArrowRightOutlined />
              </a-button>
              <a-button v-else type="primary" html-type="submit" :loading="submitting">
                <SaveOutlined />
                {{ isEdit ? '保存模型' : '创建模型' }}
              </a-button>
            </div>
          </footer>
        </a-form>
      </main>

      <aside class="model-editor__summary">
        <div class="summary-card">
          <h3>模型摘要</h3>
          <dl>
            <div>
              <dt>slug</dt>
              <dd>{{ formState.slug || '未填写' }}</dd>
            </div>
            <div>
              <dt>能力族</dt>
              <dd>{{ modelFamilyLabel || '未选择' }}</dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>{{ formState.version || '未填写' }}</dd>
            </div>
            <div>
              <dt>输入 / 输出</dt>
              <dd>{{ contractInputs.length }} / {{ contractOutputs.length }}</dd>
            </div>
            <div>
              <dt>镜像</dt>
              <dd :title="formState.k8s_image">{{ digestShort || '未填写' }}</dd>
            </div>
          </dl>
          <div class="summary-divider" />
          <div class="summary-status">
            <span :class="formState.name && formState.slug ? 'ok' : 'warn'">
              {{ formState.name && formState.slug ? '✓ 基本信息完整' : '! 基本信息待完善' }}
            </span>
            <span :class="formState.k8s_image ? 'ok' : 'warn'">
              {{ formState.k8s_image ? '✓ 镜像已填写' : '! 镜像待填写' }}
            </span>
            <span :class="toolContract ? 'ok' : 'warn'">
              {{ toolContract ? '✓ 契约已登记' : '! 契约待登记' }}
            </span>
          </div>
          <a-button block class="summary-link" @click="goPackages">
            打开模型交付包
          </a-button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckOutlined,
  InfoCircleOutlined,
  ReadOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
import ToolParameterSchemaEditor from '@/components/tools/ToolParameterSchemaEditor.vue'
import { useToolCreateEditorState } from '@/composables/useToolCreateEditorState'
import {
  buildToolEditFormPatch,
  createEmptyParameterSchema,
  createToolCreateFormState,
  createToolCreateSubmission,
  formatToolCreateSubmissionErrorMessage,
  buildToolVersionCreatePayload,
  resolveToolCreateSubmissionBlocker,
  validateParameterSchema,
  type ToolConfigFormPatch,
  type ToolCreateFormState,
} from '@/domain/tools'
import type { Tool, ToolSchema } from '@/types/models'
import { useToolsStore } from '@/stores'
import {
  createToolVersion,
  getToolDetail,
  updateTool,
} from '@/api/tools'

interface ContractSlot {
  name: string
  title?: string | null
  type: string
  required?: boolean
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const toolsStore = useToolsStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const submitting = ref(false)
const activeStep = ref(1)

const wizardSteps = [
  { key: 1, title: '基本信息', hint: '名称 / slug / 能力族' },
  { key: 2, title: '镜像与运行', hint: '镜像 digest / 资源画像' },
  { key: 3, title: '输入/输出契约', hint: '标准 Artifact 类型' },
  { key: 4, title: '运行参数', hint: 'parameters_schema' },
  { key: 5, title: '版本与发布', hint: '版本号 / 变更说明 / 冒烟' },
]

const originalVersion = ref('')
const originalChangelog = ref('')
const originalNotes = ref('')
const originalConfigSnapshot = ref('')
const toolContract = ref<Tool['contract'] | null>(null)

const isEdit = computed(() => route.name === 'AdminToolEdit' || route.name === 'ToolEdit')
const toolId = computed(() => String(route.params.id || ''))

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
  snapshot: editorStateSnapshot,
} = useToolCreateEditorState()

const categories = computed(() => toolsStore.categories)
const tags = computed(() => toolsStore.tags)

const isLegacyTool = computed(() => formState.tool_type !== 'k8s_job')

const modelFamilyLabel = computed(() => {
  const category = categories.value.find(item => item.id === formState.category_id)
  return toolContract.value?.model_family || category?.name || ''
})

const contractInputs = computed<ContractSlot[]>(() => {
  const slots = toolContract.value?.artifacts?.inputs
  return Array.isArray(slots)
    ? slots.map(slot => ({
        name: slot.name,
        title: slot.title,
        type: slot.type,
        required: slot.required,
      }))
    : []
})

const contractOutputs = computed<ContractSlot[]>(() => {
  const slots = toolContract.value?.artifacts?.outputs
  return Array.isArray(slots)
    ? slots.map(slot => ({
        name: slot.name,
        title: slot.name,
        type: slot.type,
        required: slot.required,
      }))
    : []
})

const digestShort = computed(() => {
  const raw = formState.k8s_image
  if (!raw) return ''
  const at = raw.indexOf('@sha256:')
  if (at < 0) return raw
  return `sha256:${raw.slice(at + 8, at + 20)}…`
})

const k8sImageRules = computed<Rule[]>(() => {
  if (isLegacyTool.value) return []
  return [
    { required: true, message: '请输入不可变镜像引用', trigger: 'blur' },
    {
      pattern: /@sha256:[a-fA-F0-9]{64}$/,
      message: '镜像必须使用完整 SHA-256 digest',
      trigger: 'blur',
    },
  ]
})

const formRules: Record<string, Rule[]> = {
  name: [
    { required: true, message: '请输入模型名称', trigger: 'blur' },
    { min: 2, max: 100, message: '名称长度为 2–100 个字符', trigger: 'blur' },
  ],
  slug: [
    { required: true, message: '请输入模型标识', trigger: 'blur' },
    { pattern: /^[a-z0-9-]+$/, message: '只允许小写字母、数字与连字符', trigger: 'blur' },
  ],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}

const stepFields: Record<number, string[]> = {
  1: ['name', 'slug', 'description'],
  2: isLegacyTool.value ? [] : ['k8s_image', 'k8s_resource_profile'],
  3: [],
  4: [],
  5: ['version'],
}

function setInputSchemaEditorValidity(valid: boolean): void {
  inputSchemaEditorValid.value = valid
}

function applyToolFormPatch(patch: ToolConfigFormPatch): void {
  Object.assign(formState, patch.form)
}

function goBack(): void {
  router.back()
}

function goGuide(): void {
  router.push('/admin/model-guide')
}

function goPackages(): void {
  router.push('/admin/tool-packages')
}

const nextStep = async (): Promise<void> => {
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

const loadToolDetail = async (): Promise<void> => {
  if (!isEdit.value || !toolId.value) return
  loading.value = true
  try {
    const response = await getToolDetail(toolId.value)
    const tool = response.data
    toolContract.value = tool.contract ?? null
    const patch = buildToolEditFormPatch(tool)
    applyToolFormPatch(patch)
    originalVersion.value = patch.originalVersion
    originalChangelog.value = patch.originalChangelog
    originalNotes.value = patch.originalNotes
    originalConfigSnapshot.value = patch.originalConfigSnapshot
    // 旧版 Agent 语义映射不再在模型编辑页维护。
    formState.agent_capability_enabled = false
    formState.agent_inputs = []
    formState.agent_outputs = []
  } catch {
    message.error(t('tools.loadFailed'))
    router.push('/admin/tools')
  } finally {
    loading.value = false
  }
}

const handleSubmit = async (): Promise<void> => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  const schemaErrors = validateParameterSchema(inputParameterSchema.value)
  if (!inputSchemaEditorValid.value || schemaErrors.length > 0) {
    message.error(schemaErrors[0] || '请先修正运行参数 Schema')
    return
  }

  submitting.value = true
  try {
    let submission: ReturnType<typeof createToolCreateSubmission>
    try {
      submission = createToolCreateSubmission({
        formState,
        editorState: editorStateSnapshot(),
        agentDefaultsText: '{}',
        isEdit: isEdit.value,
        originalVersion: originalVersion.value,
        originalChangelog: originalChangelog.value,
        originalNotes: originalNotes.value,
        originalConfigSnapshot: originalConfigSnapshot.value,
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
          buildToolVersionCreatePayload(formState, submission.config),
        )
      }
      message.success(
        submission.versionConfigChanged ? '模型与版本更新成功' : '模型信息已保存',
      )
    } else {
      message.error('请通过「模型交付包」登记新模型')
      return
    }

    router.push('/admin/tools')
  } catch {
    // 请求层已提示错误
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    toolsStore.fetchCategories(),
    toolsStore.fetchTags(),
  ])
  await loadToolDetail()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-editor {
  padding: @spacing-lg 0 90px;

  &__topbar {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-lg;
    margin-bottom: @spacing-lg;
  }

  &__back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
    padding: 0;
    border: none;
    background: transparent;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    cursor: pointer;

    &:hover {
      color: @primary-color;
    }
  }

  &__title {
    margin: 0;
    color: @text-color-light-primary;
    font-size: 24px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }

  &__subtitle {
    margin: 6px 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  &__loading {
    max-width: 900px;
  }

  &__layout {
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr) 220px;
    gap: @spacing-lg;
    align-items: start;
  }

  &__steps {
    position: sticky;
    top: @spacing-lg;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: @spacing-sm;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    background: @bg-surface;
  }

  &__main {
    min-width: 0;
  }

  &__summary {
    position: sticky;
    top: @spacing-lg;
  }
}

.model-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: @border-radius-md;
  background: transparent;
  color: @text-color-light-secondary;
  text-align: left;
  cursor: pointer;
  transition: all @transition-fast;

  &:hover {
    background: @bg-hover;
  }

  &.is-active {
    border-color: @accent-color-border;
    background: @accent-color-light;
    color: @text-color-light-primary;
  }

  &.is-done .model-step__index {
    background: @success-color;
    color: #fff;
  }

  &__index {
    display: inline-flex;
    flex: 0 0 24px;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: 1px solid @border-color;
    border-radius: 50%;
    background: @bg-elevated;
    color: @text-color-light-secondary;
    font-size: 12px;
    font-weight: 600;
  }

  &.is-active &__index {
    border-color: @primary-color;
    background: @primary-color;
    color: #fff;
  }

  &__copy {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;

    strong {
      color: inherit;
      font-size: 13px;
      font-weight: 600;
    }

    small {
      color: @text-color-light-tertiary;
      font-size: 11px;
      line-height: 1.4;
    }
  }
}

.model-step-help {
  display: flex;
  gap: 8px;
  margin-top: @spacing-sm;
  padding: @spacing-sm;
  border-radius: @border-radius-md;
  background: @bg-color-light;
  color: @text-color-light-tertiary;
  font-size: 11px;
  line-height: 1.6;

  p {
    margin: 0;
  }
}

.editor-card {
  padding: @spacing-xl;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  background: @bg-surface;

  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-lg;

    h2 {
      margin: 0;
      color: @text-color-light-primary;
      font-size: 18px;
    }

    p {
      margin: 5px 0 0;
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
    }
  }
}

.editor-alert {
  margin-bottom: @spacing-lg;
}

.form-extra {
  color: @text-color-light-tertiary;
  font-size: @font-size-sm;
}

.switch-label {
  margin-left: @spacing-sm;
  color: @text-color-light-secondary;
}

.contract-block {
  margin-bottom: @spacing-lg;

  &__head {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    margin-bottom: @spacing-sm;

    h3 {
      margin: 0;
      color: @text-color-light-primary;
      font-size: 14px;
      font-weight: 600;
    }
  }
}

.contract-pill {
  padding: 1px 7px;
  border-radius: 999px;
  background: @accent-color-light;
  color: @primary-color;
  font-size: 11px;
}

.contract-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.contract-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-md;
  padding: 10px 12px;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-md;
  background: @bg-color-light;
}

.contract-row__main {
  display: flex;
  flex-direction: column;
  gap: 3px;

  strong {
    color: @text-color-light-primary;
    font-size: 13px;
  }

  code {
    color: @text-color-light-secondary;
    font-family: @font-family-mono;
    font-size: 11px;
  }
}

.contract-empty,
.contract-hint {
  color: @text-color-light-tertiary;
  font-size: @font-size-sm;
}

.editor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: @spacing-lg;

  &__right {
    display: flex;
    gap: @spacing-sm;
  }
}

.summary-card {
  padding: @spacing-lg;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  background: @bg-surface;

  h3 {
    margin: 0 0 @spacing-md;
    color: @text-color-light-primary;
    font-size: 14px;
  }

  dl {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin: 0;
  }

  dl > div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  dt {
    color: @text-color-light-tertiary;
    font-size: 11px;
  }

  dd {
    margin: 0;
    color: @text-color-light-primary;
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.summary-divider {
  height: 1px;
  margin: @spacing-md 0;
  background: @border-color-light;
}

.summary-status {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: @spacing-md;
  font-size: 11px;

  .ok {
    color: @success-color;
  }

  .warn {
    color: @warning-color;
  }
}

.summary-link {
  margin-top: @spacing-sm;
}

@media (max-width: 1280px) {
  .model-editor__layout {
    grid-template-columns: 200px minmax(0, 1fr);
  }

  .model-editor__summary {
    position: static;
    grid-column: 1 / -1;
  }
}

@media (max-width: @screen-md) {
  .model-editor__layout {
    grid-template-columns: 1fr;
  }

  .model-editor__steps {
    position: static;
    flex-direction: row;
    overflow-x: auto;
  }

  .model-step {
    min-width: 150px;
  }

  .model-step-help {
    display: none;
  }

  .editor-card {
    padding: @spacing-lg;
  }
}
</style>
