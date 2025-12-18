<template>
  <div class="tools-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title">{{ t('tools.title') }}</h1>
        <p class="page-subtitle">{{ t('tools.subtitle') }}</p>
      </div>

      <!-- 三视图切换标签 -->
      <div class="view-tabs">
        <a-tabs v-model:activeKey="currentView" @change="handleViewChange">
          <a-tab-pane key="public">
            <template #tab>
              <span class="tab-label">
                <AppstoreOutlined />
                {{ t('tools.publicTools') }}
                <a-badge v-if="total > 0" :count="total" :overflow-count="999" class="tab-badge" />
              </span>
            </template>
          </a-tab-pane>
          <a-tab-pane key="favorite" :disabled="!userStore.isLoggedIn">
            <template #tab>
              <span class="tab-label">
                <HeartOutlined />
                {{ t('tools.favoriteTools') }}
                <a-badge v-if="favoritesTotal > 0" :count="favoritesTotal" :overflow-count="999" class="tab-badge" />
              </span>
            </template>
          </a-tab-pane>
          <a-tab-pane key="custom" :disabled="!userStore.isLoggedIn">
            <template #tab>
              <span class="tab-label">
                <UserOutlined />
                {{ t('tools.customTools') }}
                <a-badge v-if="customTotal > 0" :count="customTotal" :overflow-count="999" class="tab-badge" />
              </span>
            </template>
          </a-tab-pane>
        </a-tabs>
      </div>

      <!-- 搜索和筛选 -->
      <div class="filter-bar">
        <a-input-search
          v-model:value="searchKeyword"
          :placeholder="t('tools.search')"
          size="large"
          style="max-width: 400px"
          allow-clear
          @search="handleSearch"
        />
        <a-select
          v-model:value="selectedCategory"
          :placeholder="t('tools.allCategories')"
          size="large"
          style="width: 200px"
          allow-clear
          @change="handleCategoryChange"
        >
          <a-select-option v-for="cat in categories" :key="cat.id" :value="cat.id">
            <span class="category-option">
              <span v-if="cat.icon" class="category-icon">{{ cat.icon }}</span>
              {{ cat.name }}
              <span v-if="cat.tool_count" class="category-count">({{ cat.tool_count }})</span>
            </span>
          </a-select-option>
        </a-select>
        <a-select
          v-model:value="selectedTags"
          :placeholder="t('tools.filterTags')"
          size="large"
          style="width: 200px"
          mode="multiple"
          allow-clear
          :max-tag-count="2"
          @change="handleTagChange"
        >
          <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.id">
            <a-tag :color="tag.color" size="small">{{ tag.name }}</a-tag>
          </a-select-option>
        </a-select>
        <a-dropdown v-if="currentView === 'public'">
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
      </div>

      <!-- 游客模式提示 -->
      <a-alert
        v-if="userStore.isGuest && (currentView === 'favorite' || currentView === 'custom')"
        type="warning"
        show-icon
        :message="t('tools.guestWarning')"
        style="margin-bottom: 16px"
      >
        <template #action>
          <a-button size="small" type="primary" @click="goLogin">
            {{ t('auth.goLogin') }}
          </a-button>
        </template>
      </a-alert>

      <!-- 工具列表 -->
      <a-spin :spinning="loading">
        <div v-if="displayTools.length" class="tools-grid">
          <a-row :gutter="[24, 24]">
            <a-col v-for="tool in displayTools" :key="tool.id" :xs="24" :sm="12" :lg="8" :xl="6">
              <div class="tool-card" @click="goToDetail(tool.id)">
                <div class="tool-header">
                  <div class="tool-icon">
                    <span v-if="tool.icon">{{ tool.icon }}</span>
                    <ToolOutlined v-else />
                  </div>
                  <div class="tool-badges">
                    <a-tag v-if="tool.category" color="gold">{{ tool.category.name }}</a-tag>
                    <a-tag v-if="tool.is_free" color="green">{{ t('tools.free') }}</a-tag>
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
                      {{ formatNumber(tool.run_count) }}
                    </span>
                    <span class="tool-stat">
                      <HeartFilled v-if="tool.is_favorited" class="favorited" />
                      <HeartOutlined v-else />
                      {{ formatNumber(tool.favorite_count) }}
                    </span>
                  </div>
                  <div class="tool-credits" v-if="!tool.is_free">
                    <ThunderboltOutlined />
                    {{ tool.credits }} {{ t('common.credits') }}
                  </div>
                </div>
              </div>
            </a-col>
          </a-row>
        </div>
        <a-empty v-else :description="emptyText">
          <template v-if="currentView === 'favorite'" #extra>
            <a-button type="primary" @click="currentView = 'public'">
              {{ t('tools.browseTools') }}
            </a-button>
          </template>
        </a-empty>
      </a-spin>

      <!-- 分页 -->
      <div v-if="currentTotal > pageSize" class="pagination">
        <a-pagination
          v-model:current="currentPage"
          :total="currentTotal"
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
  import { ref, computed, onMounted, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import {
    ToolOutlined,
    PlayCircleOutlined,
    HeartOutlined,
    HeartFilled,
    AppstoreOutlined,
    UserOutlined,
    SortAscendingOutlined,
    DownOutlined,
    ThunderboltOutlined
  } from '@ant-design/icons-vue'
  import { useToolsStore, useUserStore } from '@/stores'
  import type { ToolView } from '@/types/models'

  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()

  const searchKeyword = ref('')
  const selectedCategory = ref<number | undefined>()
  const selectedTags = ref<number[]>([])
  const currentPage = ref(1)
  const pageSize = ref(12)
  const sortBy = ref('popular')
  const currentView = ref<ToolView>('public')

  const loading = computed(() => toolsStore.loading)
  const categories = computed(() => toolsStore.categories)
  const tags = computed(() => toolsStore.tags)
  const total = computed(() => toolsStore.total)
  const favoritesTotal = computed(() => toolsStore.favoritesTotal)
  const customTotal = computed(() => toolsStore.customTotal)

  const displayTools = computed(() => {
    switch (currentView.value) {
      case 'favorite':
        return toolsStore.favoriteToolsList
      case 'custom':
        return toolsStore.customToolsList
      default:
        return toolsStore.tools
    }
  })

  const currentTotal = computed(() => {
    switch (currentView.value) {
      case 'favorite':
        return favoritesTotal.value
      case 'custom':
        return customTotal.value
      default:
        return total.value
    }
  })

  const sortLabel = computed(() => {
    const labels: Record<string, string> = {
      popular: t('tools.sortPopular'),
      newest: t('tools.sortNewest'),
      name: t('tools.sortName')
    }
    return labels[sortBy.value] || t('tools.sortPopular')
  })

  const emptyText = computed(() => {
    switch (currentView.value) {
      case 'favorite':
        return t('tools.noFavorites')
      case 'custom':
        return t('tools.noCustomTools')
      default:
        return t('tools.noTools')
    }
  })

  const formatNumber = (num: number) => {
    if (num >= 10000) {
      return (num / 10000).toFixed(1) + 'w'
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k'
    }
    return num.toString()
  }

  const fetchData = async () => {
    const params: Record<string, unknown> = {
      keyword: searchKeyword.value || undefined,
      category_id: selectedCategory.value,
      tag_ids: selectedTags.value.length > 0 ? selectedTags.value : undefined,
      page: currentPage.value,
      page_size: pageSize.value,
      sort_by: sortBy.value
    }

    switch (currentView.value) {
      case 'favorite':
        await toolsStore.fetchFavoriteTools(params)
        break
      case 'custom':
        await toolsStore.fetchCustomTools(params)
        break
      default:
        await toolsStore.fetchTools(params)
    }
  }

  const handleViewChange = (view: string) => {
    currentView.value = view as ToolView
    toolsStore.setCurrentView(view as ToolView)
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

  const goToDetail = (id: number) => {
    router.push(`/tools/${id}`)
  }

  const goLogin = () => {
    router.push('/login')
  }

  // 监听用户登录状态，自动刷新收藏数
  watch(() => userStore.isLoggedIn, (isLoggedIn) => {
    if (isLoggedIn) {
      toolsStore.fetchFavoriteTools({ page: 1, page_size: 1 })
    }
  })

  onMounted(async () => {
    await Promise.all([
      fetchData(),
      toolsStore.fetchCategories(),
      toolsStore.fetchTags()
    ])

    // 如果已登录，获取收藏数
    if (userStore.isLoggedIn) {
      toolsStore.fetchFavoriteTools({ page: 1, page_size: 1 })
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tools-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .page-header {
    text-align: center;
    margin-bottom: @spacing-xl;
  }

  .page-title {
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    margin-bottom: @spacing-sm;
  }

  .page-subtitle {
    color: @text-color-light-secondary;
    font-size: @font-size-lg;
  }

  // 视图切换标签
  .view-tabs {
    margin-bottom: @spacing-lg;

    :deep(.ant-tabs-nav) {
      margin-bottom: 0;

      &::before {
        border-bottom: none;
      }
    }

    .tab-label {
      display: flex;
      align-items: center;
      gap: @spacing-xs;

      .anticon {
        font-size: 16px;
      }
    }

    .tab-badge {
      margin-left: @spacing-xs;

      :deep(.ant-badge-count) {
        background: @accent-color;
        font-size: 10px;
        height: 16px;
        min-width: 16px;
        line-height: 16px;
      }
    }
  }

  .filter-bar {
    display: flex;
    gap: @spacing-md;
    margin-bottom: @spacing-xl;
    flex-wrap: wrap;

    .category-option {
      display: flex;
      align-items: center;
      gap: @spacing-xs;

      .category-icon {
        font-size: 16px;
      }

      .category-count {
        color: @text-color-light-tertiary;
        font-size: @font-size-sm;
      }
    }
  }

  .tools-grid {
    margin-bottom: @spacing-xl;
  }

  .tool-card {
    .card();
    cursor: pointer;
    height: 100%;
    display: flex;
    flex-direction: column;

    &:hover {
      transform: translateY(-4px);
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
    background: @accent-color-light;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    color: @accent-color;
  }

  .tool-badges {
    display: flex;
    gap: @spacing-xs;
    flex-wrap: wrap;
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

  .tool-credits {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    color: @warning-color;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
  }

  .pagination {
    display: flex;
    justify-content: center;
  }
</style>
