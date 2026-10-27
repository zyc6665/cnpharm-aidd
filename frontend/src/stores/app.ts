import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { setLocale as syncI18nLocale } from '@/locales'

export type Locale = 'zh-CN' | 'en-US'
export type Theme = 'light' | 'dark'

const LOCALE_STORAGE_KEY = 'cpumodel_locale'
const THEME_STORAGE_KEY = 'cpumodel_theme'

const getInitialLocale = (): Locale => {
  if (typeof localStorage === 'undefined') {
    return 'zh-CN'
  }

  const storedLocale = localStorage.getItem(LOCALE_STORAGE_KEY)
  return storedLocale === 'en-US' ? 'en-US' : 'zh-CN'
}

/**
 * 主题初值。刻意不跟随 `prefers-color-scheme`：本平台是科研工具，
 * 界面要在同一台机器的演示、截图与验收记录里保持一致的观感，
 * 跟随系统会让同一份文档里的截图忽明忽暗。用户显式切换过则以存储为准。
 */
const getInitialTheme = (): Theme => {
  if (typeof localStorage === 'undefined') {
    return 'dark'
  }

  return localStorage.getItem(THEME_STORAGE_KEY) === 'light' ? 'light' : 'dark'
}

export const useAppStore = defineStore('app', () => {
  // State
  const locale = ref<Locale>(getInitialLocale())
  const theme = ref<Theme>(getInitialTheme())
  const collapsed = ref(false)
  const loading = ref(false)

  // Getters
  const isDark = computed(() => theme.value === 'dark')
  const isCollapsed = computed(() => collapsed.value)

  // Actions
  const setLocale = (newLocale: Locale) => {
    locale.value = newLocale
    syncI18nLocale(newLocale)
  }

  const toggleLocale = () => {
    setLocale(locale.value === 'zh-CN' ? 'en-US' : 'zh-CN')
  }

  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', newTheme)
    }
    // 不写存储的话，用户切到浅色后刷新一次就回暗色——这是评审时发现的缺陷。
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(THEME_STORAGE_KEY, newTheme)
    }
  }

  const toggleTheme = () => {
    setTheme(theme.value === 'light' ? 'dark' : 'light')
  }

  const setCollapsed = (value: boolean) => {
    collapsed.value = value
  }

  const toggleCollapsed = () => {
    collapsed.value = !collapsed.value
  }

  const setLoading = (value: boolean) => {
    loading.value = value
  }

  return {
    // State
    locale,
    theme,
    collapsed,
    loading,
    // Getters
    isDark,
    isCollapsed,
    // Actions
    setLocale,
    toggleLocale,
    setTheme,
    toggleTheme,
    setCollapsed,
    toggleCollapsed,
    setLoading
  }
}, {
  persist: {
    pick: ['locale', 'theme', 'collapsed']
  }
})
