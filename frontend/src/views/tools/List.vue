<template>
  <div class="tools-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title">{{ t('tools.title') }}</h1>
        <p class="page-subtitle">{{ t('tools.subtitle') }}</p>
      </div>

      <!-- 视图切换标签 -->
      <div class="view-tabs">
        <a-radio-group v-model:value="currentView" button-style="solid" size="large" @change="handleViewChange">
          <a-radio-button value="public">
            <AppstoreOutlined />
            {{ t('tools.publicTools') }}
          </a-radio-button>
          <a-radio-button v-if="isLoggedIn" value="my">
            <UserOutlined />
            {{ t('tools.myTools') }}
          </a-radio-button>
          <a-radio-button v-if="isLoggedIn" value="favorites">
            <HeartOutlined />
            {{ t('tools.favorites') }}
          </a-radio-button>
        </a-radio-group>

        <!-- 创建工具按钮 -->
        <a-button v-if="isLoggedIn" type="primary" size="large" @click="goToCreate">
          <PlusOutlined />
          {{ t('tools.createTool') }}
        </a-button>

        <!-- 工具来源筛选（仅公开视图） -->
        <a-radio-group
          v-if="currentView === 'public'"
          v-model:value="providerFilter"
          size="large"
          @change="handleProviderChange"
        >
          <a-radio-button value="">{{ t('tools.allTools') }}</a-radio-button>
          <a-radio-button value="platform">
            <SafetyCertificateOutlined />
            {{ t('tools.providerType.platform') }}
          </a-radio-button>
          <a-radio-button value="user">
            <TeamOutlined />
            {{ t('tools.providerType.user') }}
          </a-radio-button>
        </a-radio-group>
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
          size="large"
          style="width: 200px"
          allow-clear
          @change="handleTagChange"
        >
          <a-select-option v-for="tag in tags" :key="tag.id" :value="tag.name">
            <a-tag :color="tag.color" size="small">{{ tag.name }}</a-tag>
          </a-select-option>
        </a-select>

        <!-- 我的工具视图的审核状态筛选 -->
        <a-select
          v-if="currentView === 'my'"
          v-model:value="reviewStatusFilter"
          :placeholder="t('tools.reviewStatus.all')"
          size="large"
          style="width: 160px"
          allow-clear
          @change="handleReviewStatusChange"
        >
          <a-select-option value="pending">{{ t('tools.reviewStatus.pending') }}</a-select-option>
          <a-select-option value="approved">{{ t('tools.reviewStatus.approved') }}</a-select-option>
          <a-select-option value="rejected">{{ t('tools.reviewStatus.rejected') }}</a-select-option>
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
      </div>

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
                    <!-- 工具来源标签 -->
                    <a-tag v-if="tool.provider_type === 'platform'" color="blue">
                      <SafetyCertificateOutlined />
                      {{ t('tools.providerType.platform') }}
                    </a-tag>
                    <a-tag v-else-if="tool.provider_type === 'user'" color="green">
                      <TeamOutlined />
                      {{ t('tools.providerType.user') }}
                    </a-tag>
                    <!-- 审核状态标签（仅我的工具视图） -->
                    <a-tag v-if="currentView === 'my'" :color="getReviewStatusColor(tool.review_status)">
                      {{ t(`tools.reviewStatus.${tool.review_status}`) }}
                    </a-tag>
                    <a-tag v-if="tool.gpu_required" color="purple">GPU</a-tag>
                  </div>
                </div>
                <h3 class="tool-name">{{ tool.name }}</h3>
                <p class="tool-desc">{{ tool.description }}</p>

                <!-- 拒绝原因提示（仅我的工具视图） -->
                <a-alert
                  v-if="currentView === 'my' && tool.review_status === 'rejected' && tool.reject_reason"
                  type="error"
                  :message="t('tools.rejectReason')"
                  :description="tool.reject_reason"
                  show-icon
                  class="reject-alert"
                />

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
                </div>
              </div>
            </a-col>
          </a-row>
        </div>
        <a-empty v-else :description="t('tools.noTools')" />
      </a-spin>

      <!-- 分页 -->
      <div v-if="displayTotal > pageSize" class="pagination">
        <a-pagination
          v-model:current="currentPage"
          :total="displayTotal"
          :page-size="pageSize"
          :show-total="(t: number) => `共 ${t} 条`"
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
    EyeOutlined,
    SortAscendingOutlined,
    DownOutlined,
    AppstoreOutlined,
    UserOutlined,
    SafetyCertificateOutlined,
    TeamOutlined,
    PlusOutlined
  } from '@ant-design/icons-vue'
  import { useToolsStore, useUserStore } from '@/stores'
  import type { ToolView, ToolProviderType, ToolReviewStatus } from '@/types/models'

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
  const providerFilter = ref<ToolProviderType | ''>('')
  const reviewStatusFilter = ref<ToolReviewStatus | undefined>()

  const loading = computed(() => toolsStore.loading)
  const isLoggedIn = computed(() => userStore.isLoggedIn)

  // 根据视图类型获取工具列表
  const displayTools = computed(() => {
    if (currentView.value === 'my') {
      return toolsStore.myTools
    }
    return toolsStore.tools
  })

  const displayTotal = computed(() => {
    if (currentView.value === 'my') {
      return toolsStore.myToolsTotal
    }
    return toolsStore.total
  })

  const categories = computed(() => toolsStore.categories)
  const tags = computed(() => toolsStore.tags)

  const sortLabel = computed(() => {
    const labels: Record<string, string> = {
      popular: t('tools.sortPopular'),
      newest: t('tools.sortNewest'),
      name: t('tools.sortName')
    }
    return labels[sortBy.value] || t('tools.sortPopular')
  })

  const formatNumber = (num: number) => {
    // 处理 undefined/null 的情况
    if (num == null || num === undefined) {
      return '0'
    }
    if (num >= 10000) {
      return (num / 10000).toFixed(1) + 'w'
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k'
    }
    return num.toString()
  }

  const getReviewStatusColor = (status: ToolReviewStatus) => {
    const colors: Record<ToolReviewStatus, string> = {
      not_required: 'blue',
      pending: 'orange',
      approved: 'green',
      rejected: 'red'
    }
    return colors[status] || 'default'
  }

  const fetchData = async () => {
    if (currentView.value === 'my') {
      await toolsStore.fetchMyTools({
        page: currentPage.value,
        page_size: pageSize.value,
        review_status: reviewStatusFilter.value,
        sort_by: sortBy.value
      })
    } else if (currentView.value === 'favorites') {
      await toolsStore.fetchTools({
        view: 'favorites',
        search: searchKeyword.value || undefined,
        category: selectedCategory.value,
        tag: selectedTag.value,
        page: currentPage.value,
        page_size: pageSize.value,
        sort_by: sortBy.value
      })
    } else {
      await toolsStore.fetchTools({
        view: 'public',
        search: searchKeyword.value || undefined,
        category: selectedCategory.value,
        tag: selectedTag.value,
        provider_type: providerFilter.value || undefined,
        page: currentPage.value,
        page_size: pageSize.value,
        sort_by: sortBy.value
      })
    }
  }

  const handleViewChange = () => {
    currentPage.value = 1
    reviewStatusFilter.value = undefined
    providerFilter.value = ''
    fetchData()
  }

  const handleProviderChange = () => {
    currentPage.value = 1
    fetchData()
  }

  const handleReviewStatusChange = () => {
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

  const goToDetail = (id: string) => {
    router.push(`/tools/${id}`)
  }

  const goToCreate = () => {
    router.push('/tools/create')
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

  .view-tabs {
    display: flex;
    justify-content: center;
    gap: @spacing-lg;
    margin-bottom: @spacing-xl;
    flex-wrap: wrap;
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
    max-width: 60%;
    justify-content: flex-end;
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

  .reject-alert {
    margin-top: @spacing-sm;
    margin-bottom: @spacing-sm;
    font-size: @font-size-xs;
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

  .pagination {
    display: flex;
    justify-content: center;
  }
</style>
