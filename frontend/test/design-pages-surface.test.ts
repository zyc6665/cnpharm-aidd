import { describe, expect, test } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mount } from '@vue/test-utils'
import MockDataBanner from '@/components/common/MockDataBanner.vue'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

describe('设计页（P-15 / P-16 / P-17）交付面', () => {
  test('三个视图文件、组件与 API/类型文件均存在', () => {
    const files = [
      'src/views/design/MoleculeGeneration.vue',
      'src/views/design/PeptideDesign.vue',
      'src/views/design/GenerationResults.vue',
      'src/views/design/components/PocketPicker.vue',
      'src/components/common/MockDataBanner.vue',
      'src/api/design.ts',
      'src/types/design.ts',
    ]
    for (const file of files) {
      expect(existsSync(resolve(rootDir, file)), `${file} 必须存在`).toBe(true)
    }
  })

  test('路由注册了三条设计页路由且为懒加载', () => {
    const source = readSource('src/router/index.ts')
    const routes: Array<{ name: string; path: string; view: string }> = [
      { name: 'MoleculeGeneration', path: '/design/molecules', view: '@/views/design/MoleculeGeneration.vue' },
      { name: 'PeptideDesign', path: '/design/peptides', view: '@/views/design/PeptideDesign.vue' },
      { name: 'GenerationResults', path: '/tasks/:id/results', view: '@/views/design/GenerationResults.vue' },
    ]
    for (const route of routes) {
      expect(source).toContain(`path: '${route.path}'`)
      expect(source).toContain(`name: '${route.name}'`)
      expect(source).toContain(`import('${route.view}')`)
    }
  })

  test('tool slug 与冻结契约一致', () => {
    const source = readSource('src/types/design.ts')
    expect(source).toContain("MOLECULE_GENERATION_TOOL_SLUG = 'std-diff-molecule-generation'")
    expect(source).toContain("PEPTIDE_DESIGN_TOOL_SLUG = 'therapainter-peptide-design'")
  })

  test('api/design.ts 使用契约约定的工具列表与表格下载端点', () => {
    const source = readSource('src/api/design.ts')
    expect(source).toContain('page_size: 100')
    expect(source).toContain(
      '/api/v1/artifacts/${table.artifactId}/versions/${table.versionId}/files/${MOLECULE_TABLE_FILE_ROLE}/download'
    )
    expect(source).toContain('MOLECULE_TABLE_FILE_ROLE')
    expect(readSource('src/types/design.ts')).toContain("MOLECULE_TABLE_FILE_ROLE = 'table_file'")
  })

  test('MockDataBanner 在 mock 为真时渲染，为假时不渲染任何 DOM', () => {
    const visible = mount(MockDataBanner, { props: { mock: true } })
    expect(visible.find('[data-testid="mock-data-banner"]').exists()).toBe(true)

    const hidden = mount(MockDataBanner, { props: { mock: false } })
    expect(hidden.find('[data-testid="mock-data-banner"]').exists()).toBe(false)
  })

  test('i18n 在 tasks 命名空间之前提供了 design 命名空间（中英双语）', () => {
    for (const locale of ['src/locales/zh-CN/index.ts', 'src/locales/en-US/index.ts']) {
      const source = readSource(locale)
      const designIndex = source.indexOf('\n  design: {')
      const tasksIndex = source.indexOf('\n  tasks: {')
      expect(designIndex, `${locale} 必须有 design 命名空间`).toBeGreaterThan(-1)
      expect(tasksIndex, `${locale} 必须有 tasks 命名空间`).toBeGreaterThan(-1)
      expect(designIndex, `${locale} design 必须插在 tasks 之前`).toBeLessThan(tasksIndex)
    }
  })
})
