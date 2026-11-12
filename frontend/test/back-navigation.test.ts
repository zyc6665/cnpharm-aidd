import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { readHistoryBack, resolveBackTarget } from '../src/domain/navigation/back'

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

describe('返回按钮的落点', () => {
  it('历史里有上一页时回上一页，而不是固定父级', () => {
    const decision = resolveBackTarget({
      historyBack: '/achievements?projectId=p1&targetId=t1',
      currentPath: '/structures/s1',
      fallback: '/targets/t1'
    })
    assert.deepEqual(decision, { mode: 'back', to: '/achievements?projectId=p1&targetId=t1' })
  })

  it('直接打开链接（历史里没有上一条）时退到兜底路径', () => {
    const decision = resolveBackTarget({
      historyBack: null,
      currentPath: '/structures/s1',
      fallback: '/targets/t1'
    })
    assert.deepEqual(decision, { mode: 'push', to: '/targets/t1' })
  })

  it('上一条就是自己时不原地打转', () => {
    const decision = resolveBackTarget({
      historyBack: '/structures/s1',
      currentPath: '/structures/s1',
      fallback: '/targets/t1'
    })
    assert.deepEqual(decision, { mode: 'push', to: '/targets/t1' })
  })

  it('history.state 里读不到 back 时返回 null', () => {
    expect(readHistoryBack(null)).toBeNull()
    expect(readHistoryBack(undefined)).toBeNull()
    expect(readHistoryBack({})).toBeNull()
    expect(readHistoryBack({ back: 42 })).toBeNull()
    expect(readHistoryBack({ back: '' })).toBeNull()
    expect(readHistoryBack({ back: '/workspace' })).toBe('/workspace')
  })
})

describe('详情页统一用 AppBackLink', () => {
  const pages = [
    'src/views/targets/StructureDetail.vue',
    'src/views/targets/Detail.vue',
    'src/views/targets/Pockets.vue',
    'src/views/targets/PocketResidues.vue',
    'src/views/targets/Predict.vue',
    'src/views/results/ResultDetail.vue',
    'src/views/compounds/CandidateSetDetail.vue'
  ]

  it('都引用同一个返回组件，并保留兜底路径', () => {
    for (const page of pages) {
      const text = source(page)
      assert.match(text, /import AppBackLink from '@\/components\/common\/AppBackLink\.vue'/, page)
      assert.match(text, /<AppBackLink[\s\S]{0,160}:fallback=/, page)
      // 旧的写死父级链接不能再出现：它就是「返回跳到靶点详情」的来源
      assert.doesNotMatch(text, /<router-link :to="[^"]*" class="back-link">/, page)
    }
  })

  it('每个页面都给出父级文案，让用户还能选「回上一层」', () => {
    for (const page of pages) {
      const text = source(page)
      // 两种情况都要有入口：只是「回上一页」不够，用户有时就是想回到上一层
      assert.match(text, /:parent-label="t\('[a-zA-Z.]+'\)"/, page)
    }
  })

  it('组件本身优先走历史，回不去才 push 兜底', () => {
    const component = source('src/components/common/AppBackLink.vue')
    assert.match(component, /readHistoryBack\(window\.history\.state\)/)
    assert.match(component, /resolveBackTarget\(/)
    assert.match(component, /router\.back\(\)/)
    assert.match(component, /router\.push\(decision\.to\)/)
  })

  it('组件同时渲染「上一页」按钮与父级链接两个入口', () => {
    const component = source('src/components/common/AppBackLink.vue')
    assert.match(component, /parentLabel\?: string/)
    assert.match(component, /<button[^>]*class="app-back-link"[^>]*@click="handleBack"/)
    assert.match(
      component,
      /<router-link class="app-back-link app-back-link--parent" :to="fallback"/
    )
    // 父级链接只在给了文案时才出现，避免出现「返回」两个同义按钮
    assert.match(component, /<template v-if="parentLabel">/)
  })
})
