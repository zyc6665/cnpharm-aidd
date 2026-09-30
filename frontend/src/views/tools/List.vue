<template>
  <div class="tools-page">
    <div class="container">
      <AppPageHeader :title="t('tools.title')" :subtitle="t('tools.subtitle')" />

      <div class="workflow-entry-card">
        <div class="workflow-entry-copy">
          <h2 class="workflow-entry-title">{{ t('workflow.title') }}</h2>
          <p class="workflow-entry-desc">{{ t('workflow.subtitle') }}</p>
        </div>
        <router-link to="/workflow">
          <a-button type="primary" size="large">
            {{ t('workflow.entry.tools') }}
          </a-button>
        </router-link>
      </div>

      <!-- 视图切换标签 -->
      <div class="view-tabs">
        <a-radio-group v-model:value="currentView" button-style="solid" size="large" @change="handleViewChange">
          <a-radio-button value="public">
            <AppstoreOutlined />
            {{ t('tools.publicTools') }}
          </a-radio-button>
          <a-radio-button v-if="isLoggedIn" value="favorites">
            <HeartOutlined />
            {{ t('tools.favorites') }}
          </a-radio-button>
        </a-radio-group>
      </div>

      <!-- 搜索和筛选 -->
      <AppFilterBar>
        <a-input-search
          v-model:value="searchKeyword"
          :placeholder="t('tools.search')"
          class="tool-search-input"
          size="large"
          allow-clear
          @search="handleSearch"
        />
        <a-select
          v-model:value="selectedCategory"
          :placeholder="t('tools.allCategories')"
          class="tool-filter-select"
          size="large"
          allow-clear
          @change="handleCategoryChange"
        >
          <a-select-option v-for="cat in categories" :key="cat.name" :value="cat.name">
            <span class="category-option">
              {{ cat.name }}
              <span v-if="cat.count" class="category-count">({{ cat.count }})</span>
            </span>
          </a-select-option>
        </a-select>
        <a-select
          v-model:value="selectedTag"
          :placeholder="t('tools.filterTags')"
          class="tool-filter-select"
          size="large"
          allow-clear
          @change="handleTagChange"
        >
          <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.name">
            <a-tag :color="tag.color" size="small">{{ tag.name }}</a-tag>
          </a-select-option>
        </a-select>

        <a-dropdown>
          <a-button size="large">
            <SortAscendingOutlined />
            {{ sortLabel }}
            <DownOutlined />
          </a-button>
          <template #overlay>
            <a-menu @click="handleSortChange">
              <a-menu-item key="popular">{{ t('tools.sortPopular') }}</a-menu-item>
              <a-menu-item key="newest">{{ t('tools.sortNewest') }}</a-menu-item>
              <a-menu-item key="name">{{ t('tools.sortName') }}</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </AppFilterBar>

    <div class="tools-results-summary">
      <span>{{ currentViewLabel }}</span>
      <span>{{ t('common.totalItems', { total: displayTotal }) }}</span>
      <span class="tools-results-sort">{{ sortLabel }}</span>
      <a-button
        v-if="hasActiveFilters"
        type="link"
        size="small"
        class="clear-filters-button"
        @click="resetFilters"
      >
        {{ t('common.reset') }}
      </a-button>
    </div>

      <!-- 工具列表 -->
      <SkeletonList v-if="loading" :count="8" />
        <div v-else-if="displayTools.length" class="tools-grid">
          <a-row :gutter="[24, 24]">
            <a-col v-for="tool in displayTools" :key="tool.id" :xs="24" :sm="12" :lg="8" :xl="6">
              <div
                class="tool-card"
                role="button"
                tabindex="0"
                :aria-label="tool.name"
                @click="goToDetail(tool.id)"
                @keydown.enter="goToDetail(tool.id)"
                @keydown.space.prevent="goToDetail(tool.id)"
              >
                <div class="tool-header">
                  <div class="tool-icon">
                    <span v-if="tool.icon">{{ tool.icon }}</span>
                    <ToolOutlined v-else />
                  </div>
                </div>
                <h3 class="tool-name">{{ tool.name }}</h3>
                <p class="tool-desc">{{ tool.description }}</p>

                <div class="tool-tags" v-if="tool.tags?.length">
                  <a-tag
                    v-for="tag in tool.tags.slice(0, 3)"
                    :key="tag.id"
                    :color="tag.color"
                    size="small"
                  >
                    {{ tag.name }}
                  </a-tag>
                </div>
                <div class="tool-footer">
                  <div class="tool-stats">
                    <span class="tool-stat">
                      <PlayCircleOutlined />
                      {{ formatNumber(tool.usage_count) }}
                    </span>
                    <span class="tool-stat">
                      <EyeOutlined />
                      {{ formatNumber(tool.view_count) }}
                    </span>
                    <span class="tool-stat">
                      <HeartFilled v-if="tool.is_favorited" class="favorited" />
                      <HeartOutlined v-else />
                      {{ formatNumber(tool.favorite_count) }}
                    </span>
                  </div>
                  <a-button
                    type="primary"
                    size="small"
                    class="tool-use-button"
                    @click.stop="goToDetail(tool.id)"
                  >
                    <PlayCircleOutlined />
                    {{ t('tools.useNow') }}
                  </a-button>
                </div>
              </div>
            </a-col>
          </a-row>
        </div>
        <a-empty v-else-if="hasActiveFilters" :description="t('tools.noMatchingTools')">
          <a-button type="primary" @click="resetFilters">
            {{ t('common.reset') }}
          </a-button>
        </a-empty>
        <a-empty v-else :description="t('tools.noTools')" />

      <!-- 分页 -->
      <div v-if="displayTotal > pageSize" class="pagination">
        <a-pagination
          v-model:current="currentPage"
          :total="displayTotal"
          :page-size="pageSize"
          :show-total="(total: number) => t('common.totalItems', { total })"
          show-quick-jumper
          show-size-changer
          :page-size-options="['12', '24', '48']"
          @change="handlePageChange"
          @show-size-change="handlePageSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import AppFilterBar from '@/components/common/AppFilterBar.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import {
    buildToolListParams,
    formatToolCount,
    getToolSortLabelKey,
    getToolViewLabelKey
  } from '@/domain/tools'
  import {
    ToolOutlined,
    PlayCircleOutlined,
    HeartOutlined,
    HeartFilled,
    EyeOutlined,
    SortAscendingOutlined,
    DownOutlined,
    AppstoreOutlined,
  } from '@ant-design/icons-vue'
  import { useToolsStore, useUserStore } from '@/stores'
  import type { ToolView } from '@/types/models'

  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()

  const searchKeyword = ref('')
  const selectedCategory = ref<string | undefined>()
  const selectedTag = ref<string | undefined>()
  const currentPage = ref(1)
  const pageSize = ref(12)
  const sortBy = ref('popular')
  const currentView = ref<ToolView>('public')

  const loading = computed(() => toolsStore.loading)
  const isLoggedIn = computed(() => userStore.isLoggedIn)

  const displayTools = computed(() => toolsStore.tools)
  const displayTotal = computed(() => toolsStore.total)

  const categories = computed(() => toolsStore.categories)
  const tags = computed(() => toolsStore.tags)

  const sortLabel = computed(() => t(getToolSortLabelKey(sortBy.value)))
  const currentViewLabel = computed(() => t(getToolViewLabelKey(currentView.value)))
  const hasActiveFilters = computed(() => Boolean(
    searchKeyword.value.trim() || selectedCategory.value || selectedTag.value
  ))

  const formatNumber = formatToolCount

  const fetchData = async () => {
    await toolsStore.fetchTools(
      buildToolListParams({
        view: currentView.value,
        searchKeyword: searchKeyword.value,
        // category: selectedCategory.value is normalized by buildToolListParams.
        selectedCategory: selectedCategory.value,
        selectedTag: selectedTag.value,
        currentPage: currentPage.value,
        pageSize: pageSize.value,
        sortBy: sortBy.value
      })
    )
  }

  const handleViewChange = () => {
    currentPage.value = 1
    fetchData()
  }

  const handleSearch = () => {
    currentPage.value = 1
    fetchData()
  }

  const handleCategoryChange = () => {
    currentPage.value = 1
    fetchData()
  }

  const handleTagChange = () => {
    currentPage.value = 1
    fetchData()
  }

  const handleSortChange = ({ key }: { key: string }) => {
    sortBy.value = key
    currentPage.value = 1
    fetchData()
  }

  const handlePageChange = (page: number) => {
    currentPage.value = page
    fetchData()
  }

  const handlePageSizeChange = (_current: number, size: number) => {
    pageSize.value = size
    currentPage.value = 1
    fetchData()
  }

  const resetFilters = () => {
    searchKeyword.value = ''
    selectedCategory.value = undefined
    selectedTag.value = undefined
    currentPage.value = 1
    fetchData()
  }

  const goToDetail = (id: string) => {
    router.push(`/tools/${id}`)
  }

  onMounted(async () => {
    await Promise.all([
      fetchData(),
      toolsStore.fetchCategories(),
      toolsStore.fetchTags()
    ])
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tools-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .workflow-entry-card {
    .card();
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-lg;
    margin-bottom: @spacing-xl;

    @media (max-width: @screen-md) {
      flex-direction: column;
      align-items: flex-start;
    }
  }

  .workflow-entry-copy {
    flex: 1;
  }

  .workflow-entry-title {
    font-size: @font-size-xl;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .workflow-entry-desc {
    color: @text-color-light-secondary;
    margin: 0;
  }

  .view-tabs {
    display: flex;
    justify-content: center;
    gap: @spacing-lg;
    margin-bottom: @spacing-xl;
    flex-wrap: wrap;
  }

  .category-option {
    display: flex;
    align-items: center;
    gap: @spacing-xs;

    .category-count {
      color: @text-color-light-tertiary;
      font-size: @font-size-sm;
    }
  }

  .tool-search-input {
    width: min(400px, 100%);
  }

  .tool-filter-select {
    width: 200px;
  }

  .tools-results-summary {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-sm @spacing-md;
    margin: -@spacing-md 0 @spacing-lg;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .tools-results-sort {
    color: @text-color-light-tertiary;
  }

  .clear-filters-button {
    padding: 0;
  }

  .tools-grid {
    margin-bottom: @spacing-xl;
  }

  .tool-card {
    .card();
    position: relative;
    overflow: hidden;
    min-height: 234px;
    cursor: pointer;
    height: 100%;
    display: flex;
    flex-direction: column;
    border-radius: @border-radius-md;
    background: linear-gradient(180deg, @bg-card-light 0%, @bg-color-light 100%);

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, @accent-color, @primary-color);
      opacity: 0;
      transition: opacity @transition-base;
    }

    &:hover,
    &:focus-visible {
      transform: translateY(-4px);
      border-color: @accent-color-border;
      box-shadow: @shadow-md;

      &::before {
        opacity: 1;
      }
    }

    &:focus-visible {
      outline: 3px solid @accent-color-border;
      outline-offset: 3px;
    }
  }

  .tool-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: @spacing-md;
  }

  .tool-icon {
    width: 48px;
    height: 48px;
    border-radius: @border-radius-md;
    background: linear-gradient(135deg, @accent-color-light, @primary-color-light);
    border: 1px solid @accent-color-border;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    color: @accent-color;
  }

  .tool-name {
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-sm;
    .text-ellipsis();
  }

  .tool-desc {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
    flex: 1;
    .text-ellipsis-lines(2);
  }

  .tool-tags {
    display: flex;
    gap: @spacing-xs;
    flex-wrap: wrap;
    margin-top: @spacing-sm;
    margin-bottom: @spacing-sm;
  }

  .tool-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: @spacing-md;
    padding-top: @spacing-md;
    border-top: 1px solid @border-color-light;
  }

  .tool-stats {
    display: flex;
    gap: @spacing-md;
  }

  .tool-stat {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;

    .favorited {
      color: @error-color;
    }
  }

  .tool-use-button {
    flex-shrink: 0;
  }

  .pagination {
    display: flex;
    justify-content: center;
  }

  @media (max-width: @screen-sm) {
    .tool-search-input,
    .tool-filter-select {
      width: 100%;
    }

    .tools-results-summary {
      margin-top: -@spacing-sm;
    }
  }
</style>
