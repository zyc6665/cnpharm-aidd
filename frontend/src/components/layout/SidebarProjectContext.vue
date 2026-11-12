<template>
  <div class="project-context" data-testid="sidebar-project-context">
    <template v-if="!collapsed">
      <div class="project-context__head">
        <span class="project-context__title">{{ t('projectNav.title') }}</span>
        <router-link to="/workspace" class="project-context__all" data-testid="sidebar-project-all">
          {{ t('projectNav.allProjects') }}
        </router-link>
      </div>
      <div class="project-context__row">
        <a-select
          v-model:value="selectedId"
          class="project-context__select"
          show-search
          option-filter-prop="label"
          :loading="loading"
          :options="projectOptions"
          :placeholder="t('projectNav.placeholder')"
          data-testid="sidebar-project-switch"
          @change="handleChange"
        />
        <router-link
          v-if="activeProjectId && !atProjectOverview"
          :to="`/projects/${activeProjectId}`"
          class="project-context__open"
          :title="t('projectNav.overview')"
          data-testid="sidebar-project-overview"
        >
          <ArrowRightOutlined />
        </router-link>
      </div>
      <p v-if="!activeProjectId" class="project-context__hint">{{ t('projectNav.hint') }}</p>
    </template>

    <router-link
      v-else
      :to="activeProjectId ? `/projects/${activeProjectId}` : '/workspace'"
      class="project-context__collapsed"
      :title="t('projectNav.title')"
      data-testid="sidebar-project-collapsed"
    >
      <FolderOpenOutlined />
    </router-link>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { ArrowRightOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
  import { useActiveProject } from '@/composables/useActiveProject'

  const props = withDefaults(defineProps<{ collapsed?: boolean }>(), { collapsed: false })

  const route = useRoute()
  const { t } = useI18n()
  const { loading, activeProjectId, projectOptions, ensureProjects, switchProject } = useActiveProject()

  const selectedId = ref<string>(activeProjectId.value)

  watch(activeProjectId, value => {
    selectedId.value = value
  })

  /**
   * 这里只放「换项目 + 回项目总览」。
   *
   * 项目内的横向导航（项目总览 / 靶点与结构 / …）几乎所有项目页面自己都会渲染一份，
   * 侧边栏再列一遍就是把同一份清单画两次；缺的那份能力是「在任何页面都能回到某个项目」，
   * 所以只保留切换器，并给一个直达总览的箭头。
   */
  const currentProjectPath = computed(() =>
    activeProjectId.value ? `/projects/${activeProjectId.value}` : ''
  )

  async function handleChange(value: unknown): Promise<void> {
    if (typeof value !== 'string') return
    await switchProject(value)
  }

  onMounted(() => {
    if (!props.collapsed) void ensureProjects()
  })

  watch(
    () => props.collapsed,
    collapsedState => {
      if (!collapsedState) void ensureProjects()
    }
  )

  /** 当前已经在项目总览时，箭头没有意义（避免点一下原地不动）。 */
  const atProjectOverview = computed(
    () => Boolean(currentProjectPath.value) && route.path === currentProjectPath.value
  )

</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .project-context {
    padding: 8px 12px 12px;
    border-bottom: 1px solid @border-color-split;
    margin-bottom: 8px;
  }

  .project-context__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }

  .project-context__title {
    color: @text-tertiary;
    font-size: 12px;
    letter-spacing: 0.04em;
  }

  .project-context__all {
    color: @primary-color;
    font-size: 12px;
  }

  .project-context__row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .project-context__select {
    flex: 1;
    min-width: 0;
  }

  .project-context__open {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: 1px solid @border-color;
    border-radius: 6px;
    color: @text-secondary;
  }

  .project-context__open:hover {
    border-color: @primary-color;
    color: @primary-color;
  }

  .project-context__hint {
    margin: 8px 0 0;
    color: @text-tertiary;
    font-size: 12px;
    line-height: 1.5;
  }

  .project-context__collapsed {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 6px 0;
    color: @text-secondary;
    font-size: 18px;
  }
</style>
