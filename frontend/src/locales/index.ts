import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export type Locale = 'zh-CN' | 'en-US'

const isBrowser = typeof window !== 'undefined' && typeof localStorage !== 'undefined'
const savedLocale = isBrowser ? localStorage.getItem('cpumodel_locale') : null

const i18n = createI18n({
  legacy: false,
  locale: savedLocale === 'en-US' ? savedLocale : 'zh-CN',
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  }
})

export const setLocale = (locale: Locale) => {
  i18n.global.locale.value = locale
  if (!isBrowser) {
    return
  }
  localStorage.setItem('cpumodel_locale', locale)
  document.documentElement.setAttribute('lang', locale === 'zh-CN' ? 'zh' : 'en')
}

export const getLocale = (): Locale => {
  return i18n.global.locale.value as Locale
}

export default i18n
