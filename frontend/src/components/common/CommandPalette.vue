<template>
  <Teleport to="body">
    <Transition name="cp-fade">
      <div v-if="visible" class="cp-backdrop" @click="close">
        <Transition name="cp-scale" appear>
          <div v-if="visible" class="cp-panel" @click.stop>
            <div class="cp-input-wrap">
              <SearchOutlined class="cp-search-icon" />
              <input
                ref="inputRef"
                v-model="query"
                type="text"
                class="cp-input"
                :placeholder="t('command.placeholder')"
                @keydown="onKeydown"
                autocomplete="off"
                spellcheck="false"
              />
              <kbd class="cp-shortcut">Esc</kbd>
            </div>

            <div v-if="filteredItems.length === 0" class="cp-empty">
              {{ t('command.noResults') }}
            </div>

            <div v-else class="cp-results" ref="resultsRef">
              <template v-for="(group, gIdx) in groupedResults" :key="gIdx">
                <div class="cp-group-label">{{ group.label }}</div>
                <button
                  v-for="(item, iIdx) in group.items"
                  :key="item.id"
                  class="cp-item"
                  :class="{ active: activeId === item.id }"
                  @click="execute(item)"
                  @mouseenter="activeId = item.id"
                >
                  <component :is="item.icon" class="cp-item-icon" />
                  <span class="cp-item-label">{{ item.label }}</span>
                  <span v-if="item.shortcut" class="cp-item-shortcut">{{ item.shortcut }}</span>
                </button>
              </template>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  SearchOutlined,
  HomeOutlined,
  AppstoreOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  DashboardOutlined,
  SettingOutlined,
  BulbOutlined,
  PlusOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useUserStore } from '@/stores'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()

const visible = ref(false)
const query = ref('')
const activeId = ref<string | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

interface PaletteItem {
  id: string
  label: string
  icon: Component
  action: () => void
  shortcut?: string
  group: string
}

const items = computed<PaletteItem[]>(() => {
  const list: PaletteItem[] = [
    {
      id: 'nav-workspace',
      label: t('nav.workspace'),
      icon: HomeOutlined,
      action: () => router.push('/workspace'),
      group: t('command.group.navigate'),
    },
    {
      id: 'nav-tools',
      label: t('nav.tools'),
      icon: AppstoreOutlined,
      action: () => router.push('/tools'),
      group: t('command.group.navigate'),
    },
    {
      id: 'nav-tasks',
      label: t('nav.tasks'),
      icon: ExperimentOutlined,
      action: () => router.push('/tasks'),
      group: t('command.group.navigate'),
    },
    {
      id: 'nav-workflow',
      label: t('nav.workflow'),
      icon: ApartmentOutlined,
      action: () => router.push('/workflow'),
      group: t('command.group.navigate'),
    },
    {
      id: 'action-new-task',
      label: t('command.newTask'),
      icon: PlusOutlined,
      action: () => router.push('/tools'),
      shortcut: 'N',
      group: t('command.group.actions'),
    },
    {
      id: 'action-settings',
      label: t('user.settings'),
      icon: SettingOutlined,
      action: () => router.push('/user/settings'),
      group: t('command.group.actions'),
    },
    {
      id: 'action-toggle-theme',
      label: t('command.toggleTheme'),
      icon: BulbOutlined,
      action: () => toggleTheme(),
      group: t('command.group.actions'),
    },
  ]

  if (userStore.isAdmin) {
    list.push({
      id: 'nav-admin',
      label: t('nav.admin'),
      icon: DashboardOutlined,
      action: () => router.push('/admin/dashboard'),
      group: t('command.group.navigate'),
    })
  }

  return list
})

const filteredItems = computed(() => {
  const q = query.value.toLowerCase().trim()
  if (!q) return items.value
  return items.value.filter(
    (item) =>
      item.label.toLowerCase().includes(q) ||
      item.id.toLowerCase().includes(q),
  )
})

const groupedResults = computed(() => {
  const groups = new Map<string, PaletteItem[]>()
  for (const item of filteredItems.value) {
    const g = groups.get(item.group) ?? []
    g.push(item)
    groups.set(item.group, g)
  }
  return Array.from(groups.entries()).map(([label, items]) => ({ label, items }))
})

function open() {
  visible.value = true
  query.value = ''
  activeId.value = filteredItems.value[0]?.id ?? null
  nextTick(() => inputRef.value?.focus())
}

function close() {
  visible.value = false
}

function execute(item: PaletteItem) {
  item.action()
  close()
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme')
  const next = current === 'light' ? null : 'light'
  if (next) {
    document.documentElement.setAttribute('data-theme', next)
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    const flat = filteredItems.value
    const idx = flat.findIndex((i) => i.id === activeId.value)
    activeId.value = idx < flat.length - 1 ? flat[idx + 1]?.id ?? null : flat[0]?.id ?? null
    return
  }

  if (e.key === 'ArrowUp') {
    e.preventDefault()
    const flat = filteredItems.value
    const idx = flat.findIndex((i) => i.id === activeId.value)
    activeId.value = idx > 0 ? flat[idx - 1]?.id ?? null : flat[flat.length - 1]?.id ?? null
    return
  }

  if (e.key === 'Enter') {
    e.preventDefault()
    const item = filteredItems.value.find((i) => i.id === activeId.value)
    if (item) execute(item)
    return
  }
}

defineExpose({ open, close })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.cp-backdrop {
  position: fixed;
  inset: 0;
  z-index: @z-index-command-palette;
  display: flex;
  justify-content: center;
  padding-top: 20vh;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.cp-panel {
  width: 100%;
  max-width: 520px;
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  background: @bg-elevated;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-xl;
  box-shadow:
    0 25px 50px -12px rgba(0, 0, 0, 0.6),
    0 0 0 1px rgba(255, 255, 255, 0.04);
  overflow: hidden;
}

.cp-input-wrap {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-md;
  border-bottom: 1px solid @border-color;
}

.cp-search-icon {
  font-size: 18px;
  color: @text-tertiary;
  flex-shrink: 0;
}

.cp-input {
  flex: 1;
  border: none;
  background: transparent;
  color: @text-primary;
  font-size: @font-size-md;
  font-family: @font-family;
  outline: none;

  &::placeholder {
    color: @text-tertiary;
  }
}

.cp-shortcut {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  padding: 0 8px;
  background: @bg-hover;
  border: 1px solid @border-color;
  border-radius: @border-radius-sm;
  color: @text-tertiary;
  font-size: 11px;
  font-family: @font-family;
  font-weight: @font-weight-medium;
  line-height: 1;
}

.cp-empty {
  padding: @spacing-xl @spacing-md;
  text-align: center;
  color: @text-tertiary;
  font-size: @font-size-sm;
}

.cp-results {
  overflow-y: auto;
  padding: @spacing-xs;
  max-height: 340px;
}

.cp-group-label {
  padding: @spacing-sm @spacing-sm 4px;
  color: @text-tertiary;
  font-size: @font-size-xs;
  font-weight: @font-weight-semibold;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.cp-item {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  width: 100%;
  height: 40px;
  padding: 0 @spacing-sm;
  border: none;
  border-radius: @border-radius-md;
  background: none;
  color: @text-secondary;
  font-size: @font-size-sm;
  font-family: @font-family;
  cursor: pointer;
  transition: all @transition-fast;
  text-align: left;

  &:hover,
  &.active {
    color: @text-primary;
    background: @bg-hover;
  }
}

.cp-item-icon {
  font-size: 16px;
  width: 20px;
  flex-shrink: 0;
}

.cp-item-label {
  flex: 1;
}

.cp-item-shortcut {
  color: @text-tertiary;
  font-size: @font-size-xs;
  font-family: @font-family-mono;
}

// ── 过渡动画 ──
.cp-fade-enter-active,
.cp-fade-leave-active {
  transition: opacity 0.15s ease;
}

.cp-fade-enter-from,
.cp-fade-leave-to {
  opacity: 0;
}

.cp-scale-enter-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.cp-scale-leave-active {
  transition: all 0.1s ease;
}

.cp-scale-enter-from {
  opacity: 0;
  transform: scale(0.96) translateY(-8px);
}

.cp-scale-leave-to {
  opacity: 0;
  transform: scale(0.98);
}
</style>
