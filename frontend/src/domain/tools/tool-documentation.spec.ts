import { describe, expect, it } from 'vitest'
import { renderMarkdownToHtml } from './tool-documentation'

function renderLink(href: string, label = 'link'): string {
  return renderMarkdownToHtml(`[${label}](${href})`)
}

function extractHref(html: string): string | null {
  return /href="([^"]*)"/.exec(html)?.[1] ?? null
}

describe('tool documentation link sanitization', () => {
  it.each([
    ['https://example.com/docs', 'https://example.com/docs'],
    ['http://example.com/docs', 'http://example.com/docs'],
    ['mailto:docs@example.com', 'mailto:docs@example.com'],
    ['/docs/getting-started', '/docs/getting-started'],
    ['#parameters', '#parameters'],
    ['?tab=examples', '?tab=examples'],
    ['./guide.md', './guide.md'],
    ['../overview', '../overview'],
  ])('allows safe href %s', (href, expected) => {
    expect(extractHref(renderLink(href))).toBe(expected)
  })

  it.each([
    'javascript:alert(1)',
    'java\tscript:alert(1)',
    'java\rscript:alert(1)',
    'data:text/html;base64,PHNjcmlwdD4=',
    'vbscript:msgbox',
    'JavaScript:alert(1)',
    ' \u0000\u001f javascript:alert(1)',
    '&#x6a;avascript:alert(1)',
    'file:///etc/passwd',
    'blob:https://example.com/550e8400-e29b-41d4-a716-446655440000',
    'relative/page',
  ])('rejects unsafe href %j', href => {
    expect(extractHref(renderLink(href))).toBe('#')
  })

  it('neutralizes a newline-obfuscated scheme to #', () => {
    const html = renderMarkdownToHtml('[link](java\nscript:alert(1))')

    expect(extractHref(html)).toBe('#')
    expect(html).not.toContain('href="javascript:')
  })

  it('keeps escaping other markup when rendering links', () => {
    const html = renderMarkdownToHtml(
      '<script>alert(1)</script>\n\n[<b>label</b>](https://example.com)'
    )

    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).not.toContain('<b>')
    expect(html).toContain('&amp;lt;b&amp;gt;label&amp;lt;/b&amp;gt;')
    expect(html).toContain('href="https://example.com"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })
})
