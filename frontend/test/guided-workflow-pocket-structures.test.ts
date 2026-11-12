import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

const guided = readSource('src/views/workflow/GuidedWorkflow.vue')
const predict = readSource('src/views/predict/PropertyPredictSubmit.vue')

test('口袋识别步骤可以切换蛋白结构', () => {
  assert.match(guided, /data-testid="guided-structure-select"/)
  assert.match(guided, /v-model:value="selectedStructureId"/)
  assert.match(guided, /@change="handleStructureChange"/)
  // 默认取最新，但要经过显式排序，而不是信任后端返回顺序
  assert.match(guided, /structures\.value = sortStructuresByNewest\(/)
  // 口袋面板跟随所选结构
  assert.match(guided, /:structure-id="structureId"/)
})

test('已识别口袋按全部结构汇总，不再只看最新那个结构', () => {
  // 旧实现是 pocketCount = listPockets(structures[0]).length，旧结构上的口袋会被统计抹掉
  assert.match(guided, /Object\.values\(pocketCounts\.value\)\.reduce/)
  assert.match(guided, /pocketCounts\.value = Object\.fromEntries\(entries\)/)
  assert.match(guided, /当前结构口袋/)
  assert.doesNotMatch(guided, /const pocketCount = ref\(0\)/)
})

test('晚到的加载响应不会覆盖用户已经选定的结构', () => {
  assert.match(guided, /let loadToken = 0/)
  assert.match(guided, /loadToken \+= 1/)
  // load() 内每个 await 之后都要检查令牌，否则慢响应会把用户的选择写回去
  const loadBody = guided.slice(guided.indexOf('async function load()'), guided.indexOf('onMounted(load)'))
  const tokenChecks = loadBody.match(/if \(token !== loadToken\) return/g) ?? []
  assert.ok(tokenChecks.length >= 4, `load() 里只有 ${tokenChecks.length} 处令牌检查`)
})

test('亲和力预测在设计流程里就地预测，而不是只给一个跳转按钮', () => {
  assert.match(guided, /<PropertyPredictSubmit :project-id-override="projectId" initial-type="affinity" \/>/)
  assert.match(guided, /在性质预测页打开/)
  // 宿主固定初始类型，避免点了亲和力那一步却停在上传 SMILES 的 ADMET 表单上
  assert.match(predict, /initialType\?: 'admet' \| 'affinity'/)
  assert.match(predict, /props\.initialType === 'affinity' \|\| route\.query\.type === 'affinity'/)
  // 内嵌时不渲染页面头（外层已有步骤标题）
  assert.match(predict, /<AppPageHeader\s+v-if="!projectIdOverride"/)
})
