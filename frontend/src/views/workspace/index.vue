<template>
  <div class="workspace-page">
    <header class="ws-header">
      <div class="ws-greeting">
        <h1 class="ws-title">{{ greeting }}</h1>
        <p class="ws-date">{{ today }}</p>
      </div>
      <div class="ws-actions">
        <a-button type="primary" @click="$router.push('/tools')">
          <PlusOutlined /> {{ t('command.newTask') }}
        </a-button>
      </div>
    </header>

    <div class="ws-grid">
      <!-- 最近任务 -->
      <section class="ws-section ws-recent">
        <div class="ws-section-head">
          <h2 class="ws-section-title">{{ t('workspace.recentTasks') }}</h2>
          <router-link to="/tasks" class="ws-section-link">{{ t('common.more') }}</router-link>
        </div>
        <div v-if="recentTasks.length" class="ws-task-list">
          <div v-for="task in recentTasks" :key="task.id" class="ws-task-card" @click="$router.push(`/tasks/${task.id}`)">
            <span class="ws-task-status" :class="`status-${task.status}`"></span>
            <div class="ws-task-info">
              <strong>{{ task.name }}</strong>
              <span>{{ task.tool_name }}</span>
            </div>
            <span class="ws-task-time">{{ task.created_at }}</span>
          </div>
        </div>
        <div v-else class="ws-empty">
          <ExperimentOutlined class="ws-empty-icon" />
          <p>{{ t('workspace.noRecentTasks') }}</p>
          <a-button type="link" @click="$router.push('/tools')">{{ t('workspace.startFirst') }}</a-button>
        </div>
      </section>

      <!-- 快速操作 -->
      <section class="ws-section ws-quick">
        <div class="ws-section-head">
          <h2 class="ws-section-title">{{ t('workspace.quickActions') }}</h2>
        </div>
        <div class="ws-quick-grid">
          <button class="ws-quick-card" @click="$router.push('/workflow')">
            <ApartmentOutlined class="ws-quick-icon" />
            <span>{{ t('workspace.newWorkflow') }}</span>
          </button>
          <button class="ws-quick-card" @click="$router.push('/tools')">
            <AppstoreOutlined class="ws-quick-icon" />
            <span>{{ t('workspace.browseTools') }}</span>
          </button>
          <button class="ws-quick-card" @click="$router.push('/tasks')">
            <ExperimentOutlined class="ws-quick-icon" />
            <span>{{ t('workspace.viewTasks') }}</span>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  PlusOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
} from '@ant-design/icons-vue'

const { t } = useI18n()
const router = useRouter()

const recentTasks = ref<any[]>([])

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return t('workspace.goodMorning')
  if (hour < 18) return t('workspace.goodAfternoon')
  return t('workspace.goodEvening')
})

const today = computed(() => {
  return new Date().toLocaleDateString(
    document.documentElement.lang === 'zh' ? 'zh-CN' : 'en-US',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' },
  )
})

onMounted(async () => {
  // TODO: 加载最近任务
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workspace-page {
  max-width: 960px;
  margin: 0 auto;
  padding: @spacing-xxl @spacing-lg;
}

.ws-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: @spacing-lg;
  margin-bottom: @spacing-xl;
  flex-wrap: wrap;
}

.ws-title {
  font-size: @font-size-xxl;
  font-weight: @font-weight-bold;
  color: @text-primary;
  margin: 0;
  letter-spacing: -0.03em;
  line-height: @line-height-tight;
}

.ws-date {
  color: @text-tertiary;
  font-size: @font-size-sm;
  margin: @spacing-xs 0 0;
}

.ws-grid {
  display: flex;
  flex-direction: column;
  gap: @spacing-xl;
}

.ws-section {
  .card();
  padding: @spacing-lg;
}

.ws-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: @spacing-md;
}

.ws-section-title {
  font-size: @font-size-md;
  font-weight: @font-weight-semibold;
  color: @text-primary;
  margin: 0;
}

.ws-section-link {
  color: @text-tertiary;
  font-size: @font-size-sm;
  text-decoration: none;

  &:hover {
    color: @accent-color;
  }
}

.ws-task-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ws-task-card {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-sm @spacing-md;
  border-radius: @border-radius-md;
  cursor: pointer;
  transition: background @transition-fast;

  &:hover {
    background: @bg-hover;
  }
}

.ws-task-status {
  width: 8px;
  height: 8px;
  border-radius: @border-radius-round;
  flex-shrink: 0;

  &.status-completed { background: @success-color; }
  &.status-running { background: @accent-color; animation: skeletonPulse 1.5s ease-in-out infinite; }
  &.status-failed { background: @error-color; }
  &.status-pending { background: @warning-color; }
}

.ws-task-info {
  flex: 1;
  min-width: 0;

  strong {
    display: block;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    color: @text-primary;
    .text-ellipsis();
  }

  span {
    font-size: @font-size-xs;
    color: @text-tertiary;
  }
}

.ws-task-time {
  font-size: @font-size-xs;
  color: @text-tertiary;
  white-space: nowrap;
}

.ws-empty {
  text-align: center;
  padding: @spacing-xl 0;
  color: @text-tertiary;

  p {
    margin: @spacing-sm 0;
    font-size: @font-size-sm;
  }
}

.ws-empty-icon {
  font-size: 32px;
  color: @text-disabled;
}

.ws-quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: @spacing-sm;
}

.ws-quick-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-lg;
  background: @bg-hover;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  color: @text-secondary;
  font-size: @font-size-sm;
  font-family: @font-family;
  cursor: pointer;
  transition: all @transition-fast;

  &:hover {
    background: @accent-color-light;
    border-color: @accent-color-border;
    color: @text-primary;
  }
}

.ws-quick-icon {
  font-size: 24px;
  color: @accent-color;
}
</style>
