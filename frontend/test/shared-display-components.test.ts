import { assert, describe, it } from 'vitest'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC = resolve(process.cwd(), 'src')
const read = (rel: string): string => readFileSync(resolve(SRC, rel), 'utf-8')

/**
 * 这组测试守的是「显示层要有共用组件」这条约定本身。
 *
 * 背景：详情页原先各写一份 `<a-descriptions>` 与 `<pre>{{ JSON.stringify(...) }}</pre>`，
 * 结果同一个概念在不同页显示不一致（空值是 `-` 还是 `—`、小数位数、枚举是否翻译）。
 * 收敛后：原始 JSON 一律走 `AppRawJson`，分节字段一律走 `AppDescriptionList`。
 * 这两个约定一旦被绕过，页面就会重新长出自己的实现，所以用测试钉住。
 */
describe('共用显示组件', () => {
  it('两个共用组件存在', () => {
    assert.equal(existsSync(resolve(SRC, 'components/common/AppRawJson.vue')), true)
    assert.equal(existsSync(resolve(SRC, 'components/common/AppDescriptionList.vue')), true)
  })

  it('AppRawJson 自己负责 JSON 序列化，调用方不再各自 stringify', () => {
    const raw = read('components/common/AppRawJson.vue')
    assert.include(raw, 'JSON.stringify')
    assert.include(raw, 'a-collapse')
  })

  it('任务参数表与结果区改用共用 JSON 折叠块', () => {
    assert.include(read('components/tasks/TaskParameterTable.vue'), 'AppRawJson')
    assert.notInclude(read('components/tasks/TaskParameterTable.vue'), 'JSON.stringify(')
  })

  it('结果详情、管理端任务与系统配置页也走同一个折叠块', () => {
    for (const rel of [
      'views/results/ResultDetail.vue',
      'views/admin/Tasks.vue',
      'views/admin/System.vue',
    ]) {
      const source = read(rel)
      assert.include(source, 'AppRawJson', `${rel} 应该使用 AppRawJson`)
      assert.notInclude(source, 'JSON.stringify(', `${rel} 不应自己序列化只读 JSON`)
    }
  })

  it('候选物详情展示 attrs，且未识别键不隐藏', () => {
    const source = read('views/compounds/CandidateDetail.vue')
    assert.include(source, 'AppDescriptionList')
    assert.include(source, 'candidate-attrs')
    assert.include(source, 'humanizeKey')
  })

  it('格式化原语只有一份，页面不再本地重复实现 humanize/空值兜底', () => {
    const format = read('domain/common/format.ts')
    for (const name of [
      'formatNullable', 'formatNumber', 'formatFixed', 'formatWithUnit',
      'formatBytes', 'humanizeKey', 'formatDateTimeOrDash', 'formatDateOrDash',
      'formatDateTimeSecondsOrDash',
    ]) {
      assert.include(format, `export function ${name}`, `format.ts 缺少 ${name}`)
    }
    const candidate = read('views/compounds/CandidateDetail.vue')
    assert.include(candidate, "@/domain/common/format")
  })
})

  it('页面不再各自实现 formatDate / formatSize / formatNumber', () => {
    const offenders = [
      'views/compounds/Assets.vue',
      'views/compounds/Candidates.vue',
      'views/compounds/CandidateDetail.vue',
      'views/compounds/CompoundDetail.vue',
      'views/results/List.vue',
      'views/results/ResultDetail.vue',
      'views/admin/Tasks.vue',
      'views/admin/Users.vue',
      'views/user/Profile.vue',
      'components/artifacts/CompoundSetArtifact.vue',
      'components/artifacts/DatasetArtifact.vue',
    ]
    for (const rel of offenders) {
      const source = read(rel)
      for (const pattern of ['function formatDate', 'const formatDate = (', 'function formatSize', 'function formatSimilarity']) {
        assert.notInclude(source, pattern, `${rel} 仍在本地实现 ${pattern}`)
      }
    }
  })

  it('字节与小数格式化统一到共用原语', () => {
    assert.include(read('domain/projects/overview.ts'), "from '@/domain/common/format'")
    assert.include(read('domain/workspace/overview.ts'), "from '@/domain/common/format'")
    assert.include(read('domain/results/index.ts'), "from '@/domain/common/format'")
  })

  it('空值占位符全平台只有一种写法', () => {
    const offenders: string[] = []
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name === 'dist') continue
        const full = `${dir}/${entry.name}`
        if (entry.isDirectory()) {
          walk(full)
          continue
        }
        if (!/\.(vue|ts)$/.test(entry.name) || /\.spec\.ts$/.test(entry.name)) continue
        const source = readFileSync(full, 'utf-8')
        // 只允许 EMPTY_DISPLAY（format.ts 定义）与字面 '-'；禁止全角破折号当占位符
        if (source.includes("'—'")) offenders.push(full.replace(`${process.cwd()}/src/`, ''))
      }
    }
    walk(`${process.cwd()}/src`)
    assert.deepEqual(offenders, [], `以下文件仍用全角破折号当空值占位符：${offenders.join(', ')}`)
  })

  it('字节格式化只有 formatBytes 一份实现', () => {
    for (const rel of ['components/artifacts/FileArtifact.vue', 'domain/tasks/detail.ts']) {
      assert.notInclude(read(rel), 'Math.log(', `${rel} 仍在本地换算字节单位`)
    }
    assert.include(read('domain/tasks/detail.ts'), "from '@/domain/common/format'")
  })
