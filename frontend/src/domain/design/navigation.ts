/**
 * 「设计流程」侧栏分组（按 AIDD 阶段组织，而非工具清单）。
 *
 * 说明：结构预测 / 口袋预测落到 `/design` 流程总览页并聚焦对应阶段（`?focus=`），
 * 避免为两个入口各造一个只在选择项目时才成立的独立页面。
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

export function buildDesignNavGroups(): DesignNavGroup[] {
  return [
    {
      groupKey: 'prepare',
      labelKey: 'nav.designGroupPrepare',
      items: [
        { key: 'structurePredict', to: '/design?focus=structure', labelKey: 'nav.structurePredict', isNew: true },
        { key: 'pocketPredict', to: '/design?focus=pocket', labelKey: 'nav.pocketPredict', isNew: true },
      ],
    },
    {
      groupKey: 'design',
      labelKey: 'nav.designGroupDesign',
      items: [
        { key: 'molecules', to: '/design/molecules', labelKey: 'nav.molecules' },
        { key: 'peptides', to: '/design/peptides', labelKey: 'nav.peptides' },
        { key: 'screen', to: '/screen', labelKey: 'nav.screen' },
      ],
    },
    {
      groupKey: 'evaluate',
      labelKey: 'nav.designGroupEvaluate',
      items: [
        { key: 'predict', to: '/predict', labelKey: 'nav.predict' },
        { key: 'md', to: '/md', labelKey: 'nav.md' },
      ],
    },
    {
      groupKey: 'record',
      labelKey: 'nav.designGroupRecord',
      items: [{ key: 'designRuns', to: '/design/runs', labelKey: 'nav.designRuns' }],
    },
  ]
}
