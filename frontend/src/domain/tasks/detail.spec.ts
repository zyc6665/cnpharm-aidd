import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  formatTaskDetailTime,
  formatTaskFileSize,
  getTaskCompletedTitleKey
} from './detail'

test('任务详情时间格式保持页面展示格式', () => {
  assert.equal(formatTaskDetailTime('2026-08-05T02:30:00Z'), '2026-08-05 02:30:00')
})

test('任务详情文件大小格式支持空值、B、KB、MB 和 GB', () => {
  assert.equal(formatTaskFileSize(undefined), '0 B')
  assert.equal(formatTaskFileSize(0), '0 B')
  assert.equal(formatTaskFileSize(512), '512 B')
  assert.equal(formatTaskFileSize(1536), '1.5 KB')
  assert.equal(formatTaskFileSize(1024 * 1024), '1 MB')
  assert.equal(formatTaskFileSize(1024 * 1024 * 1024), '1 GB')
})

test('任务完成标题 key 由终态决定，非终态回退 completed', () => {
  assert.equal(getTaskCompletedTitleKey('success'), 'tasks.completed')
  assert.equal(getTaskCompletedTitleKey('failure'), 'tasks.failed')
  assert.equal(getTaskCompletedTitleKey('canceled'), 'tasks.canceled')
  assert.equal(getTaskCompletedTitleKey('running'), 'tasks.completed')
})
