export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Clipboard API can be unavailable on intranet HTTP pages.
    }
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.readOnly = true
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  const active = document.activeElement
  const container = active?.closest('[role="dialog"]') ?? document.body
  container.appendChild(textarea)
  try {
    textarea.select()
    if (!document.execCommand('copy')) throw new Error('Copy failed')
  } finally {
    textarea.remove()
    if (active instanceof HTMLElement) active.focus()
  }
}
