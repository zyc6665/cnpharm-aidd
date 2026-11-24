import { computed, reactive } from 'vue'
import { message } from 'ant-design-vue'

/**
 * 全局下载记录（本次会话）。
 *
 * 背景：下载过去散落在二十多个组件里，各自「建 <a> → click → 删掉」，
 * 用户点完按钮看不到任何反馈——成功与否全靠浏览器下载栏，失败时有的组件还会吞掉异常。
 * 这里把每一次下载登记成一条记录（准备中 / 已开始 / 失败），侧栏「下载」入口展示它们，
 * 失败的记录可以一键重试。
 *
 * 只登记、不发请求：真正的下载仍由 `protected-file-access.ts` 完成，
 * 它在开始、成功、失败三个时点调用这里的函数。记录只存在内存里，刷新即清空
 * （跨会话的下载历史需要后端支持，不在前端范围）。
 */
export type DownloadStatus = 'pending' | 'done' | 'error'

export interface DownloadRecord {
  id: number
  filename: string
  status: DownloadStatus
  startedAt: number
  finishedAt?: number
  error?: string
  retry?: () => Promise<void>
}

const MAX_RECORDS = 50

const state = reactive({
  records: [] as DownloadRecord[],
})

let nextId = 1

function findRecord(id: number): DownloadRecord | undefined {
  return state.records.find(record => record.id === id)
}

export function beginDownloadRecord(filename: string, retry?: () => Promise<void>): number {
  const id = nextId++
  state.records.unshift({
    id,
    filename: filename || 'download',
    status: 'pending',
    startedAt: Date.now(),
    retry,
  })
  if (state.records.length > MAX_RECORDS) {
    state.records.splice(MAX_RECORDS)
  }
  return id
}

export function completeDownloadRecord(id: number): void {
  const record = findRecord(id)
  if (!record) return
  record.status = 'done'
  record.finishedAt = Date.now()
  record.error = undefined
}

export function failDownloadRecord(id: number, cause: unknown): void {
  const record = findRecord(id)
  if (!record) return
  record.status = 'error'
  record.finishedAt = Date.now()
  record.error = cause instanceof Error ? cause.message : String(cause ?? '')
}

export function removeDownloadRecord(id: number): void {
  const index = state.records.findIndex(record => record.id === id)
  if (index >= 0) state.records.splice(index, 1)
}

export function clearFinishedDownloadRecords(): void {
  state.records = state.records.filter(record => record.status === 'pending')
}

/** 包一层：开始登记 → 轻提示 → 执行 → 成功/失败落状态；异常继续抛给调用方，保持原有错误处理不变。 */
export async function trackDownload(filename: string, run: () => Promise<void>): Promise<void> {
  const id = beginDownloadRecord(filename, () => trackDownload(filename, run))
  try {
    message.info(`开始下载：${filename}`)
  } catch {
    // 非浏览器/测试环境忽略提示异常
  }
  try {
    await run()
    completeDownloadRecord(id)
  } catch (cause) {
    failDownloadRecord(id, cause)
    throw cause
  }
}

export function useDownloadHistory() {
  const records = computed(() => state.records)
  const pendingCount = computed(() => state.records.filter(record => record.status === 'pending').length)
  const errorCount = computed(() => state.records.filter(record => record.status === 'error').length)
  return {
    records,
    pendingCount,
    errorCount,
    remove: removeDownloadRecord,
    clearFinished: clearFinishedDownloadRecords,
  }
}

/** 测试用：重置模块状态。 */
export function resetDownloadHistoryForTest(): void {
  state.records = []
  nextId = 1
}
