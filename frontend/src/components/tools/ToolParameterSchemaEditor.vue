<template>
  <div class="parameter-schema-editor">
    <div class="editor-toolbar">
      <span class="editor-title">运行参数</span>
      <a-radio-group
        :value="editorMode"
        size="small"
        button-style="solid"
        @change="handleModeChange"
      >
        <a-radio-button value="fields">表单编辑</a-radio-button>
        <a-radio-button value="json">高级 JSON</a-radio-button>
      </a-radio-group>
    </div>

    <a-alert
      v-if="editorError"
      class="editor-alert"
      type="error"
      show-icon
      :message="editorError"
    />

    <a-textarea
      v-if="editorMode === 'json'"
      :value="jsonText"
      :rows="12"
      spellcheck="false"
      @input="handleJsonInput"
    />

    <template v-else>
      <a-empty v-if="fields.length === 0" description="还没有运行参数" />
      <div v-else class="parameter-list">
        <section v-for="field in fields" :key="field.id" class="parameter-row">
          <div class="parameter-row-header">
            <strong>{{ field.title || field.name || '新参数' }}</strong>
            <a-tooltip title="删除参数">
              <a-button size="small" danger @click="removeField(field.id)">
                <DeleteOutlined />
              </a-button>
            </a-tooltip>
          </div>

          <a-row :gutter="12" align="bottom">
            <a-col :xs="24" :md="7">
              <a-form-item label="参数名">
                <a-input
                  v-model:value="field.name"
                  placeholder="例如 num_samples"
                  @change="commitFields"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="7">
              <a-form-item label="显示名称">
                <a-input
                  v-model:value="field.title"
                  placeholder="例如 生成数量"
                  @change="commitFields"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="18" :md="6">
              <a-form-item label="输入类型">
                <a-select :value="field.type" @change="changeFieldType(field, $event)">
                  <a-select-option value="string">文本</a-select-option>
                  <a-select-option value="number">小数</a-select-option>
                  <a-select-option value="integer">整数</a-select-option>
                  <a-select-option value="boolean">开关</a-select-option>
                  <a-select-option value="array">列表</a-select-option>
                  <a-select-option value="object">对象</a-select-option>
                  <a-select-option v-if="allowFileFields" value="file">文件</a-select-option>
                  <a-select-option v-if="allowFileFields" value="select">选项</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :xs="6" :md="4">
              <a-form-item label="必填">
                <a-switch v-model:checked="field.required" @change="commitFields" />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="12">
            <a-col :xs="24" :md="12">
              <a-form-item label="参数说明">
                <a-textarea
                  v-model:value="field.description"
                  :rows="2"
                  placeholder="告诉用户这个参数控制什么"
                  @change="commitFields"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item label="默认值">
                <a-select
                  v-if="field.type === 'boolean'"
                  v-model:value="field.defaultText"
                  allow-clear
                  placeholder="不设置默认值"
                  @change="setBooleanDefault(field, $event)"
                >
                  <a-select-option value="true">开启</a-select-option>
                  <a-select-option value="false">关闭</a-select-option>
                </a-select>
                <a-input-number
                  v-else-if="field.type === 'number' || field.type === 'integer'"
                  :value="numericDefault(field.defaultText)"
                  :precision="field.type === 'integer' ? 0 : undefined"
                  style="width: 100%"
                  placeholder="不设置默认值"
                  @change="setNumericDefault(field, $event)"
                />
                <a-input
                  v-else-if="field.type === 'string' || field.type === 'select'"
                  v-model:value="field.defaultText"
                  placeholder="不设置默认值"
                  @change="setStringDefault(field)"
                />
                <span v-else class="advanced-value-hint">复杂默认值请在高级 JSON 中编辑</span>
              </a-form-item>
            </a-col>
          </a-row>

          <a-collapse ghost>
            <a-collapse-panel :key="field.id" header="选项、范围与格式">
              <a-row :gutter="12">
                <a-col v-if="supportsEnum(field.type)" :xs="24" :md="12">
                  <a-form-item label="可选值（每行一个）">
                    <a-textarea
                      v-model:value="field.enumText"
                      :rows="3"
                      placeholder="例如\nfast\naccurate"
                      @change="commitEnum(field)"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-if="field.type === 'number' || field.type === 'integer'" :xs="12" :md="6">
                  <a-form-item label="最小值">
                    <a-input-number
                      v-model:value="field.minimum"
                      :precision="field.type === 'integer' ? 0 : undefined"
                      style="width: 100%"
                      @change="commitFields"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-if="field.type === 'number' || field.type === 'integer'" :xs="12" :md="6">
                  <a-form-item label="最大值">
                    <a-input-number
                      v-model:value="field.maximum"
                      :precision="field.type === 'integer' ? 0 : undefined"
                      style="width: 100%"
                      @change="commitFields"
                    />
                  </a-form-item>
                </a-col>
                <a-col v-if="field.type === 'string'" :xs="24" :md="12">
                  <a-form-item label="文本呈现">
                    <a-select
                      v-model:value="field.format"
                      allow-clear
                      placeholder="单行文本"
                      @change="commitFields"
                    >
                      <a-select-option value="textarea">多行文本</a-select-option>
                      <a-select-option value="fasta">FASTA 序列</a-select-option>
                      <a-select-option value="pdb">PDB 结构</a-select-option>
                      <a-select-option value="email">邮箱</a-select-option>
                      <a-select-option value="url">URL</a-select-option>
                      <a-select-option v-if="allowFileFields" value="uri">文件 URI</a-select-option>
                      <a-select-option v-if="allowFileFields" value="file">文件</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
              </a-row>
            </a-collapse-panel>
          </a-collapse>
        </section>
      </div>

      <a-button class="add-parameter" @click="addField">
        <PlusOutlined />
        添加参数
      </a-button>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
  import type { SchemaProperty, ToolSchema } from '@/types/models'
  import { validateParameterSchema } from '@/domain/tools/parameter-schema'

  interface ParameterFieldDraft {
    id: number
    name: string
    title: string
    type: string
    description: string
    required: boolean
    defaultText: string
    hasDefault: boolean
    defaultDirty: boolean
    enumText: string
    hasEnum: boolean
    enumDirty: boolean
    minimum?: number
    maximum?: number
    format?: string
    source: SchemaProperty
    sourceType?: SchemaProperty['type']
  }

  const props = withDefaults(defineProps<{
    modelValue: ToolSchema
    allowFileFields?: boolean
  }>(), {
    allowFileFields: false,
  })

  const emit = defineEmits<{
    'update:modelValue': [schema: ToolSchema]
    'validity-change': [valid: boolean]
  }>()

  const fields = ref<ParameterFieldDraft[]>([])
  const editorMode = ref<'fields' | 'json'>('fields')
  const jsonText = ref('')
  const editorError = ref('')
  const lastEmittedSchema = ref('')
  let nextFieldId = 1

  const validationErrors = computed(() => validateParameterSchema(props.modelValue, {
    allowLegacyUiTypes: props.allowFileFields,
  }))

  watch(
    () => props.modelValue,
    (schema) => {
      const serialized = JSON.stringify(schema)
      if (serialized === lastEmittedSchema.value) return
      fields.value = schemaToFields(schema)
      jsonText.value = JSON.stringify(schema, null, 2)
      lastEmittedSchema.value = serialized
      editorError.value = ''
      emit('validity-change', validationErrors.value.length === 0)
    },
    { immediate: true, deep: true },
  )

  function schemaToFields(schema: ToolSchema): ParameterFieldDraft[] {
    return Object.entries(schema.properties ?? {}).map(([name, property]) => {
      const source = { ...property }
      const rawType = property.type
      const type = Array.isArray(rawType)
        ? String(rawType.find(item => item !== 'null') ?? 'string')
        : String(rawType ?? '')
      const defaultValue = property.default
      const hasDefault = Object.prototype.hasOwnProperty.call(property, 'default')
      const sourceEnum = Array.isArray(property.enum) ? [...property.enum] : undefined
      return {
        id: nextFieldId++,
        name,
        title: property.title ?? '',
        type,
        description: property.description ?? '',
        required: schema.required?.includes(name) ?? false,
        defaultText: typeof defaultValue === 'string' ? defaultValue : String(defaultValue ?? ''),
        hasDefault,
        defaultDirty: false,
        enumText: sourceEnum?.map(value => String(value)).join('\n') ?? '',
        hasEnum: sourceEnum !== undefined,
        enumDirty: false,
        minimum: property.minimum,
        maximum: property.maximum,
        format: property.format,
        source,
        sourceType: rawType,
      }
    })
  }

  function addField() {
    let index = fields.value.length + 1
    const currentNames = new Set(fields.value.map(field => field.name.trim()))
    while (currentNames.has(`parameter_${index}`)) index += 1
    fields.value.push({
      id: nextFieldId++,
      name: `parameter_${index}`,
      title: `参数 ${index}`,
      type: 'string',
      description: '',
      required: false,
      defaultText: '',
      hasDefault: false,
      defaultDirty: false,
      enumText: '',
      hasEnum: false,
      enumDirty: false,
      source: { type: 'string' },
    })
    commitFields()
  }

  function removeField(id: number) {
    fields.value = fields.value.filter(field => field.id !== id)
    commitFields()
  }

  function setNumericDefault(field: ParameterFieldDraft, value: number | string | null) {
    field.defaultText = value === null || value === undefined ? '' : String(value)
    field.hasDefault = value !== null && value !== undefined
    field.defaultDirty = true
    commitFields()
  }

  function setBooleanDefault(field: ParameterFieldDraft, value: unknown) {
    field.defaultText = value === 'true' || value === 'false' ? value : ''
    field.hasDefault = field.defaultText !== ''
    field.defaultDirty = true
    commitFields()
  }

  function setStringDefault(field: ParameterFieldDraft) {
    field.hasDefault = field.defaultText !== ''
    field.defaultDirty = true
    commitFields()
  }

  function commitEnum(field: ParameterFieldDraft) {
    field.hasEnum = field.enumText.trim().length > 0
    field.enumDirty = true
    commitFields()
  }

  function changeFieldType(field: ParameterFieldDraft, value: unknown) {
    field.type = String(value ?? '')
    field.defaultText = ''
    field.hasDefault = false
    field.defaultDirty = true
    field.enumText = ''
    field.hasEnum = false
    field.enumDirty = true
    if (field.type !== 'string') field.format = undefined
    commitFields()
  }

  function numericDefault(value: string): number | undefined {
    if (!value.trim()) return undefined
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }

  function commitFields() {
    const names = fields.value.map(field => field.name.trim())
    if (names.some(name => !name)) {
      editorError.value = '参数名不能为空'
      emit('validity-change', false)
      return
    }
    if (names.some((name, index) => names.indexOf(name) !== index)) {
      editorError.value = '参数名不能重复'
      emit('validity-change', false)
      return
    }

    const properties: Record<string, SchemaProperty> = {}
    for (const field of fields.value) {
      const name = field.name.trim()
      if (!name) continue
      const sourceType = field.sourceType
      const next: SchemaProperty = { ...field.source }
      if (field.type && field.type !== normalizedType(sourceType)) next.type = field.type as SchemaProperty['type']
      if (field.title.trim()) next.title = field.title.trim()
      else delete next.title
      if (field.description.trim()) next.description = field.description.trim()
      else delete next.description
      if (['string', 'select', 'number', 'integer', 'boolean'].includes(field.type)) {
        if (field.defaultDirty) {
          if (field.hasDefault) {
            const defaultValue = parseDefault(field)
            if (defaultValue !== undefined) next.default = defaultValue
          } else {
            delete next.default
          }
        }
      }
      if (field.hasEnum && supportsEnum(field.type)) {
        if (field.enumDirty) {
          const enumValues = parseEnum(field.enumText, field.type)
          if (enumValues.length > 0) next.enum = enumValues
          else delete next.enum
        }
      } else if (field.enumDirty) {
        delete next.enum
      }
      if (field.minimum !== undefined) next.minimum = field.minimum
      else delete next.minimum
      if (field.maximum !== undefined) next.maximum = field.maximum
      else delete next.maximum
      if (field.type === 'string') {
        if (field.format) next.format = field.format as SchemaProperty['format']
        else delete next.format
      }
      if (field.type === 'file' && field.format) {
        next.format = field.format as SchemaProperty['format']
      }
      properties[name] = next
    }

    const schema: ToolSchema = {
      ...props.modelValue,
      type: 'object',
      properties,
      required: fields.value
        .filter(field => field.required && field.name.trim())
        .map(field => field.name.trim()),
    }
    const errors = validateParameterSchema(schema, { allowLegacyUiTypes: props.allowFileFields })
    editorError.value = errors[0] ?? ''
    const serialized = JSON.stringify(schema)
    lastEmittedSchema.value = serialized
    emit('update:modelValue', schema)
    emit('validity-change', errors.length === 0)
  }

  function handleModeChange(event: { target?: { value?: unknown } }) {
    const nextMode = event.target?.value
    if (nextMode === 'json') {
      commitFields()
      jsonText.value = JSON.stringify(props.modelValue, null, 2)
      editorMode.value = 'json'
      return
    }
    if (nextMode !== 'fields') return
    if (!applyJsonText()) return
    editorMode.value = 'fields'
    fields.value = schemaToFields(props.modelValue)
  }

  function handleJsonInput(event: Event) {
    jsonText.value = (event.target as HTMLTextAreaElement).value
    applyJsonText()
  }

  function applyJsonText(): boolean {
    let parsed: unknown
    try {
      parsed = JSON.parse(jsonText.value)
    } catch {
      editorError.value = 'JSON 格式不正确'
      emit('validity-change', false)
      return false
    }
    if (!isToolSchema(parsed)) {
      editorError.value = 'Schema 必须包含 type: object 和 properties 对象'
      emit('validity-change', false)
      return false
    }
    const errors = validateParameterSchema(parsed, { allowLegacyUiTypes: props.allowFileFields })
    editorError.value = errors[0] ?? ''
    if (errors.length > 0) {
      emit('validity-change', false)
      return false
    }
    lastEmittedSchema.value = JSON.stringify(parsed)
    emit('update:modelValue', parsed)
    emit('validity-change', true)
    return true
  }

  function parseDefault(field: ParameterFieldDraft): unknown {
    if (field.type === 'boolean') {
      if (field.defaultText === 'true') return true
      if (field.defaultText === 'false') return false
      return undefined
    }
    if (field.type === 'number' || field.type === 'integer') {
      if (!field.defaultText.trim()) return undefined
      const value = Number(field.defaultText)
      return Number.isFinite(value) ? value : undefined
    }
    return field.defaultText
  }

  function parseEnum(value: string, type: string): unknown[] {
    const lines = value.split('\n').map(line => line.trim()).filter(Boolean)
    if (type === 'number' || type === 'integer') {
      return lines.map(line => Number(line)).filter(Number.isFinite)
    }
    return lines
  }

  function supportsEnum(type: string): boolean {
    return type === 'string' || type === 'number' || type === 'integer' || type === 'select'
  }

  function normalizedType(type: SchemaProperty['type']): string {
    return Array.isArray(type)
      ? String(type.find(item => item !== 'null') ?? '')
      : String(type ?? '')
  }

  function isToolSchema(value: unknown): value is ToolSchema {
    return Boolean(
      value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      (value as Record<string, unknown>).type === 'object' &&
      (value as Record<string, unknown>).properties &&
      typeof (value as Record<string, unknown>).properties === 'object' &&
      !Array.isArray((value as Record<string, unknown>).properties)
    )
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .parameter-schema-editor {
    display: grid;
    gap: @spacing-md;
    min-width: 0;
  }

  .editor-toolbar,
  .parameter-row-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .editor-title {
    color: @text-color-light-secondary;
    font-weight: @font-weight-medium;
  }

  .editor-alert {
    margin: 0;
  }

  .parameter-list {
    display: grid;
    gap: @spacing-md;
  }

  .parameter-row {
    min-width: 0;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-base;
  }

  .parameter-row-header {
    margin-bottom: @spacing-sm;
  }

  .parameter-row :deep(.ant-form-item) {
    margin-bottom: @spacing-sm;
  }

  .parameter-row :deep(.ant-collapse) {
    border: 0;
  }

  .advanced-value-hint {
    color: @text-color-light-tertiary;
    line-height: 32px;
  }

  .add-parameter {
    justify-self: start;
  }
</style>
