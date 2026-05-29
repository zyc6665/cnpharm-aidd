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
  fetchBlob?: (url: string, token: string) => Promise<Blob>
  fetchText?: (url: string, token: string) => Promise<string>
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

function getStoredToken(): string | null {
  return typeof localStorage === 'undefined' ? null : localStorage.getItem('cpumodel_token')
}

async function fetchProtectedFileBlob(url: string, token: string): Promise<Blob> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `文件访问失败 (${response.status})`)
  }

  return await response.blob()
}

async function fetchProtectedTextContent(url: string, token: string): Promise<string> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `文件访问失败 (${response.status})`)
  }

  return await response.text()
}

function resolveDownloadName(file: ProtectedFileReference): string {
  return file.original_name || file.filename || 'download'
}

function resolveProtectedToken(
  dependencies: ProtectedFileAccessDependencies = {}
): string {
  const token = (dependencies.getToken || getStoredToken)()
  if (!token) {
    throw new Error('需要登录后才能访问此文件')
  }

  return token
}

function isBrowserObjectUrl(url: string): boolean {
  return url.startsWith('blob:') || url.startsWith('data:')
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

  const token = resolveProtectedToken(dependencies)

  const blob = await (dependencies.fetchBlob || fetchProtectedFileBlob)(fileUrl, token)
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
  const token = resolveProtectedToken(dependencies)
  return await (dependencies.fetchText || fetchProtectedTextContent)(fileUrl, token)
}

export async function triggerProtectedFileDownload(
  file: ProtectedFileReference,
  dependencies: ProtectedFileAccessDependencies = {}
): Promise<void> {
  if (!file.url) {
    throw new Error('缺少文件下载地址')
  }

  const resource = await createProtectedObjectUrl(file.url, dependencies)
  const dom = dependencies.dom || defaultDownloadDomApi
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
