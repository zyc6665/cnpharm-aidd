<template>
  <div class="user-favorites">
    <a-card :title="t('user.favorites')">
      <template #extra>
        <a-input-search
          v-model:value="searchKeyword"
          :placeholder="t('tools.search')"
          style="width: 200px"
          @search="handleSearch"
        />
      </template>

      <a-spin :spinning="loading">
        <template v-if="favorites.length > 0">
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
                      <a-tag :color="getCategoryColor(tool.category?.slug)">
                        {{ tool.category?.name || tool.category }}
                      </a-tag>
                      <span class="tool-stats">
                        <PlayCircleOutlined /> {{ tool.run_count || 0 }}
                      </span>
                    </div>
                  </template>
                </a-card-meta>
                <template #actions>
                  <a-tooltip :title="t('tools.run')">
                    <PlayCircleOutlined @click.stop="runTool(tool.id)" />
                  </a-tooltip>
                  <a-tooltip :title="t('tools.unfavorite')">
                    <HeartFilled
                      class="favorite-icon"
                      @click.stop="handleUnfavorite(tool.id)"
                    />
                  </a-tooltip>
                </template>
              </a-card>
            </a-col>
          </a-row>
        </template>

        <a-empty v-else :description="t('user.noFavorites')">
          <template #image>
            <HeartOutlined style="font-size: 64px; color: #ccc" />
          </template>
          <a-button type="primary" @click="goToTools">
            {{ t('user.exploreTool') }}
          </a-button>
        </a-empty>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ExperimentOutlined,
  PlayCircleOutlined,
  HeartOutlined,
  HeartFilled
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
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
    await toolsStore.fetchFavoriteTools()
    favorites.value = toolsStore.favoriteToolsList
  } catch {
    // 错误已处理
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  // 搜索在 computed 中处理
}

const goToTool = (id: number) => {
  router.push(`/tools/${id}`)
}

const goToTools = () => {
  router.push('/tools')
}

const runTool = (id: number) => {
  router.push(`/tools/${id}`)
}

const handleUnfavorite = (toolId: number) => {
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
  .tool-card {
    height: 100%;

    .tool-cover {
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, @primary-color-light 0%, #e6f7ff 100%);
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

    .favorite-icon {
      color: @error-color;
    }

    :deep(.ant-card-actions) {
      li {
        margin: 0;
      }
    }
  }
}
</style>
