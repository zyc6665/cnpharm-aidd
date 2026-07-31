<template>
  <aside class="conversation-sidebar" data-testid="conversation-sidebar">
    <div class="sidebar-heading">
      <strong>研究会话</strong>
      <button type="button" title="新建会话" aria-label="新建会话" @click="$emit('create')">
        <PlusOutlined />
      </button>
    </div>
    <nav aria-label="项目会话">
      <button
        v-for="conversation in conversations"
        :key="conversation.id"
        type="button"
        :class="{ active: conversation.id === activeId }"
        @click="$emit('select', conversation.id)"
      >
        <MessageOutlined />
        <span>{{ conversation.title }}</span>
      </button>
    </nav>
    <a-empty v-if="!conversations.length" description="暂无会话" />
  </aside>
</template>

<script setup lang="ts">
import { MessageOutlined, PlusOutlined } from '@ant-design/icons-vue'
import type { ProjectConversation } from '@/types/conversations'

defineProps<{ conversations: ProjectConversation[]; activeId: string | null }>()
defineEmits<{ select: [conversationId: string]; create: [] }>()
</script>

<style scoped lang="less">
.conversation-sidebar { min-width: 0; padding: 16px 10px; border-right: 1px solid @border-color; background: @bg-surface; }
.sidebar-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 8px 12px; }
.sidebar-heading button { width: 28px; height: 28px; border: 0; background: transparent; color: @text-secondary; cursor: pointer; }
nav { display: grid; gap: 3px; }
nav button { display: flex; align-items: center; gap: 8px; width: 100%; min-width: 0; height: 36px; padding: 0 10px; border: 0; border-radius: 6px; background: transparent; color: @text-secondary; cursor: pointer; text-align: left; }
nav button:hover, nav button.active { background: @bg-hover; color: @text-primary; }
nav span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
