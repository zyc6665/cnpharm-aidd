import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export type Locale = 'zh-CN' | 'en-US'

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('cpumodel_locale') as Locale || 'zh-CN',
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  }
})

export const setLocale = (locale: Locale) => {
  i18n.global.locale.value = locale
  localStorage.setItem('cpumodel_locale', locale)
  document.documentElement.setAttribute('lang', locale === 'zh-CN' ? 'zh' : 'en')
}

export const getLocale = (): Locale => {
  return i18n.global.locale.value as Locale
}

export default i18n
