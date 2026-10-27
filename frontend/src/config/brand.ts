/**
 * 平台品牌标识集中定义。
 *
 * 为什么要有这个模块：品牌名原来散落在 13 处（index.html、登录壳层、侧边栏、
 * 错误页、路由标题、首页页脚、两份 locale 的版权行……），改一次要全文搜索，
 * 漏一处就会在客户现场露出上游产品名。集中到一处后，换名只改这里。
 *
 * 名称取自 `docs/06-UI交互与原型说明.md` §4 的全局框架稿「Logo 中国医药 AI 药物研发平台」。
 */

/** 完整产品名，用于登录页标题、页面 title、版权行。 */
export const PLATFORM_NAME = '中国医药 AI 药物研发平台'

/** 侧边栏等窄容器里的短名。中文全名在 240px 侧栏里会换行，故拆一个短名。 */
export const PLATFORM_SHORT_NAME = '中国医药 AIDD'

/** 登录页的英文眉标，与中文主标题形成层次，不承担识别职责。 */
export const PLATFORM_EYEBROW = 'China Pharmaceutical AIDD Platform'

/** 页面标题后缀，`${页面名} - ${PLATFORM_NAME}`。 */
export function buildDocumentTitle(pageTitle?: string | null): string {
  return pageTitle ? `${pageTitle} - ${PLATFORM_NAME}` : PLATFORM_NAME
}

/** 版权行。年份由调用方传入，避免模块加载期把年份固化。 */
export function buildCopyright(year: number): string {
  return `© ${year} 中国医药健康产业股份有限公司`
}
