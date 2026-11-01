/**
 * 统一图表配色 — 与 assets/styles/variables.less 的 @chart-1..8 一一对应。
 *
 * 视图里的 ECharts 配置不要再写死十六进制色，统一从这里取：
 *   import { chartPalette, chartColors } from '@/utils/chartTheme'
 *   color: [...chartPalette]        // 分类色板
 *   color: chartColors.primary      // 单色（折线 / 柱状主线）
 *
 * 暗 / 浅主题共享同一套色值，保证同一数据系列的图形语义一致；
 * 若未来需要主题化图表，可在此扩展为基于 document data-theme 的 getter。
 */
export const chartPalette = [
  '#5b8ff9', // chart-1 主蓝
  '#61ddaa', // chart-2 青绿
  '#f6bd16', // chart-3 金
  '#ff9845', // chart-4 橙
  '#7262fd', // chart-5 紫
  '#9270ca', // chart-6 浅紫
  '#52c41a', // chart-7 绿（正向 / 达标）
  '#f5222d' // chart-8 红（负向 / 告警）
] as const

export const chartColors = {
  /** 主折线 / 主柱（chart-1） */
  primary: chartPalette[0],
  /** 正向 / 达标（chart-7） */
  positive: chartPalette[6],
  /** 负向 / 告警（chart-8） */
  negative: chartPalette[7],
  /** 中性提示 / 对比序列（chart-3） */
  warning: chartPalette[2],
  /** 次要序列（chart-6） */
  purple: chartPalette[5],
  /** 主色半透明面积填充（主色 18%） */
  primaryArea: 'rgba(91, 143, 249, 0.18)',
  /** 正向半透明面积填充 */
  positiveArea: 'rgba(82, 196, 26, 0.18)'
} as const

/** 按索引取色，超出自动循环 */
export function chartColorAt(index: number): string {
  const color = chartPalette[index % chartPalette.length]
  return color ?? chartPalette[0]
}
