<template>
  <section class="message-timeline" data-testid="message-timeline" aria-label="研究消息">
    <article v-for="message in messages" :key="message.id" :class="['message-row', `role-${message.role}`]">
      <div class="message-role">{{ roleLabel(message.role) }}</div>
      <div class="message-body">
        <template v-for="(block, index) in message.content" :key="index">
          <p v-if="block.type === 'text'">{{ block.text }}</p>
          <PlanApprovalCard
            v-else-if="block.type === 'approval_ref'"
            :plan="block"
            :can-run="canRun"
            @approve="$emit('approve', $event)"
            @reject="$emit('reject', $event)"
          />
          <a v-else-if="block.type === 'citation' && block.url" :href="String(block.url)" target="_blank" rel="noopener noreferrer">
            {{ block.title || '引用来源' }}
          </a>
          <span v-else-if="block.type === 'artifact_ref'" class="artifact-ref">{{ block.title || '研究产物' }}</span>
        </template>
        <button
          v-if="message.role === 'user'"
          type="button"
          class="branch-button"
          data-testid="branch-message"
          title="编辑并创建新分支"
          @click="$emit('branch', message)"
        ><BranchesOutlined /> 编辑并分支</button>
      </div>
    </article>
    <a-empty v-if="!messages.length" description="发送研究目标以开始" />
  </section>
</template>

<script setup lang="ts">
import { BranchesOutlined } from '@ant-design/icons-vue'
import PlanApprovalCard from './PlanApprovalCard.vue'
import type { ConversationMessage } from '@/types/conversations'

defineProps<{ messages: ConversationMessage[]; canRun: boolean }>()
defineEmits<{
  approve: [planId: string]
  reject: [planId: string]
  branch: [message: ConversationMessage]
}>()

const roleLabel = (role: ConversationMessage['role']) => ({ user: '你', assistant: '研究助手', system: '系统', tool: '工具' })[role]
</script>

<style scoped lang="less">
.message-timeline { width: min(780px, 100%); margin: 0 auto; padding: 24px 28px 160px; }
.message-row { display: grid; grid-template-columns: 76px minmax(0, 1fr); min-height: 68px; padding: 18px 0; border-bottom: 1px solid @border-color-light; }
.message-role { padding-top: 2px; font-size: 12px; font-weight: 600; color: @text-tertiary; }
.message-body { min-width: 0; color: @text-primary; line-height: 1.7; overflow-wrap: anywhere; }
.message-body p { margin: 0 0 8px; white-space: pre-wrap; }
.artifact-ref { display: inline-flex; padding: 4px 8px; background: @bg-hover; border-radius: 4px; }
.branch-button { display: flex; align-items: center; gap: 5px; margin-top: 8px; padding: 3px 0; border: 0; background: transparent; color: @text-tertiary; cursor: pointer; }
.branch-button:hover { color: @accent-color; }
@media (max-width: @screen-sm) { .message-timeline { padding: 16px 16px 150px; } .message-row { grid-template-columns: 1fr; gap: 6px; } }
</style>
