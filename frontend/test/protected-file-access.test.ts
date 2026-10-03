import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  createProtectedObjectUrl,
  fetchProtectedFileText,
  triggerProtectedFileDownload
} from '../src/utils/protected-file-access.ts'

test('createProtectedObjectUrl 应使用登录令牌拉取受保护文件并返回可撤销 blob URL', async () => {
  let requestedUrl = ''
  let requestedHeaders: Record<string, string> | undefined
  let revokedUrl = ''

  const blob = new Blob(['mol'])

  const resource = await createProtectedObjectUrl('/api/v1/files/file-1/download', {
    getToken: () => 'token-123',
    fetchBlob: async (url, headers) => {
      requestedUrl = url
      requestedHeaders = headers
      return blob
    },
    objectUrl: {
      createObjectURL(value) {
        assert.equal(value, blob)
        return 'blob:viewer-1'
      },
      revokeObjectURL(url) {
        revokedUrl = url
      }
    }
  })

  assert.equal(requestedUrl, '/api/v1/files/file-1/download')
  assert.deepEqual(requestedHeaders, { Authorization: 'Bearer token-123' })
  assert.equal(resource.url, 'blob:viewer-1')

  resource.revoke()
  assert.equal(revokedUrl, 'blob:viewer-1')
})

test('triggerProtectedFileDownload 应优先获取短时效 URL 后触发原生下载', async () => {
  const clicks: Array<{ href: string; download: string }> = []
  const appended: string[] = []
  const removed: string[] = []
  let requestedFileId = ''
  let requestedHeaders: Record<string, string> | undefined

  await triggerProtectedFileDownload(
    {
      url: '/api/v1/files/file-2/download',
      original_name: 'generated_molecules.sdf'
    },
    {
      getToken: () => 'token-abc',
      fetchDownloadUrl: async (fileId, headers) => {
        requestedFileId = fileId
        requestedHeaders = headers
        return '/api/v1/files/file-2/download?token=short-lived'
      },
      dom: {
        appendAnchor(anchor) {
          appended.push(anchor.download)
        },
        createAnchor() {
          return {
            href: '',
            download: '',
            click() {
              clicks.push({ href: this.href, download: this.download })
            },
            remove() {
              removed.push(this.download)
            }
          }
        }
      }
    }
  )

  assert.equal(requestedFileId, 'file-2')
  assert.deepEqual(requestedHeaders, { Authorization: 'Bearer token-abc' })
  assert.deepEqual(clicks, [{ href: '/api/v1/files/file-2/download?token=short-lived', download: 'generated_molecules.sdf' }])
  assert.deepEqual(appended, ['generated_molecules.sdf'])
  assert.deepEqual(removed, ['generated_molecules.sdf'])
})

test('triggerProtectedFileDownload 在短时效 URL 不可用时回退到 Blob 下载', async () => {
  const clicks: Array<{ href: string; download: string }> = []
  const revoked: string[] = []

  await triggerProtectedFileDownload(
    {
      url: '/api/v1/files/file-legacy/download',
      original_name: 'legacy.sdf'
    },
    {
      getToken: () => 'token-legacy',
      fetchDownloadUrl: async () => {
        throw new Error('旧后端不支持短时效下载地址')
      },
      fetchBlob: async () => new Blob(['sdf']),
      objectUrl: {
        createObjectURL() {
          return 'blob:legacy-download'
        },
        revokeObjectURL(url) {
          revoked.push(url)
        }
      },
      dom: {
        appendAnchor() {},
        createAnchor() {
          return {
            href: '',
            download: '',
            click() {
              clicks.push({ href: this.href, download: this.download })
            },
            remove() {}
          }
        }
      }
    }
  )

  assert.deepEqual(clicks, [{ href: 'blob:legacy-download', download: 'legacy.sdf' }])
  assert.deepEqual(revoked, ['blob:legacy-download'])
})

test('createProtectedObjectUrl 在缺少登录令牌时应直接失败', async () => {
  await assert.rejects(
    () =>
      createProtectedObjectUrl('/api/v1/files/file-3/download', {
        getToken: () => null
      }),
    /登录/
  )
})

test('fetchProtectedFileText 应使用登录令牌拉取受保护文本文件', async () => {
  let requestedUrl = ''
  let requestedHeaders: Record<string, string> | undefined

  const text = await fetchProtectedFileText('/api/v1/files/file-4/download', {
    getToken: () => 'token-text',
    fetchText: async (url, headers) => {
      requestedUrl = url
      requestedHeaders = headers
      return 'SMILES,score\\nCCO,0.8\\n'
    }
  })

  assert.equal(requestedUrl, '/api/v1/files/file-4/download')
  assert.deepEqual(requestedHeaders, { Authorization: 'Bearer token-text' })
  assert.equal(text, 'SMILES,score\\nCCO,0.8\\n')
})

test('fetchProtectedFileText 应在无登录令牌时拒绝访问', async () => {
  await assert.rejects(
    () => fetchProtectedFileText('/api/v1/files/file-5/download', { getToken: () => null }),
    /需要登录后才能访问此文件/
  )
})
