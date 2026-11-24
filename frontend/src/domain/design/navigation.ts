import {
  MOLECULE_GENERATION_TOOL_SLUG,
  PEPTIDE_DESIGN_TOOL_SLUG,
  POCKET_PREDICT_TOOL_SLUG,
  STRUCTURE_PREDICT_TOOL_SLUG,
} from '@/types/design'

/**
 * 「研发流程」工具分组（按 AIDD 阶段组织）。
 *
 * 默认每个工具都是独立入口（可直接选项目数据或本地上传运行，不强绑定前置步骤）；
 * 需要多步串联时再走工作流编排。
 */
export interface DesignNavItem {
  key: string
  to: string
  labelKey: string
  isNew?: boolean
}

export interface DesignNavGroup {
  groupKey: string
  labelKey: string
  items: DesignNavItem[]
}

export function buildDesignNavGroups(projectId?: string): DesignNavGroup[] {
  const withProject = (base: string): string => {
    if (!projectId) return base
    const sep = base.includes('?') ? '&' : '?'
    return `${base}${sep}project_id=${encodeURIComponent(projectId)}`
  }
  return [
    {
      groupKey: 'prepare',
      labelKey: 'nav.designGroupPrepare',
      items: [
        { key: 'structurePredict', to: withProject(`/tools/${STRUCTURE_PREDICT_TOOL_SLUG}`), labelKey: 'nav.structurePredict' },
        { key: 'pocketPredict', to: withProject(`/tools/${POCKET_PREDICT_TOOL_SLUG}`), labelKey: 'nav.pocketPredict' },
      ],
    },
    {
      groupKey: 'design',
      labelKey: 'nav.designGroupDesign',
      items: [
        { key: 'molecules', to: withProject('/design/molecules'), labelKey: 'nav.molecules' },
        { key: 'peptides', to: withProject('/design/peptides'), labelKey: 'nav.peptides' },
        { key: 'screen', to: withProject('/screen'), labelKey: 'nav.screen' },
      ],
    },
    {
      groupKey: 'evaluate',
      labelKey: 'nav.designGroupEvaluate',
      items: [
        { key: 'predict', to: withProject('/predict'), labelKey: 'nav.predict' },
        { key: 'md', to: withProject('/md'), labelKey: 'nav.md' },
      ],
    },
  ]
}

export interface DesignNavLocation {
  path: string
  focus?: string
}

/**
 * 侧栏项是否高亮：`to` 可携带 `?focus=` 查询（结构/口袋入口），
 * 不能只用 `route.path.startsWith(to)`，否则带 query 的项永远不高亮。
 */
export function isDesignNavItemActive(
  item: DesignNavItem,
  location: DesignNavLocation
): boolean {
  const [path, query] = item.to.split('?')
  if (location.path !== path) return false
  if (!query) return true
  const expectedFocus = new URLSearchParams(query).get('focus') ?? ''
  return (location.focus ?? '') === expectedFocus
}
