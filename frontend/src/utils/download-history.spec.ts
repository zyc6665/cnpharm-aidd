import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearFinishedDownloadRecords,
  removeDownloadRecord,
  resetDownloadHistoryForTest,
  trackDownload,
  useDownloadHistory,
} from './download-history'

describe('download-history', () => {
  beforeEach(() => {
    resetDownloadHistoryForTest()
  })

  it('tracks successful downloads from pending to done', async () => {
    const { records, pendingCount, errorCount } = useDownloadHistory()
    let resolveRun!: () => void
    const promise = trackDownload(
      'result.sdf',
      () =>
        new Promise<void>(resolve => {
          resolveRun = resolve
        })
    )

    expect(records.value).toHaveLength(1)
    expect(records.value[0]?.status).toBe('pending')
    expect(pendingCount.value).toBe(1)

    resolveRun()
    await promise

    expect(records.value[0]?.status).toBe('done')
    expect(pendingCount.value).toBe(0)
    expect(errorCount.value).toBe(0)
  })

  it('records failed downloads, rethrows the error, and supports retry', async () => {
    const { records, errorCount } = useDownloadHistory()
    let attempts = 0
    const run = vi.fn(async () => {
      attempts += 1
      if (attempts === 1) throw new Error('network failed')
    })

    await expect(trackDownload('report.pdf', run)).rejects.toThrow('network failed')
    expect(records.value[0]?.status).toBe('error')
    expect(records.value[0]?.error).toBe('network failed')
    expect(errorCount.value).toBe(1)

    const retry = records.value[0]?.retry
    removeDownloadRecord(records.value[0]!.id)
    await retry?.()

    expect(records.value[0]?.status).toBe('done')
    expect(errorCount.value).toBe(0)
  })

  it('clears finished records while keeping pending ones', async () => {
    const { records } = useDownloadHistory()
    await trackDownload('done.csv', async () => undefined)
    void trackDownload('pending.csv', () => new Promise<void>(() => undefined))

    expect(records.value).toHaveLength(2)
    clearFinishedDownloadRecords()
    expect(records.value).toHaveLength(1)
    expect(records.value[0]?.filename).toBe('pending.csv')
  })
})
