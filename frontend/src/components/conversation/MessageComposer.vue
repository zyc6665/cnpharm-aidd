<template>
  <div class="composer-shell">
    <div class="composer">
      <div v-if="proteinArtifactOptions.length" class="artifact-picker">
        <label for="protein-artifact-select">蛋白结构 Artifact</label>
        <select
          id="protein-artifact-select"
          data-testid="protein-artifact-select"
          :disabled="disabled"
          :value="proteinArtifactVersionId || ''"
          @change="selectProteinArtifact"
        >
          <option value="">不指定蛋白结构</option>
          <option
            v-for="option in proteinArtifactOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </div>
      <textarea
        v-model="draft"
        rows="2"
        :disabled="disabled"
        :placeholder="editing ? '修改消息后发送以创建新分支...' : '描述研究目标，或引用项目中的蛋白结构...'"
        @keydown.enter.exact.prevent="submit"
      />
      <div class="composer-actions">
        <button type="button" data-testid="stop-run" title="停止运行" @click="$emit('stop')"><StopOutlined /></button>
        <button type="button" data-testid="regenerate-run" title="重新生成" @click="$emit('regenerate')"><RedoOutlined /></button>
        <button v-if="editing" type="button" title="取消编辑" @click="cancelEdit"><CloseOutlined /></button>
        <button type="button" class="send" :title="editing ? '创建分支' : '发送'" :disabled="!draft.trim() || disabled" @click="submit"><SendOutlined /></button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { CloseOutlined, RedoOutlined, SendOutlined, StopOutlined } from '@ant-design/icons-vue'

interface ProteinArtifactOption {
  value: string
  label: string
}

const props = withDefaults(defineProps<{
  disabled?: boolean
  editing?: boolean
  initialText?: string
  proteinArtifactOptions?: ProteinArtifactOption[]
  proteinArtifactVersionId?: string
}>(), {
  proteinArtifactOptions: () => []
})
const emit = defineEmits<{
  submit: [text: string]
  stop: []
  regenerate: []
  cancelEdit: []
  'update:proteinArtifactVersionId': [versionId: string | undefined]
}>()
const draft = ref('')

watch(() => props.initialText, text => {
  if (props.editing) draft.value = text || ''
}, { immediate: true })

function submit() {
  const text = draft.value.trim()
  if (!text) return
  emit('submit', text)
  draft.value = ''
}

function cancelEdit() {
  draft.value = ''
  emit('cancelEdit')
}

function selectProteinArtifact(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('update:proteinArtifactVersionId', value || undefined)
}
</script>

<style scoped lang="less">
.composer-shell { position: absolute; left: 0; right: 0; bottom: 0; padding: 16px 24px 22px; background: linear-gradient(to bottom, transparent, @bg-body 22%); pointer-events: none; }
.composer { width: min(780px, 100%); margin: 0 auto; border: 1px solid @border-color; border-radius: 8px; background: @bg-surface; box-shadow: @shadow-md; overflow: hidden; pointer-events: auto; }
.artifact-picker { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-bottom: 1px solid @border-color-light; color: @text-secondary; font-size: 12px; }
.artifact-picker label { flex: 0 0 auto; color: @text-tertiary; }
.artifact-picker select { min-width: 0; flex: 1; height: 30px; border: 1px solid @border-color; border-radius: 5px; background: @bg-body; color: @text-primary; }
textarea { display: block; width: 100%; min-height: 68px; resize: none; padding: 13px 14px 8px; border: 0; outline: 0; background: transparent; color: @text-primary; font: inherit; line-height: 1.5; }
.composer-actions { display: flex; justify-content: flex-end; gap: 5px; padding: 6px 8px 8px; }
.composer-actions button { display: grid; place-items: center; width: 30px; height: 30px; border: 0; border-radius: 5px; background: transparent; color: @text-secondary; cursor: pointer; }
.composer-actions button:hover { background: @bg-hover; color: @text-primary; }
.composer-actions .send { background: @accent-color; color: white; }
.composer-actions button:disabled { opacity: .45; cursor: not-allowed; }
</style>
