<template>
  <template v-for="(prop, key) in visibleProperties" :key="key">
    <a-form-item
      :name="key"
      :label="prop.title"
      :rules="fieldRules(String(key), prop)"
      :extra="prop.description"
    >
      <a-input
        v-if="prop.type === 'string' && (!prop.format || prop.format === 'email' || prop.format === 'url') && !prop.enum"
        v-model:value="formState[key]"
        :type="prop.format === 'email' ? 'email' : prop.format === 'url' ? 'url' : 'text'"
      />
      <a-textarea
        v-else-if="prop.type === 'string' && (prop.format === 'textarea' || prop.format === 'fasta' || prop.format === 'pdb')"
        v-model:value="formState[key]"
        :rows="prop.format === 'fasta' || prop.format === 'pdb' ? 8 : 4"
        :class="{ 'code-input': prop.format === 'fasta' || prop.format === 'pdb' }"
      />
      <a-input-number
        v-else-if="prop.type === 'number' || prop.type === 'integer'"
        v-model:value="formState[key]"
        :min="prop.minimum"
        :max="prop.maximum"
        :step="prop.type === 'integer' ? 1 : undefined"
        style="width: 100%"
      />
      <a-switch
        v-else-if="prop.type === 'boolean'"
        v-model:checked="formState[key]"
      />
      <a-select
        v-else-if="prop.type === 'select' || (prop.enum && prop.type !== 'array')"
        v-model:value="formState[key]"
      >
        <a-select-option v-for="opt in prop.enum" :key="String(opt)" :value="opt">
          {{ opt }}
        </a-select-option>
      </a-select>
      <a-select
        v-else-if="prop.type === 'array' && prop.items?.enum"
        v-model:value="formState[key]"
        mode="multiple"
      >
        <a-select-option v-for="opt in prop.items.enum" :key="String(opt)" :value="opt">
          {{ opt }}
        </a-select-option>
      </a-select>
      <a-textarea
        v-else-if="isStructuredField(prop)"
        :value="structuredEditorValue(String(key), prop)"
        :rows="6"
        class="code-input"
        @update:value="updateStructuredValue(String(key), $event)"
      />
      <ArtifactFilePicker
        v-else-if="isFileField(prop)"
        :upload-list="fileList[String(key)] ?? []"
        :selected-artifact="selectedArtifacts[String(key)] ?? null"
        :accept="fileAccept(String(key), prop)"
        :allow-artifacts="allowArtifacts"
        :allow-uploads="allowUploads"
        :current-tool-slug="toolSlug"
        :preferred-group-id="preferredGroupId"
        :preferred-tool-slug="preferredToolSlug"
        :external-selection-path="externalSelectionPath"
        @update:upload-list="(files) => emit('update:fileList', String(key), files)"
        @update:selected-artifact="(artifact) => emit('update:selectedArtifact', String(key), artifact)"
      />
      <slot name="file-field-extra" :field-key="String(key)" :property="prop" />
    </a-form-item>
  </template>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { UploadFile } from 'ant-design-vue'
  import type { Rule } from 'ant-design-vue/es/form'
  import type { ArtifactFile, SchemaProperty, ToolSchema } from '@/types/models'
  import type { WorkflowArtifactSelectionPath } from '@/workflow/artifact-hierarchy'
  import { isFileSchemaProperty } from '@/domain/tools'
  import ArtifactFilePicker from './ArtifactFilePicker.vue'

  const props = withDefaults(
    defineProps<{
      schema: ToolSchema
      formState: Record<string, unknown>
      fileList: Record<string, UploadFile[]>
      selectedArtifacts: Record<string, ArtifactFile | undefined>
      allowArtifacts?: boolean
      allowUploads?: boolean
      toolId?: string | null
      toolSlug?: string | null
      preferredGroupId?: string | null
      preferredToolSlug?: string | null
      externalSelectionPath?: WorkflowArtifactSelectionPath | null
      hiddenFieldKeys?: string[]
      getFileAccept?: (key: string, property: SchemaProperty) => string | undefined
      isFileFieldSatisfied?: (key: string, property: SchemaProperty) => boolean
      requiredMessage?: (title: string) => string
      minLengthMessage?: (min: number) => string
      maxLengthMessage?: (max: number) => string
    }>(),
    {
      allowArtifacts: true,
      allowUploads: true,
      toolId: null,
      toolSlug: null,
      preferredGroupId: null,
      preferredToolSlug: null,
      externalSelectionPath: null,
      hiddenFieldKeys: () => [],
      getFileAccept: undefined,
      isFileFieldSatisfied: undefined,
      requiredMessage: (title: string) => `${title} is required`,
      minLengthMessage: (min: number) => `Min length: ${min}`,
      maxLengthMessage: (max: number) => `Max length: ${max}`,
    }
  )

  const emit = defineEmits<{
    'update:fileList': [key: string, files: UploadFile[]]
    'update:selectedArtifact': [key: string, artifact: ArtifactFile | null]
  }>()

  const { t } = useI18n()

  function isFileField(prop: SchemaProperty): boolean {
    return isFileSchemaProperty(prop) || prop.type === 'file' || prop.format === 'uri' || prop.format === 'file'
  }

  function isStructuredField(prop: SchemaProperty): boolean {
    return prop.type === 'object' || (prop.type === 'array' && !prop.items?.enum)
  }

  function structuredEditorValue(key: string, prop: SchemaProperty): string {
    const value = props.formState[key]
    if (typeof value === 'string') return value
    if (value !== undefined) return JSON.stringify(value, null, 2)
    return prop.default === undefined ? '' : JSON.stringify(prop.default, null, 2)
  }

  function updateStructuredValue(key: string, value: string) {
    props.formState[key] = value
  }

  const visibleProperties = computed(() => {
    const hidden = new Set(props.hiddenFieldKeys)
    return Object.fromEntries(
      Object.entries(props.schema.properties).filter(([key]) => !hidden.has(key))
    )
  })

  function fileAccept(key: string, prop: SchemaProperty): string | undefined {
    return props.getFileAccept?.(key, prop) ?? prop.accept
  }

  function fileFieldSatisfied(key: string, prop: SchemaProperty): boolean {
    return Boolean(
      props.isFileFieldSatisfied?.(key, prop) ||
      props.formState[key] ||
      props.fileList[key]?.length ||
      props.selectedArtifacts[key]
    )
  }

  function fieldRules(key: string, prop: SchemaProperty): Rule[] {
    const rules: Rule[] = []

    if (props.schema.required?.includes(key)) {
      if (isFileField(prop)) {
        rules.push({
          validator: async () => {
            if (fileFieldSatisfied(key, prop)) {
              return Promise.resolve()
            }
            return Promise.reject(new Error(props.requiredMessage(prop.title ?? key)))
          },
          trigger: 'change',
        })
      } else {
        rules.push({ required: true, message: props.requiredMessage(prop.title ?? key) })
      }
    }

    if (isStructuredField(prop)) {
      rules.push({
        validator: async (_rule, value: unknown) => {
          if (value === undefined || value === null || value === '') {
            return Promise.resolve()
          }
          if (typeof value !== 'string') {
            return Promise.resolve()
          }
          try {
            const parsed = JSON.parse(value)
            const validShape = prop.type === 'object'
              ? parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
              : Array.isArray(parsed)
            return validShape
              ? Promise.resolve()
              : Promise.reject(new Error(t(prop.type === 'object' ? 'tools.parameterJsonObject' : 'tools.parameterJsonArray')))
          } catch {
            return Promise.reject(new Error(t('tools.parameterJsonInvalid')))
          }
        },
        trigger: 'change',
      })
    }

    if (prop.minLength) {
      rules.push({ min: prop.minLength, message: props.minLengthMessage(prop.minLength) })
    }
    if (prop.maxLength) {
      rules.push({ max: prop.maxLength, message: props.maxLengthMessage(prop.maxLength) })
    }

    return rules
  }
</script>
