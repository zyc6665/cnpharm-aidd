import { describe, expect, it, vi } from 'vitest'
import { createNormalizedSdfObjectUrl, normalizeSdfRecord, splitSdfRecords } from './sdf-result'

describe('SDF record parsing and selection', () => {
  it('splits only delimiter lines and preserves blank headers, CRLF, and final unterminated record', () => {
    const text = '\r\n  title\r\nprogram\r\ncomment\r\n  1  0  0  0  0  0            999 V2000\r\n$$$$\r\nother\nprogram\ncomment\n  1  0  0  0  0  0            999 V2000'
    const records = splitSdfRecords(text)
    expect(records).toHaveLength(2)
    expect(records[0]).toContain('\n  title\n')
    expect(records[1]).toContain('other\n')
    expect(normalizeSdfRecord(records[0]!)).toContain('  1  0  0  0  0  0            999 V2000')
  })

  it('normalizes only the requested record and rejects invalid indexes without fallback', async () => {
    const createObjectURL = vi.fn((_blob: Blob) => 'blob:selected')
    const revokeObjectURL = vi.fn()
    const resource = await createNormalizedSdfObjectUrl('local', {
      fetchText: async () => 'first\n$$$$\nsecond', recordIndex: 1,
      objectUrl: { createObjectURL, revokeObjectURL },
    })
    expect(createObjectURL.mock.calls[0]?.[0]).toBeInstanceOf(Blob)
    await expect(createNormalizedSdfObjectUrl('local', {
      fetchText: async () => 'first', recordIndex: 1,
      objectUrl: { createObjectURL, revokeObjectURL },
    })).rejects.toThrow('SDF record index 1 is unavailable')
    resource.revoke()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:selected')
  })
})
