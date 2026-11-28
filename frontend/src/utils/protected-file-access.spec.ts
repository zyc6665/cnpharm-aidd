import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/api/request'
import {
  createProtectedObjectUrl,
  fetchProtectedFileText,
  triggerProtectedFileDownload
} from './protected-file-access'

vi.mock('@/api/request', () => ({
  default: {
    get: vi.fn(),
  },
}))

const requestGet = vi.mocked(request.get)

describe('protected-file-access', () => {
  beforeEach(() => {
    requestGet.mockReset()
    localStorage.clear()
  })

  it('downloads protected blobs through the authenticated request layer', async () => {
    const blob = new Blob(['PDB'], { type: 'chemical/x-pdb' })
    const objectUrl = 'blob:protected-file'
    requestGet.mockResolvedValue(blob)

    const resource = await createProtectedObjectUrl('/api/v1/files/file-1/download', {
      objectUrl: {
        createObjectURL: vi.fn(() => objectUrl),
        revokeObjectURL: vi.fn(),
      },
    })

    // 认证依赖 httpOnly Cookie：不再附带 Authorization 头
    expect(requestGet).toHaveBeenCalledWith('/files/file-1/download', {
      headers: {},
      responseType: 'blob',
      silent: true,
    })
    expect(resource.url).toBe(objectUrl)
  })

  it('loads protected text through the authenticated request layer', async () => {
    requestGet.mockResolvedValue('score,pose\n-7.3,ligand.sdf')

    const text = await fetchProtectedFileText('/api/v1/files/score-file/download')

    expect(requestGet).toHaveBeenCalledWith('/files/score-file/download', {
      headers: {},
      responseType: 'text',
      silent: true,
    })
    expect(text).toContain('score,pose')
  })

  it('does not read a token from localStorage', async () => {
    localStorage.setItem('cpumodel_token', 'legacy-token')
    requestGet.mockResolvedValue(new Blob(['mol']))

    await createProtectedObjectUrl('/api/v1/files/file-2/download', {
      objectUrl: {
        createObjectURL: () => 'blob:x',
        revokeObjectURL: () => undefined,
      },
    })

    const config = requestGet.mock.calls[0]?.[1]
    expect(config?.headers).toEqual({})
  })

  it('requests a short-lived download url without auth headers', async () => {
    const clicks: Array<{ href: string; download: string }> = []
    requestGet.mockResolvedValue({ data: { url: 'https://signed.example/file' } })

    await triggerProtectedFileDownload(
      { url: '/api/v1/files/file-3/download', original_name: 'a.sdf' },
      {
        dom: {
          appendAnchor: () => undefined,
          createAnchor: () => ({
            href: '',
            download: '',
            click() {
              clicks.push({ href: this.href, download: this.download })
            },
            remove: () => undefined,
          }),
        },
      }
    )

    expect(requestGet).toHaveBeenCalledWith('/files/file-3/download-url', {
      params: { expires_in: 300 },
      headers: {},
      silent: true,
    })
    expect(clicks).toEqual([{ href: 'https://signed.example/file', download: 'a.sdf' }])
  })

  it('requireContent skips the presigned url and downloads the protected body', async () => {
    const clicks: Array<{ href: string; download: string }> = []
    const revokeObjectURL = vi.fn()
    requestGet.mockResolvedValue(new Blob(['MODEL'], { type: 'chemical/x-pdb' }))

    await triggerProtectedFileDownload(
      { url: '/api/v1/files/file-4/download', filename: 'trajectory_movie.pdb' },
      {
        dom: {
          appendAnchor: () => undefined,
          createAnchor: () => ({
            href: '',
            download: '',
            click() {
              clicks.push({ href: this.href, download: this.download })
            },
            remove: () => undefined,
          }),
        },
        objectUrl: {
          createObjectURL: () => 'blob:movie',
          revokeObjectURL,
        },
      },
      { requireContent: true }
    )

    expect(requestGet).toHaveBeenCalledTimes(1)
    expect(requestGet).toHaveBeenCalledWith('/files/file-4/download', {
      headers: {},
      responseType: 'blob',
      silent: true,
    })
    expect(clicks).toEqual([{ href: 'blob:movie', download: 'trajectory_movie.pdb' }])
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:movie')
  })

  it('requireContent rejects an empty body without starting a download', async () => {
    const click = vi.fn()
    requestGet.mockResolvedValue(new Blob([], { type: 'chemical/x-pdb' }))

    await expect(
      triggerProtectedFileDownload(
        { url: '/api/v1/files/file-5/download', filename: 'trajectory_movie.pdb' },
        {
          dom: {
            appendAnchor: () => undefined,
            createAnchor: () => ({ href: '', download: '', click, remove: () => undefined }),
          },
          objectUrl: {
            createObjectURL: () => 'blob:empty',
            revokeObjectURL: vi.fn(),
          },
        },
        { requireContent: true }
      )
    ).rejects.toThrow('下载内容为空')
    expect(click).not.toHaveBeenCalled()
  })
})
