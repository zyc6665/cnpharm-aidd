<template>
  <template v-for="(prop, key) in schema.properties" :key="key">
    <a-form-item
      :name="key"
      :label="prop.title"
      :rules="fieldRules(String(key), prop)"
      :extra="prop.description"
    >
      <!-- string -->
      <a-input
        v-if="prop.type === 'string' && !prop.format && !prop.enum"
        v-model:value="formState[key]"
        :placeholder="prop.description"
      />
      <!-- textarea -->
      <a-textarea
        v-else-if="prop.type === 'string' && (prop.format === 'textarea' || prop.format === 'fasta' || prop.format === 'pdb')"
        v-model:value="formState[key]"
        :placeholder="prop.description"
        :rows="prop.format === 'fasta' || prop.format === 'pdb' ? 8 : 4"
        :class="{ 'code-input': prop.format === 'fasta' || prop.format === 'pdb' }"
      />
      <!-- number -->
      <a-input-number
        v-else-if="prop.type === 'number'"
        v-model:value="formState[key]"
        :min="prop.minimum"
        :max="prop.maximum"
        style="width: 100%"
      />
      <!-- boolean -->
      <a-switch
        v-else-if="prop.type === 'boolean'"
        v-model:checked="formState[key]"
      />
      <!-- single enum -->
      <a-select
        v-else-if="prop.type === 'select' || (prop.enum && prop.type !== 'array')"
        v-model:value="formState[key]"
        :placeholder="prop.description"
      >
        <a-select-option v-for="opt in prop.enum" :key="String(opt)" :value="opt">
          {{ opt }}
        </a-select-option>
      </a-select>
      <!-- multi enum -->
      <a-select
        v-else-if="prop.type === 'array' && prop.items?.enum"
        v-model:value="formState[key]"
        mode="multiple"
        :placeholder="prop.description"
      >
        <a-select-option v-for="opt in prop.items.enum" :key="String(opt)" :value="opt">
          {{ opt }}
        </a-select-option>
      </a-select>
      <!-- file / artifact -->
      <ArtifactFilePicker
        v-else-if="isFileField(prop)"
        :upload-list="fileList[String(key)] ?? []"
        :selected-artifact="selectedArtifacts[String(key)] ?? null"
        :accept="prop.accept"
        :allow-artifacts="allowArtifacts"
        :current-tool-id="toolId"
        :current-tool-slug="toolSlug"
        :preferred-group-id="preferredGroupId"
        :preferred-tool-slug="preferredToolSlug"
        :external-selection-path="externalSelectionPath"
        @update:upload-list="(files) => emit('update:fileList', String(key), files)"
        @update:selected-artifact="(artifact) => emit('update:selectedArtifact', String(key), artifact)"
      />
    </a-form-item>
  </template>
</template>

<script setup lang="ts">
import type { Rule } from 'ant-design-vue/es/form'
import ArtifactFilePicker from '@/components/tools/ArtifactFilePicker.vue'
import type { ArtifactFile, SchemaProperty, ToolSchema } from '@/types/models'
import { isFileSchemaProperty } from '@/views/tools/detail-schema'
import type { UploadFile } from 'ant-design-vue'
import type { WorkflowArtifactSelectionPath } from '@/workflow/artifact-hierarchy'

const props = defineProps<{
  schema: ToolSchema
  formState: Record<string, unknown>
  fileList: Record<string, UploadFile[]>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  allowArtifacts?: boolean
  toolId?: string
  toolSlug?: string
  preferredGroupId?: string
  preferredToolSlug?: string
  externalSelectionPath?: WorkflowArtifactSelectionPath | null
}>()

const emit = defineEmits<{
  'update:fileList': [key: string, files: UploadFile[]]
  'update:selectedArtifact': [key: string, artifact: ArtifactFile | null]
}>()

function isFileField(prop: SchemaProperty): boolean {
  return isFileSchemaProperty(prop) || prop.type === 'file' || prop.format === 'uri' || prop.format === 'file'
}

function fieldRules(key: string, prop: SchemaProperty): Rule[] {
  const rules: Rule[] = []

  if (props.schema.required?.includes(key)) {
    if (isFileField(prop)) {
      rules.push({
        validator: async () => {
          if (props.fileList[key]?.length || props.selectedArtifacts[key]) {
            return Promise.resolve()
          }
          return Promise.reject(new Error(`${prop.title} is required`))
        },
        trigger: 'change',
      })
    } else {
      rules.push({ required: true, message: `${prop.title} is required` })
    }
  }

  if (prop.minLength) {
    rules.push({ min: prop.minLength, message: `Min length: ${prop.minLength}` })
  }
  if (prop.maxLength) {
    rules.push({ max: prop.maxLength, message: `Max length: ${prop.maxLength}` })
  }

  return rules
}
</script>
