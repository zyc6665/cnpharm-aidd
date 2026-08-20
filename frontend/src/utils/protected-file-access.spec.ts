import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/api/request'
import { createProtectedObjectUrl, fetchProtectedFileText } from './protected-file-access'

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
    localStorage.setItem('cpumodel_token', 'access-token')
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

    expect(requestGet).toHaveBeenCalledWith('/files/file-1/download', {
      headers: { Authorization: 'Bearer access-token' },
      responseType: 'blob',
      silent: true,
    })
    expect(resource.url).toBe(objectUrl)
  })

  it('loads protected text through the authenticated request layer', async () => {
    requestGet.mockResolvedValue('score,pose\n-7.3,ligand.sdf')

    const text = await fetchProtectedFileText('/api/v1/files/score-file/download')

    expect(requestGet).toHaveBeenCalledWith('/files/score-file/download', {
      headers: { Authorization: 'Bearer access-token' },
      responseType: 'text',
      silent: true,
    })
    expect(text).toContain('score,pose')
  })
})
