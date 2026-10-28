import { computed, type Component } from 'vue'

/**
 * MockDataBanner 由另一分支（UI-1）创建，路径 `@/components/common/MockDataBanner.vue`。
 * 本分支只「使用」它，不在本分支创建/修改；若当前分支尚无该文件，编译与运行都不能失败。
 * 因此这里用 Vite 的 `import.meta.glob`（eager）在运行时探测：文件存在则使用共享组件，
 * 不存在则返回 null，由页面内的兜底 `a-alert` 渲染同样的横幅（同样带 data-testid）。
 * 合并 UI-1 的分支后，glob 会自动命中真实组件，无需改动页面。
 */
const bannerModules = import.meta.glob('../../components/common/MockDataBanner.vue', {
  eager: true
}) as Record<string, { default?: Component }>

export function useSharedMockBanner() {
  const entry = Object.values(bannerModules)[0]
  return computed<Component | null>(() => entry?.default ?? null)
}
