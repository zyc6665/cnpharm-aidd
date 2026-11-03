import { describe, expect, it } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (relativePath: string) =>
  readFileSync(resolve(rootDir, relativePath), 'utf8')

describe('任务详情页取消/重试动作按权限渲染', () => {
  it('取消与重试都改用 canCancelTask / canRetryTask 判断', () => {
    const source = readSource('src/views/tasks/Detail.vue')

    assert.equal(source.includes('canCancelTask'), true)
    assert.equal(source.includes('canRetryTask'), true)
    assert.equal(source.includes('taskActor'), true)

    // 模板：按钮由权限计算属性守卫，而不是只看状态
    assert.equal(source.includes('v-if="canCancel"'), true)
    assert.equal(source.includes('v-if="canRetry"'), true)
  })

  it('取消/重试不再仅按状态直接渲染（viewer 也能看到的旧逻辑已移除）', () => {
    const source = readSource('src/views/tasks/Detail.vue')

    assert.equal(
      source.includes("v-if=\"taskStatus === 'running' || taskStatus === 'pending'\""),
      false,
    )
    assert.equal(source.includes('v-if="taskStatus === \'failure\'"'), false)
  })
})
