import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const shellPath = 'src/components/layout/AppShell.vue'

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('路由过渡的子节点是单个带 key 的元素，多根页面不会卡在全白', () => {
  // 现场：`<transition mode="out-in">` 里直接放 `<component :is>`，而结果页有多个
  // 根节点（页头 + 内容 + 免责声明）。Vue 对 Fragment 根无法计算离场动画，
  // out-in 模式下旧页移除后新页永远不进场 —— URL 变了、主区全白、必须刷新。
  // 现在固定包一层 `<div :key="route.path" class="shell-route">`。
  const source = readSource(shellPath)

  assert.match(source, /<transition[^>]*mode="out-in"/, '过渡仍在 out-in 模式')

  const block = source.slice(source.indexOf('<transition'), source.indexOf('</transition>'))
  assert.match(
    block,
    /<div :key="route\.path" class="shell-route">\s*<component :is="Component" \/>\s*<\/div>/,
    '过渡的直接子节点必须是包住页面组件的单个 keyed div'
  )
  assert.equal(
    /<transition[^>]*>\s*<component :is="Component"/.test(source),
    false,
    '不要再用页面组件本身当过渡子节点'
  )
})

test('页面包裹层保留整屏高度，滚动与定位语义不变', () => {
  const source = readSource(shellPath)
  assert.match(source, /\.shell-route\s*\{[^}]*min-height:\s*100vh/, '包裹层需要 min-height: 100vh')
})
