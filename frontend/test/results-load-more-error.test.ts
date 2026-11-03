import { describe, expect, it } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (relativePath: string) =>
  readFileSync(resolve(rootDir, relativePath), 'utf8')

describe('结果列表「加载更多」失败不应吞掉已加载数据', () => {
  it('首屏失败与加载更多失败使用两个独立状态', () => {
    const source = readSource('src/views/results/List.vue')

    // 首屏失败仍然是整页错误
    assert.equal(source.includes('v-else-if="loadError"'), true)
    // 加载更多失败单独标记，且不写回首屏 loadError
    assert.equal(source.includes('loadMoreError'), true)

    const loadMoreBlock = source.slice(
      source.indexOf('async function loadMoreResults'),
      source.indexOf('onMounted('),
    )
    assert.equal(loadMoreBlock.includes('loadMoreError.value = true'), true)
    assert.equal(loadMoreBlock.includes('loadError.value = true'), false)
    // 已加载结果不能被清空
    assert.equal(loadMoreBlock.includes('results.value = []'), false)
  })

  it('加载更多失败时在分页区域渲染行内错误并允许重试', () => {
    const source = readSource('src/views/results/List.vue')

    const paginationBlock = source.slice(
      source.indexOf('results-pagination'),
      source.indexOf('</main>'),
    )
    assert.equal(paginationBlock.includes('loadMoreError'), true)
    assert.equal(paginationBlock.includes('AppInlineError'), true)
    assert.equal(paginationBlock.includes('@click="loadMoreResults"'), true)
  })
})
