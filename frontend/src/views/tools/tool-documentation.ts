import type { SchemaProperty, ToolSchema } from '../../types/models'

export interface ToolDocumentationLabels {
  title: string
  overview: string
  parameters: string
  outputs: string
  outputPatterns: string
  name: string
  required: string
  optional: string
  defaultValue: string
  type: string
  description: string
  range: string
  noDocumentation: string
}

export interface BuildFallbackToolDocumentationOptions {
  toolName: string
  description?: string
  inputSchema?: ToolSchema
  outputSchema?: ToolSchema
  outputGlobs?: string[]
  labels: ToolDocumentationLabels
}

const UNSAFE_PROTOCOL_RE = /^\s*(javascript|data|vbscript):/i

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeHref(href: string): string {
  const trimmed = href.trim()
  if (!trimmed || UNSAFE_PROTOCOL_RE.test(trimmed)) {
    return '#'
  }
  return escapeHtml(trimmed)
}

function renderInline(text: string): string {
  const segments = text.split(/(`[^`]+`)/g)
  return segments.map(segment => {
    if (segment.startsWith('`') && segment.endsWith('`')) {
      return `<code>${escapeHtml(segment.slice(1, -1))}</code>`
    }

    let html = escapeHtml(segment)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
      return `<a href="${sanitizeHref(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
    })
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
    return html
  }).join('')
}

function renderList(lines: string[], startIndex: number): { html: string; nextIndex: number } {
  const items: string[] = []
  let index = startIndex
  while (index < lines.length) {
    const match = (lines[index] ?? '').match(/^\s*[-*]\s+(.+)$/)
    if (!match) {
      break
    }
    items.push(`<li>${renderInline(match[1] ?? '')}</li>`)
    index += 1
  }
  return {
    html: `<ul>${items.join('')}</ul>`,
    nextIndex: index
  }
}

function isTableSeparator(line?: string): boolean {
  if (!line) {
    return false
  }
  const cells = line.trim().split('|').filter(Boolean)
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell.trim()))
}

function parseTableCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim())
}

function renderTable(lines: string[], startIndex: number): { html: string; nextIndex: number } {
  const headers = parseTableCells(lines[startIndex] ?? '')
  const rows: string[][] = []
  let index = startIndex + 2

  while (index < lines.length) {
    const line = lines[index] ?? ''
    if (!line.includes('|') || !line.trim()) {
      break
    }
    rows.push(parseTableCells(line))
    index += 1
  }

  const thead = `<thead><tr>${headers.map(header => `<th>${renderInline(header)}</th>`).join('')}</tr></thead>`
  const tbody = rows.length
    ? `<tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${renderInline(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`
    : ''

  return {
    html: `<table>${thead}${tbody}</table>`,
    nextIndex: index
  }
}

function renderParagraph(lines: string[], startIndex: number): { html: string; nextIndex: number } {
  const parts: string[] = []
  let index = startIndex
  while (index < lines.length) {
    const line = lines[index] ?? ''
    if (
      !line.trim() ||
      line.startsWith('#') ||
      /^\s*[-*]\s+/.test(line) ||
      line.startsWith('```') ||
      (line.includes('|') && isTableSeparator(lines[index + 1]))
    ) {
      break
    }
    parts.push(line.trim())
    index += 1
  }

  return {
    html: `<p>${renderInline(parts.join(' '))}</p>`,
    nextIndex: index
  }
}

export function renderMarkdownToHtml(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index] ?? ''
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const language = trimmed.slice(3).trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !(lines[index] ?? '').trim().startsWith('```')) {
        codeLines.push(lines[index] ?? '')
        index += 1
      }
      if (index < lines.length) {
        index += 1
      }
      const className = language ? ` class="language-${escapeHtml(language)}"` : ''
      blocks.push(`<pre><code${className}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      const level = (heading[1] ?? '').length
      blocks.push(`<h${level}>${renderInline(heading[2] ?? '')}</h${level}>`)
      index += 1
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const rendered = renderList(lines, index)
      blocks.push(rendered.html)
      index = rendered.nextIndex
      continue
    }

    if (line.includes('|') && isTableSeparator(lines[index + 1])) {
      const rendered = renderTable(lines, index)
      blocks.push(rendered.html)
      index = rendered.nextIndex
      continue
    }

    const rendered = renderParagraph(lines, index)
    blocks.push(rendered.html)
    index = rendered.nextIndex
  }

  return blocks.join('\n')
}

function getPropertyType(prop: SchemaProperty): string {
  const rawType = Array.isArray(prop.type) ? prop.type.filter(type => type !== 'null').join(' | ') : prop.type
  if (prop.format === 'file' || prop.format === 'uri') {
    return 'file'
  }
  return rawType || prop.format || 'string'
}

function stringifyValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(', ')
  }
  if (value && typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function buildPropertyNote(prop: SchemaProperty, labels: ToolDocumentationLabels): string {
  const notes: string[] = []

  if (prop.description) {
    notes.push(prop.description)
  }
  if (prop.default !== undefined) {
    notes.push(`${labels.defaultValue}: ${stringifyValue(prop.default)}`)
  }
  if (prop.minimum !== undefined || prop.maximum !== undefined) {
    const min = prop.minimum !== undefined ? prop.minimum : ''
    const max = prop.maximum !== undefined ? prop.maximum : ''
    notes.push(`${labels.range}: ${min} - ${max}`)
  }
  if (prop.enum?.length) {
    notes.push(`${labels.type}: ${prop.enum.map(stringifyValue).join(', ')}`)
  }

  return notes.join('<br>')
}

function appendSchemaTable(
  lines: string[],
  schema: ToolSchema | undefined,
  labels: ToolDocumentationLabels,
  requiredKeys: string[] = []
) {
  if (!schema?.properties || Object.keys(schema.properties).length === 0) {
    lines.push(labels.noDocumentation)
    return
  }

  lines.push(`| ${labels.name} | ${labels.type} | ${labels.required} | ${labels.description} |`)
  lines.push('| --- | --- | --- | --- |')

  Object.entries(schema.properties).forEach(([key, prop]) => {
    if (prop.hidden) {
      return
    }
    const name = prop.title || key
    const required = requiredKeys.includes(key) ? labels.required : labels.optional
    lines.push(`| ${name} | ${getPropertyType(prop)} | ${required} | ${buildPropertyNote(prop, labels)} |`)
  })
}

export function buildFallbackToolDocumentation(options: BuildFallbackToolDocumentationOptions): string {
  const { labels } = options
  const lines: string[] = [
    `# ${options.toolName} ${labels.title}`,
    '',
    `## ${labels.overview}`,
    '',
    options.description?.trim() || labels.noDocumentation,
    '',
    `## ${labels.parameters}`,
    ''
  ]

  appendSchemaTable(lines, options.inputSchema, labels, options.inputSchema?.required || [])

  lines.push('', `## ${labels.outputs}`, '')
  appendSchemaTable(lines, options.outputSchema, labels, options.outputSchema?.required || [])

  if (options.outputGlobs?.length) {
    lines.push('', `## ${labels.outputPatterns}`, '')
    options.outputGlobs.forEach(pattern => {
      lines.push(`- \`${pattern}\``)
    })
  }

  return lines.join('\n')
}
