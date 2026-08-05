import type { ToolView } from '@/types/models'

export interface ToolListQueryParams {
  category?: string
  tag?: string
  search?: string
  status?: string
  view?: ToolView
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface BuildToolListParamsInput {
  view: ToolView
  searchKeyword?: string
  selectedCategory?: string
  selectedTag?: string
  currentPage: number
  pageSize: number
  sortBy: string
}

export function buildToolListParams(input: BuildToolListParamsInput): ToolListQueryParams {
  return {
    view: input.view,
    search: input.searchKeyword?.trim() || undefined,
    category: input.selectedCategory,
    tag: input.selectedTag,
    page: input.currentPage,
    page_size: input.pageSize,
    sort_by: input.sortBy
  }
}

export function getToolSortLabelKey(sortBy: string): string {
  const labels: Record<string, string> = {
    popular: 'tools.sortPopular',
    newest: 'tools.sortNewest',
    name: 'tools.sortName'
  }
  return labels[sortBy] || 'tools.sortPopular'
}

export function getToolViewLabelKey(view: ToolView): string {
  return view === 'favorites' ? 'tools.favorites' : 'tools.publicTools'
}

export function formatToolCount(value?: number | null): string {
  if (value == null) {
    return '0'
  }
  if (value >= 10000) {
    return `${(value / 10000).toFixed(1)}w`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`
  }
  return value.toString()
}
