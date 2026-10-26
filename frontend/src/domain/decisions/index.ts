/**
 * 决策记录域（P-39）：barrel。
 *
 * 实现集中在 `format.ts`（分组、计数、分页守卫、快照展示、载荷组装），
 * 与 `domain/targets/index.ts` 的写法一致——页面一律从 `@/domain/decisions` 导入。
 */
export * from './format'
