import { getToken as getStoredToken } from './auth-storage.ts'
import request, { type RequestOptions } from '@/api/request'

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
  getToken?: () => string | null
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

function resolveProtectedAuthHeaders(
  dependencies: ProtectedFileAccessDependencies = {}
): Record<string, string> {
  const token = (dependencies.getToken || getStoredToken)()
  if (token) {
    return { Authorization: `Bearer ${token}` }
  }

  throw new Error('需要登录后才能访问此文件')
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

  const headers = resolveProtectedAuthHeaders(dependencies)

  const blob = await (dependencies.fetchBlob || fetchProtectedFileBlob)(fileUrl, headers)
  const objectUrlApi = dependencies.objectUrl || defaultObjectUrlApi
  const objectUrl = objectUrlApi.createObjectURL(blob)

  return {
    url: objectUrl,
    revoke: () => objectUrlApi.revokeObjectURL(objectUrl)
  }
}

export async function fetchProtectedFileText(
  fileUrl: string,
  dependencies: ProtectedFileAccessDependencies = {}
): Promise<string> {
  const headers = resolveProtectedAuthHeaders(dependencies)
  return await (dependencies.fetchText || fetchProtectedTextContent)(fileUrl, headers)
}

export async function triggerProtectedFileDownload(
  file: ProtectedFileReference,
  dependencies: ProtectedFileAccessDependencies = {}
): Promise<void> {
  if (!file.url) {
    throw new Error('缺少文件下载地址')
  }

  const dom = dependencies.dom || defaultDownloadDomApi
  const fileId = resolveProtectedFileId(file.url)

  if (fileId) {
    try {
      const headers = resolveProtectedAuthHeaders(dependencies)
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
    }
  }

  const resource = await createProtectedObjectUrl(file.url, dependencies)
  const anchor = dom.createAnchor()

  try {
    anchor.href = resource.url
    anchor.download = resolveDownloadName(file)
    dom.appendAnchor(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    resource.revoke()
  }
}
