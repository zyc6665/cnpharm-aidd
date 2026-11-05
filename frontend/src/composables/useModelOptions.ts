/**
 * 按「模型能力族（model_family）」列出可选的同类模型，供设计流程各页的「模型选择」使用。
 *
 * 数据来源：`GET /tools`（公开视图），每个工具的 `contract.model_family` 由后端规范化。
 * 默认选中传入的 `defaultSlug`（当前推荐模型）；并记住用户上次选择（localStorage）。
 * 无同类多模型时只返回一项；拉取失败时返回空数组，调用方回退到自己的默认 slug。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { getToolList } from '@/api/tools'
import { resolveModelFamily } from '@/domain/design/modelFamilies'
import type { Tool } from '@/types/models'

export interface ModelOption {
  slug: string
  name: string
  description?: string
  version?: string
  mock?: boolean
  isDefault: boolean
  /** 该工具契约声明的输入字段（用于亲和力等页按模型动态渲染输入）。 */
  inputFields: string[]
}

export interface UseModelOptionsResult {
  options: Ref<ModelOption[]>
  selectedSlug: Ref<string>
  selectedOption: ComputedRef<ModelOption | null>
  hasChoice: ComputedRef<boolean>
  loading: Ref<boolean>
  error: Ref<string>
  load: () => Promise<void>
}

const STORAGE_PREFIX = 'design:model:'

export function useModelOptions(
  family: string,
  config: { defaultSlug: string; storageKey?: string }
): UseModelOptionsResult {
  const storageKey = config.storageKey ?? `${STORAGE_PREFIX}${family}`
  const defaultSlug = config.defaultSlug
  const options: Ref<ModelOption[]> = ref([])
  const selectedSlug: Ref<string> = ref(defaultSlug)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string> = ref('')

  const selectedOption = computed<ModelOption | null>(
    () => options.value.find(option => option.slug === selectedSlug.value) ?? null
  )
  const hasChoice = computed(() => options.value.length > 1)

  function readStored(): string {
    if (typeof localStorage === 'undefined') return ''
    return localStorage.getItem(storageKey) ?? ''
  }

  function persist(slug: string): void {
    if (typeof localStorage !== 'undefined' && slug) {
      localStorage.setItem(storageKey, slug)
    }
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const response = await getToolList({ view: 'public', page: 1, page_size: 100 })
      const tools: Tool[] = (response.data.items ?? []).filter(
        tool => tool.status === 'published' && resolveModelFamily(tool) === family
      )
      const next: ModelOption[] = tools.map(tool => ({
        slug: tool.slug,
        name: tool.name,
        description: tool.description,
        version: tool.current_version?.version,
        mock: tool.mock,
        isDefault: tool.slug === defaultSlug,
        inputFields: (tool.contract?.capability?.inputs ?? [])
          .map(input => input.field)
          .filter((field): field is string => Boolean(field)),
      }))
      options.value = next

      const stored = readStored()
      const storedValid = next.some(option => option.slug === stored)
      const fallback = next.find(option => option.slug === defaultSlug)?.slug ?? next[0]?.slug ?? defaultSlug
      selectedSlug.value = storedValid ? stored : fallback
      if (selectedSlug.value) persist(selectedSlug.value)
    } catch {
      error.value = 'load-failed'
      options.value = []
      selectedSlug.value = defaultSlug
    } finally {
      loading.value = false
    }
  }

  watch(selectedSlug, value => {
    if (value) persist(value)
  })

  return { options, selectedSlug, selectedOption, hasChoice, loading, error, load }
}
