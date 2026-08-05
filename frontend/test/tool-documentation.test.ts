import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  buildFallbackToolDocumentation,
  renderMarkdownToHtml
} from '../src/domain/tools/tool-documentation.ts'

test('Markdown 渲染应转义原始 HTML 并支持常用格式', () => {
  const html = renderMarkdownToHtml(`# Tool Guide

<script>alert('xss')</script>

- input file
- output file

Use \`device\` safely.

\`\`\`json
{"device":"cpu"}
\`\`\`

[Docs](https://example.com/docs)

| Name | Type |
| --- | --- |
| pocket_pdb | file |
`)

  assert.equal(html.includes('<script>'), false)
  assert.equal(html.includes('&lt;script&gt;'), true)
  assert.equal(html.includes('<h1>Tool Guide</h1>'), true)
  assert.equal(html.includes('<ul>'), true)
  assert.equal(html.includes('<li>input file</li>'), true)
  assert.equal(html.includes('<code>device</code>'), true)
  assert.equal(html.includes('<pre><code'), true)
  assert.equal(html.includes('href="https://example.com/docs"'), true)
  assert.equal(html.includes('target="_blank"'), true)
  assert.equal(html.includes('<table>'), true)
  assert.equal(html.includes('<td>pocket_pdb</td>'), true)
})

test('兜底工具介绍应包含工具描述、输入参数、输出 Schema 和输出路径规则', () => {
  const markdown = buildFallbackToolDocumentation({
    toolName: 'Pocket Finder',
    description: 'Detect pockets from protein structures.',
    inputSchema: {
      type: 'object',
      properties: {
        protein_pdb: {
          type: 'file',
          title: 'Protein PDB',
          description: 'Input protein structure.'
        },
        n_samples: {
          type: 'integer',
          default: 8,
          minimum: 1,
          maximum: 32,
          description: 'Candidate count.'
        }
      },
      required: ['protein_pdb']
    },
    outputSchema: {
      type: 'object',
      properties: {
        pockets_csv: {
          type: 'string',
          format: 'file',
          description: 'Pocket score table.'
        }
      }
    },
    outputGlobs: ['output/result.csv', 'output/logs/run.log'],
    labels: {
      title: '工具介绍',
      overview: '模型介绍',
      parameters: '参数说明',
      outputs: '输出文件',
      outputPatterns: '输出路径规则',
      name: '名称',
      required: '必填',
      optional: '可选',
      defaultValue: '默认值',
      type: '类型',
      description: '说明',
      range: '范围',
      noDocumentation: '暂无详细介绍'
    }
  })

  assert.equal(markdown.includes('# Pocket Finder 工具介绍'), true)
  assert.equal(markdown.includes('Detect pockets from protein structures.'), true)
  assert.equal(markdown.includes('| 名称 | 类型 | 必填 | 说明 |'), true)
  assert.equal(markdown.includes('| Protein PDB | file | 必填 |'), true)
  assert.equal(markdown.includes('Candidate count.'), true)
  assert.equal(markdown.includes('默认值: 8'), true)
  assert.equal(markdown.includes('范围: 1 - 32'), true)
  assert.equal(markdown.includes('pockets_csv'), true)
  assert.equal(markdown.includes('output/result.csv'), true)
  assert.equal(markdown.includes('output/logs/run.log'), true)
})
