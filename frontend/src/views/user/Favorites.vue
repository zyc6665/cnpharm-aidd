<template>
  <div class="user-favorites">
    <AppPageHeader :title="t('user.favorites')">
      <template #actions>
        <a-input-search
          v-model:value="searchKeyword"
          :placeholder="t('tools.search')"
          class="favorites-search-input"
          @search="handleSearch"
        />
      </template>
    </AppPageHeader>

    <a-card class="favorites-card">

      <SkeletonList v-if="loading" :count="5" />
        <template v-else-if="favorites.length > 0">
          <a-row :gutter="[16, 16]">
            <a-col
              v-for="tool in filteredFavorites"
              :key="tool.id"
              :xs="24"
              :sm="12"
              :lg="8"
            >
              <a-card hoverable class="tool-card" @click="goToTool(tool.id)">
                <template #cover>
                  <div class="tool-cover">
                    <img
                      v-if="tool.icon"
                      :src="tool.icon"
                      :alt="tool.name"
                    />
                    <div v-else class="tool-icon-placeholder">
                      <ExperimentOutlined />
                    </div>
                  </div>
                </template>
                <a-card-meta :title="tool.name">
                  <template #description>
                    <p class="tool-description">{{ tool.description }}</p>
                    <div class="tool-meta">
                      <a-tag :color="getCategoryColor(tool.category)">
                        {{ tool.category }}
                      </a-tag>
                      <span class="tool-stats">
                        <PlayCircleOutlined /> {{ tool.run_count || tool.usage_count || 0 }}
                      </span>
                    </div>
                  </template>
                </a-card-meta>
                <template #actions>
                  <a-tooltip :title="t('tools.viewDetail')">
                    <a-button
                      type="text"
                      shape="circle"
                      class="favorite-card-action"
                      :aria-label="t('tools.viewDetail')"
                      @click.stop="goToTool(tool.id)"
                    >
                      <EyeOutlined />
                    </a-button>
                  </a-tooltip>
                  <a-tooltip :title="t('tools.run')">
                    <a-button
                      type="text"
                      shape="circle"
                      class="favorite-card-action"
                      :aria-label="t('tools.run')"
                      @click.stop="runTool(tool.id)"
                    >
                      <PlayCircleOutlined />
                    </a-button>
                  </a-tooltip>
                  <a-tooltip :title="t('tools.unfavorite')">
                    <a-button
                      type="text"
                      shape="circle"
                      class="favorite-card-action favorite-icon"
                      :aria-label="t('tools.unfavorite')"
                      @click.stop="handleUnfavorite(tool.id)"
                    >
                      <HeartFilled />
                    </a-button>
                  </a-tooltip>
                </template>
              </a-card>
            </a-col>
          </a-row>
        </template>

        <!-- 自绘空状态而不是 `a-empty` + `#image`：antd 的 Empty 只接受图片插槽，
             塞图标进去在深色底上仍是一块发白区域，且按钮位置与全站其它空状态不一致。 -->
        <AppEmptyState
          v-else
          :title="t('user.noFavorites')"
          :description="t('user.noFavoritesHint')"
        >
          <a-button type="primary" @click="goToTools">
            {{ t('user.exploreTool') }}
          </a-button>
        </AppEmptyState>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ExperimentOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  HeartFilled
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'
import { useToolsStore } from '@/stores'
import type { Tool } from '@/types/models'

const router = useRouter()
const { t } = useI18n()
const toolsStore = useToolsStore()

const loading = ref(false)
const searchKeyword = ref('')
const favorites = ref<Tool[]>([])

const filteredFavorites = computed(() => {
  if (!searchKeyword.value) {
    return favorites.value
  }
  const keyword = searchKeyword.value.toLowerCase()
  return favorites.value.filter(
    (tool) =>
      tool.name.toLowerCase().includes(keyword) ||
      tool.description?.toLowerCase().includes(keyword)
  )
})

const getCategoryColor = (category?: string) => {
  const colors: Record<string, string> = {
    'structure-prediction': 'blue',
    'molecular-docking': 'green',
    'sequence-analysis': 'orange',
    visualization: 'purple',
    default: 'default'
  }
  return colors[category || 'default'] || colors.default
}

const fetchFavorites = async () => {
  loading.value = true
  try {
    // 使用现有的fetchTools方法，传入view='favorites'
    await toolsStore.fetchTools({ view: 'favorites' })
    favorites.value = toolsStore.tools
  } catch {
    // 错误已处理
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  // 搜索在 computed 中处理
}

const goToTool = (id: string) => {
  router.push(`/tools/${id}`)
}

const goToTools = () => {
  router.push('/tools')
}

const runTool = (id: string) => {
  router.push(`/tools/${id}`)
}

const handleUnfavorite = (toolId: string) => {
  Modal.confirm({
    title: t('user.unfavoriteConfirm'),
    content: t('user.unfavoriteConfirmContent'),
    onOk: async () => {
      try {
        await toolsStore.toggleFavorite(toolId)
        favorites.value = favorites.value.filter((t) => t.id !== toolId)
        message.success(t('user.unfavoriteSuccess'))
      } catch {
        // 错误已处理
      }
    }
  })
}

onMounted(() => {
  fetchFavorites()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.user-favorites {
  .favorites-search-input {
    width: min(240px, 100%);
  }

  .tool-card {
    height: 100%;

    .tool-cover {
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, @primary-color-light 0%, @accent-color-light 100%);
      overflow: hidden;

      img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
      }

      .tool-icon-placeholder {
        font-size: 48px;
        color: @primary-color;
      }
    }

    .tool-description {
      height: 44px;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
      margin-bottom: @spacing-sm;
    }

    .tool-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;

      .tool-stats {
        color: @text-color-light-secondary;
        font-size: @font-size-sm;
      }
    }

    .favorite-card-action {
      color: @text-color-light-secondary;

      &:hover,
      &:focus-visible {
        color: @primary-color;
        background: @primary-color-light;
      }
    }

    .favorite-icon {
      color: @error-color;

      &:hover,
      &:focus-visible {
        color: @error-color;
        background: @error-color-light;
      }
    }

    :deep(.ant-card-actions) {
      li {
        margin: 0;
      }
    }
  }

  @media (max-width: @screen-sm) {
    .favorites-search-input {
      width: 100%;
    }
  }
}
</style>
