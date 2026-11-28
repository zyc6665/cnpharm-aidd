import request, { type RequestOptions } from '@/api/request'
import { trackDownload } from '@/utils/download-history'

interface ObjectUrlApi {
  createObjectURL(blob: Blob): string
  revokeObjectURL(url: string): void
}

interface DownloadAnchor {
  href: string
  download: string
  click(): void
  remove(): void
}

interface DownloadDomApi {
  createAnchor(): DownloadAnchor
  appendAnchor(anchor: DownloadAnchor): void
}

interface ProtectedFileAccessDependencies {
  dom?: DownloadDomApi
  fetchBlob?: (url: string, headers: Record<string, string>) => Promise<Blob>
  fetchText?: (url: string, headers: Record<string, string>) => Promise<string>
  fetchDownloadUrl?: (fileId: string, headers: Record<string, string>) => Promise<string>
  objectUrl?: ObjectUrlApi
}

interface ProtectedFileReference {
  url?: string
  filename?: string
  original_name?: string
}

interface ProtectedObjectUrlResource {
  url: string
  revoke: () => void
  /** 受保护请求读到的字节数；浏览器本地对象地址（blob:/data:）无法预知时为 undefined。 */
  size?: number
}

export interface ProtectedFileDownloadOptions {
  /**
   * 为 true 时跳过预签名直链，改用受保护请求读取完整内容：
   * 预签名地址只证明「拿到了 URL」，不证明对象存在；对必须确认可读的产物
   * （如 PDB-movie 影片，可能是上一次失败残留的空文件）要验证实际响应。
   */
  requireContent?: boolean
}

const API_PREFIX = '/api/v1'

const defaultObjectUrlApi: ObjectUrlApi = {
  createObjectURL(blob) {
    return URL.createObjectURL(blob)
  },
  revokeObjectURL(url) {
    URL.revokeObjectURL(url)
  }
}

const defaultDownloadDomApi: DownloadDomApi = {
  createAnchor() {
    return document.createElement('a')
  },
  appendAnchor(anchor) {
    document.body.appendChild(anchor as HTMLAnchorElement)
  }
}

function normalizeProtectedRequestUrl(url: string): string {
  try {
    const parsedUrl = new URL(url, typeof window === 'undefined' ? 'http://localhost' : window.location.origin)
    if (parsedUrl.pathname.startsWith(API_PREFIX)) {
      return `${parsedUrl.pathname.slice(API_PREFIX.length) || '/'}${parsedUrl.search}${parsedUrl.hash}`
    }
  } catch {
    if (url.startsWith(API_PREFIX)) {
      return url.slice(API_PREFIX.length) || '/'
    }
  }

  return url
}

async function fetchProtectedFileBlob(url: string, headers: Record<string, string>): Promise<Blob> {
  const config: RequestOptions = {
    headers,
    responseType: 'blob',
    silent: true,
  }

  return await request.get(normalizeProtectedRequestUrl(url), config) as unknown as Blob
}

async function fetchProtectedTextContent(url: string, headers: Record<string, string>): Promise<string> {
  const config: RequestOptions = {
    headers,
    responseType: 'text',
    silent: true,
  }

  return await request.get(normalizeProtectedRequestUrl(url), config) as unknown as string
}

function resolveDownloadName(file: ProtectedFileReference): string {
  return file.original_name || file.filename || 'download'
}

function resolveProtectedAuthHeaders(): Record<string, string> {
  // 认证由 httpOnly Cookie 承载，请求会自动携带；这里不再拼 Authorization。
  return {}
}

function isBrowserObjectUrl(url: string): boolean {
  return url.startsWith('blob:') || url.startsWith('data:')
}

export function isProtectedFileDownloadUrl(url: string): boolean {
  try {
    const pathname = new URL(url, window.location.origin).pathname
    return /^\/api\/v1\/files\/[^/]+\/download$/.test(pathname)
  } catch {
    return /^\/api\/v1\/files\/[^/]+\/download$/.test(url)
  }
}

function resolveProtectedFileId(url: string): string | null {
  try {
    const pathname = new URL(
      url,
      typeof window === 'undefined' ? 'http://localhost' : window.location.origin
    ).pathname
    const match = pathname.match(/^\/api\/v1\/files\/([^/]+)\/download$/)
    return match?.[1] ? decodeURIComponent(match[1]) : null
  } catch {
    const match = url.match(/^\/api\/v1\/files\/([^/]+)\/download(?:\?|#|$)/)
    return match?.[1] ? decodeURIComponent(match[1]) : null
  }
}

async function fetchProtectedDownloadUrl(
  fileId: string,
  headers: Record<string, string>
): Promise<string> {
  const config: RequestOptions = {
    params: { expires_in: 300 },
    headers,
    silent: true,
  }
  const response = await request.get(
    `/files/${encodeURIComponent(fileId)}/download-url`,
    config
  ) as unknown as { data?: { url?: string } }
  const url = response.data?.url
  if (!url) {
    throw new Error('未获取到文件下载地址')
  }
  return url
}

export async function createProtectedObjectUrl(
  fileUrl: string,
  dependencies: ProtectedFileAccessDependencies = {}
): Promise<ProtectedObjectUrlResource> {
  if (isBrowserObjectUrl(fileUrl)) {
    return {
      url: fileUrl,
      revoke: () => undefined
    }
  }

  const headers = resolveProtectedAuthHeaders()

  const blob = await (dependencies.fetchBlob || fetchProtectedFileBlob)(fileUrl, headers)
  const objectUrlApi = dependencies.objectUrl || defaultObjectUrlApi
  const objectUrl = objectUrlApi.createObjectURL(blob)

  return {
    url: objectUrl,
    revoke: () => objectUrlApi.revokeObjectURL(objectUrl),
    size: blob.size
  }
}

export async function fetchProtectedFileText(
  fileUrl: string,
  dependencies: ProtectedFileAccessDependencies = {}
): Promise<string> {
  const headers = resolveProtectedAuthHeaders()
  return await (dependencies.fetchText || fetchProtectedTextContent)(fileUrl, headers)
}

/**
 * 所有受保护文件下载的唯一出口。每次调用都会登记进全局下载记录
 * （`download-history.ts`），侧栏「下载」入口可以看到状态并重试失败项；
 * 异常仍然抛给调用方，各页面原有的错误提示保持不变。
 *
 * `options.requireContent` 用于必须确认「文件真的可读」的产物（如影片）：
 * 跳过无法证明对象存在的预签名直链，并在内容为空时按失败处理。
 */
export async function triggerProtectedFileDownload(
  file: ProtectedFileReference,
  dependencies: ProtectedFileAccessDependencies = {},
  options: ProtectedFileDownloadOptions = {}
): Promise<void> {
  await trackDownload(resolveDownloadName(file), () =>
    performProtectedFileDownload(file, dependencies, options)
  )
}

async function performProtectedFileDownload(
  file: ProtectedFileReference,
  dependencies: ProtectedFileAccessDependencies,
  options: ProtectedFileDownloadOptions = {}
): Promise<void> {
  if (!file.url) {
    throw new Error('缺少文件下载地址')
  }

  const dom = dependencies.dom || defaultDownloadDomApi
  // 预签名直链只回 URL，不验证对象是否存在；需要校验内容时走受保护读取。
  const fileId = options.requireContent ? null : resolveProtectedFileId(file.url)

  if (fileId) {
    try {
      const headers = resolveProtectedAuthHeaders()
      const downloadUrl = await (dependencies.fetchDownloadUrl || fetchProtectedDownloadUrl)(fileId, headers)
      const anchor = dom.createAnchor()
      try {
        anchor.href = downloadUrl
        anchor.download = resolveDownloadName(file)
        dom.appendAnchor(anchor)
        anchor.click()
      } finally {
        anchor.remove()
      }
      return
    } catch {
      // 预签名地址拿不到（旧文件、权限边界等）时退回到带 Cookie 的 blob 下载；
      // 兜底再失败会抛出，由下载记录和调用方共同呈现，不再静默。
    }
  }

  const resource = await createProtectedObjectUrl(file.url, dependencies)

  try {
    if (options.requireContent) {
      // blob:/data: 地址不经过受保护请求，拿不到字节数：空 data: URL 也能走到
      // 这里。requireContent 的语义是「确认内容真实可读」，无法证明就按失败处理。
      if (resource.size === undefined) {
        throw new Error('无法验证下载内容')
      }
      if (resource.size === 0) {
        throw new Error('下载内容为空')
      }
    }
    const anchor = dom.createAnchor()
    try {
      anchor.href = resource.url
      anchor.download = resolveDownloadName(file)
      dom.appendAnchor(anchor)
      anchor.click()
    } finally {
      anchor.remove()
    }
  } finally {
    resource.revoke()
  }
}

/**
 * 前端本地生成内容（CSV、报告 JSON 等）的下载出口，同样登记进下载记录。
 * 页面不要再自己 `createObjectURL` + 建 `<a>`。
 */
export async function saveBlobAsFile(
  content: Blob | string,
  filename: string,
  mimeType = 'text/plain;charset=utf-8',
  dependencies: Pick<ProtectedFileAccessDependencies, 'dom' | 'objectUrl'> = {}
): Promise<void> {
  await trackDownload(filename, async () => {
    const blob = typeof content === 'string' ? new Blob([content], { type: mimeType }) : content
    const objectUrlApi = dependencies.objectUrl || defaultObjectUrlApi
    const dom = dependencies.dom || defaultDownloadDomApi
    const url = objectUrlApi.createObjectURL(blob)
    const anchor = dom.createAnchor()
    try {
      anchor.href = url
      anchor.download = filename
      dom.appendAnchor(anchor)
      anchor.click()
    } finally {
      anchor.remove()
      // 部分浏览器在 click 之后才真正开始读取 blob，延后释放避免下载到空文件。
      setTimeout(() => objectUrlApi.revokeObjectURL(url), 0)
    }
  })
}
