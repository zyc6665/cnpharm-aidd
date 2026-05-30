<template>
  <section class="workflow-column groups-column">
    <div class="column-card">
      <h2 class="column-title">{{ t('workflow.columns.groups') }}</h2>
      <p class="column-subtitle">{{ t('workflow.columns.groupsHint') }}</p>

      <div v-if="groups.length > 0" class="group-list">
        <button
          v-for="group in groups"
          :key="group.id"
          type="button"
          :class="['group-card', { 'group-card-active': group.id === activeGroupId }]"
          @click="selectGroup(group.id)"
        >
          <div class="group-copy">
            <h3 class="group-title">{{ group.name }}</h3>
            <p class="group-desc">
              {{ group.description || t('workflow.groups.descriptionFallback') }}
            </p>
            <div class="group-meta">
              <a-tag color="blue">
                {{ t('workflow.groups.toolCount', { count: group.tools.length }) }}
              </a-tag>
              <a-tag v-if="getRecommendedCount(group) > 0" color="gold">
                {{ t('workflow.groups.recommendedCount', { count: getRecommendedCount(group) }) }}
              </a-tag>
            </div>
          </div>
        </button>
      </div>

      <a-empty v-else :description="t('workflow.groups.empty')" />
    </div>
  </section>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import type { WorkbenchGroup } from '@/types/models'

  const props = defineProps<{
    groups: WorkbenchGroup[]
    activeGroupId?: string | null
  }>()

  const emit = defineEmits<{
    select: [groupId: string]
  }>()

  const { t } = useI18n()

  function getRecommendedCount(group: WorkbenchGroup): number {
    return group.tools.filter((tool) => tool.is_recommended).length
  }

  function selectGroup(groupId: string) {
    emit('select', groupId)
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-column {
    min-width: 0;
  }

  .column-card {
    .card();
    height: 100%;
    border-color: #e8edf5;

    @media (min-width: @screen-md) {
      position: sticky;
      top: @spacing-lg;
      max-height: calc(100vh - 112px);
      overflow-y: auto;
    }
  }

  .column-title {
    font-size: @font-size-xl;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .column-subtitle {
    color: @text-color-light-secondary;
    margin-bottom: @spacing-lg;
  }

  .group-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .group-card {
    width: 100%;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
    cursor: pointer;
    text-align: left;
    transition: border-color 0.2s ease, transform 0.2s ease;

    &:hover,
    &:focus-visible {
      border-color: @accent-color;
      transform: translateY(-1px);
    }

    &:focus-visible {
      outline: 3px solid rgba(24, 144, 255, 0.28);
      outline-offset: 3px;
    }
  }

  .group-card-active {
    border-color: @accent-color;
    box-shadow: inset 3px 0 0 @accent-color, @shadow-sm;
  }

  .group-copy {
    min-width: 0;
  }

  .group-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .group-desc {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .group-meta {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
  }
</style>
