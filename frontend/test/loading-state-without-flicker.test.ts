import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * 「刷新时不许把已有内容卸载」的回归网。
 *
 * 背景：列表页/详情页曾用 `<SkeletonList v-if="loading">` 直接替换内容，
 * 任务中心的自动刷新（10s 一次）与详情页的 SSE 实时刷新都会让它原地闪成骨架屏，
 * 用户看到的就是「页面一下一下地白闪」。
 *
 * 三条规矩：
 *   1. 骨架屏只在「还没有内容」时占位（`loading && 空`），有内容时只显示进度条；
 *   2. 列表与详情的加载态必须是两个状态，否则一边刷新会波及另一边；
 *   3. 刷新首页（F5）要有首屏骨架，不能是「白屏 → 内容」硬切换。
 */

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('骨架屏只在没有内容时占位，已有内容时用进度条表示刷新', () => {
  const cases: ReadonlyArray<readonly [string, string, string]> = [
    ['src/views/tasks/List.vue', 'loading && !hasDisplayItems', 'backgroundLoading'],
    ['src/views/tools/List.vue', 'loading && !displayTools.length', 'LoadingBar'],
    ['src/views/user/Favorites.vue', 'loading && !favorites.length', 'LoadingBar'],
    ['src/views/tasks/Detail.vue', 'loading && !task', 'detailLoading'],
  ]

  for (const [file, guard, marker] of cases) {
    const source = readSource(file)
    assert.equal(source.includes(guard), true, `${file} 的骨架屏必须用「${guard}」守卫`)
    assert.equal(source.includes(marker), true, `${file} 缺少 ${marker}`)
    // 裸 `v-if="loading"` 会把整块内容卸载重挂，正是白闪的来源。
    assert.equal(
      /<Skeleton(List|Detail)\s+v-if="loading"\s*\/>/.test(source),
      false,
      `${file} 不允许用裸 loading 卸载已有内容`
    )
  }
})

test('列表与详情的加载态必须是两个状态', () => {
  const store = readSource('src/stores/tasks.ts')
  assert.equal(store.includes('const detailLoading = ref(false)'), true)
  // fetchTaskDetail 只能动 detailLoading，动 loading 就会把列表页一起切走。
  const detailBody = /const fetchTaskDetail = async \(id: string\) => \{[\s\S]*?\n {2}\}/.exec(store)?.[0]
  assert.ok(detailBody, '未找到 fetchTaskDetail 的实现')
  assert.equal(detailBody.includes('detailLoading.value = true'), true)
  assert.equal(/\bloading\.value = (true|false)/.test(detailBody), false)

  const detailView = readSource('src/views/tasks/Detail.vue')
  assert.equal(detailView.includes('tasksStore.detailLoading'), true)
  assert.equal(detailView.includes('tasksStore.loading'), false)
})

test('首次进入页面要有首屏骨架，而不是白屏硬切内容', () => {
  const html = readSource('index.html')
  assert.equal(html.includes('id="app-splash"'), true)
  // 主题要在 HTML 解析阶段落一次，否则暗色界面会先闪一下亮色。
  assert.equal(html.includes("getItem('cpumodel_theme')"), true)

  const main = readSource('src/main.ts')
  assert.equal(main.includes('router.isReady().then(dismissSplash)'), true)
  // 路由异常时骨架不能永久盖住界面。
  assert.equal(main.includes('setTimeout(dismissSplash'), true)
  // 骨架必须真的从 DOM 移除，不能只是透明（否则会吞掉点击）。
  assert.equal(main.includes('splash.remove()'), true)
})
