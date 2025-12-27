import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type Locale = 'zh-CN' | 'en-US'
export type Theme = 'light' | 'dark'

export const useAppStore = defineStore('app', () => {
  // State
  const locale = ref<Locale>('zh-CN')
  const theme = ref<Theme>('light')
  const collapsed = ref(false)
  const loading = ref(false)

  // Getters
  const isDark = computed(() => theme.value === 'dark')
  const isCollapsed = computed(() => collapsed.value)

  // Actions
  const setLocale = (newLocale: Locale) => {
    locale.value = newLocale
  }

  const toggleLocale = () => {
    locale.value = locale.value === 'zh-CN' ? 'en-US' : 'zh-CN'
  }

  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme
    document.documentElement.setAttribute('data-theme', newTheme)
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
