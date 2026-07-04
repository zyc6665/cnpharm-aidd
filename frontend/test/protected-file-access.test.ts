import test from 'node:test'
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

test('triggerProtectedFileDownload 应通过 blob URL 触发下载而不是直接打开受保护接口', async () => {
  const clicks: Array<{ href: string; download: string }> = []
  const appended: string[] = []
  const removed: string[] = []
  const revoked: string[] = []

  await triggerProtectedFileDownload(
    {
      url: '/api/v1/files/file-2/download',
      original_name: 'generated_molecules.sdf'
    },
    {
      getToken: () => 'token-abc',
      fetchBlob: async () => new Blob(['sdf']),
      objectUrl: {
        createObjectURL() {
          return 'blob:download-1'
        },
        revokeObjectURL(url) {
          revoked.push(url)
        }
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

  assert.deepEqual(clicks, [{ href: 'blob:download-1', download: 'generated_molecules.sdf' }])
  assert.deepEqual(appended, ['generated_molecules.sdf'])
  assert.deepEqual(removed, ['generated_molecules.sdf'])
  assert.deepEqual(revoked, ['blob:download-1'])
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

test('fetchProtectedFileText 应在无登录令牌时使用游客会话头', async () => {
  let requestedUrl = ''
  let requestedHeaders: Record<string, string> | undefined

  const text = await fetchProtectedFileText('/api/v1/files/file-5/download', {
    getToken: () => null,
    getGuestSession: () => 'guest-session-123',
    fetchText: async (url, headers) => {
      requestedUrl = url
      requestedHeaders = headers
      return 'guest file'
    }
  })

  assert.equal(requestedUrl, '/api/v1/files/file-5/download')
  assert.deepEqual(requestedHeaders, { 'X-Guest-Session': 'guest-session-123' })
  assert.equal(text, 'guest file')
})
