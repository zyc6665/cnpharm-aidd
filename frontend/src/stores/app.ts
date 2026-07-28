import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { setLocale as syncI18nLocale } from '@/locales'

export type Locale = 'zh-CN' | 'en-US'
export type Theme = 'light' | 'dark'

const getInitialLocale = (): Locale => {
  if (typeof localStorage === 'undefined') {
    return 'zh-CN'
  }

  const storedLocale = localStorage.getItem('cpumodel_locale')
  return storedLocale === 'en-US' ? 'en-US' : 'zh-CN'
}

export const useAppStore = defineStore('app', () => {
  // State
  const locale = ref<Locale>(getInitialLocale())
  const theme = ref<Theme>('dark')
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
