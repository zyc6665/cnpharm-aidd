import { ref, type Ref } from 'vue'
import { getToolList } from '@/api/tools'

/**
 * 判断某个工具是否为「演示（mock）模型包」，用于页面上的数据可信度提示。
 *
 * 背景：这个标记以前是页面硬编码的告警条，结果真实模型包上线后仍一直显示
 * 「本结果由 mock 模型包生成」，与事实不符。真值在工具包清单的
 * `metadata.mock`（后端序列化为 `Tool.mock`），前端只负责如实反映。
 *
 * 约定：
 * - 查询失败或工具不存在时返回 `false`（不显示横幅）——宁可不提示，也不谎报。
 * - 只读一次，不做轮询：工具是否 mock 在页面生命周期内不会变化。
 */
export function useToolMockBanner(toolSlug: string): { isMock: Ref<boolean> } {
  const isMock = ref(false)
  void (async () => {
    try {
      const response = await getToolList({ search: toolSlug, page: 1, page_size: 5 })
      const items = response.data?.items ?? []
      const matched = items.find((item) => item.slug === toolSlug)
      isMock.value = matched?.mock === true
    } catch {
      isMock.value = false
    }
  })()
  return { isMock }
}
