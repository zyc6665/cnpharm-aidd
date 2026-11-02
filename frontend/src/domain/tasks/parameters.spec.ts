import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildParameterGroups,
  extractToolParams,
  hasNoParameters,
  parameterLabel,
} from './parameters'

const GENERATION_SCHEMA = {
  type: 'object',
  properties: {
    n_samples: { type: 'integer', default: 8, minimum: 1, maximum: 256 },
    timesteps: { type: 'integer', default: 100 },
    sanitize: { type: 'boolean', default: true },
    device: { type: 'string', enum: ['auto', 'cpu', 'cuda'], default: 'auto' },
    seed: { type: 'integer' },
  },
  required: ['n_samples'],
}

const DOCKING_SCHEMA = {
  type: 'object',
  properties: {
    exhaustiveness: { type: 'integer', default: 8 },
    center_x: { type: 'number' },
    center_y: { type: 'number' },
    center_z: { type: 'number' },
    size_x: { type: 'number' },
  },
}

test('按 schema 声明顺序输出并拆出对接盒与计算设备分组', () => {
  const groups = buildParameterGroups(
    { exhaustiveness: 16, center_x: 12.5, center_y: -3, center_z: 40.2, size_x: 20 },
    { type: 'object', properties: { ...DOCKING_SCHEMA.properties, device: { type: 'string', enum: ['auto', 'cuda'] } } },
  )
  assert.deepEqual(
    groups.map((group) => group.id),
    ['basic', 'dockingBox', 'device'],
  )
  const basic = groups.find((group) => group.id === 'basic')
  assert.deepEqual(basic?.fields.map((field) => field.key), ['exhaustiveness'])
  const box = groups.find((group) => group.id === 'dockingBox')
  assert.deepEqual(box?.fields.map((field) => field.key), ['center_x', 'center_y', 'center_z', 'size_x'])
})

test('常见参数给出中文名，未收录的键退化为空格分词的大写开头', () => {
  assert.equal(parameterLabel('n_samples', 'zh-CN'), '生成数量')
  assert.equal(parameterLabel('n_samples', 'en-US'), 'Sample count')
  assert.equal(parameterLabel('custom_flag', 'zh-CN'), 'Custom flag')
  assert.equal(parameterLabel('custom_flag', 'en-US'), 'Custom flag')
  assert.equal(parameterLabel('未命名', 'zh-CN'), '未命名')
})

test('对接盒坐标带单位，普通数值不带单位', () => {
  const groups = buildParameterGroups({ center_x: 12.5, exhaustiveness: 16 }, {
    type: 'object',
    properties: {
      center_x: { type: 'number' },
      exhaustiveness: { type: 'integer' },
    },
  })
  const fields = groups.flatMap((group) => group.fields)
  assert.equal(fields.find((field) => field.key === 'center_x')?.display, '12.5 Å')
  assert.equal(fields.find((field) => field.key === 'exhaustiveness')?.display, '16')
})

test('布尔值翻成是/否而不是 true/false', () => {
  const groups = buildParameterGroups({ sanitize: false }, {
    type: 'object',
    properties: { sanitize: { type: 'boolean' } },
  })
  assert.equal(groups[0]!.fields[0]!.display, '否')
  assert.equal(groups[0]!.fields[0]!.type, 'boolean')
})

test('未提交但 schema 有默认值：标注「默认」并标记 fromDefault', () => {
  const groups = buildParameterGroups({ timesteps: 500 }, GENERATION_SCHEMA)
  const fields = groups.flatMap((group) => group.fields)
  const samples = fields.find((field) => field.key === 'n_samples')
  assert.equal(samples?.display, '默认 8')
  assert.equal(samples?.fromDefault, true)
  const timesteps = fields.find((field) => field.key === 'timesteps')
  assert.equal(timesteps?.display, '500')
  assert.equal(timesteps?.fromDefault, false)
})

test('既未提交也没有默认值：显示未设置而不是空白', () => {
  const groups = buildParameterGroups({}, GENERATION_SCHEMA, { unsetText: '未设置' })
  const seed = groups.flatMap((group) => group.fields).find((field) => field.key === 'seed')
  assert.equal(seed?.display, '未设置')
})

test('枚举值翻译成中文并列出可选项', () => {
  const groups = buildParameterGroups({ device: 'cuda' }, GENERATION_SCHEMA)
  const device = groups.flatMap((group) => group.fields).find((field) => field.key === 'device')
  assert.equal(device?.display, 'GPU (CUDA)')
  assert.deepEqual(device?.options, ['自动选择', '仅 CPU', 'GPU (CUDA)'])
})

test('required 与取值范围带出来，便于判断是否被截断', () => {
  const groups = buildParameterGroups({}, GENERATION_SCHEMA)
  const samples = groups.flatMap((group) => group.fields).find((field) => field.key === 'n_samples')
  assert.equal(samples?.required, true)
  assert.equal(samples?.range, '≥ 1 且 ≤ 256')
})

test('schema 未声明的键进「未声明」分组，不静默丢弃', () => {
  const groups = buildParameterGroups({ n_samples: 4, hidden_knob: 'x' }, GENERATION_SCHEMA)
  const other = groups.find((group) => group.id === 'other')
  assert.deepEqual(other?.fields.map((field) => field.key), ['hidden_knob'])
})

test('工具完全没声明 schema 时，提交值仍然全部列出', () => {
  const groups = buildParameterGroups({ foo: 1, bar: 'baz' }, null)
  assert.deepEqual(groups.map((group) => group.id), ['other'])
  assert.deepEqual(groups[0]!.fields.map((field) => field.key), ['foo', 'bar'])
})

test('嵌套对象压缩成一行 JSON，避免描述表被撑开', () => {
  const groups = buildParameterGroups({ box: { x: 1, y: 2 } }, {
    type: 'object',
    properties: { box: { type: 'object' } },
  })
  assert.equal(groups[0]!.fields[0]!.display, '{"x":1,"y":2}')
})

test('无参数且无 schema 时判定为空', () => {
  assert.equal(hasNoParameters({}, null), true)
  assert.equal(hasNoParameters(null, null), true)
  assert.equal(hasNoParameters({}, GENERATION_SCHEMA), false)
})

test('剥掉平台写入的 params 包装层，参数表才看得见真正提交的值', () => {
  const raw = {
    params: { sampling_steps: 50, recycling_steps: 1, sequence: 'MKTAYIAK' },
    input_files: { 'protein_structure@1': 'artifact-version-1' },
  }
  const params = extractToolParams(raw)
  assert.deepEqual(params, {
    sampling_steps: 50,
    recycling_steps: 1,
    sequence: 'MKTAYIAK',
  })
  assert.equal('input_files' in params, false, '输入绑定不是工具参数')
})

test('包装层之外平台额外写入的字段保留，不被丢掉', () => {
  const params = extractToolParams({
    params: { n_samples: 4 },
    input_files: {},
    platform: 'gcdm',
  })
  assert.deepEqual(params, { n_samples: 4, platform: 'gcdm' })
})

test('没有包装层时原样返回，仅去掉 input_files', () => {
  assert.deepEqual(extractToolParams({ n_samples: 8, input_files: {} }), { n_samples: 8 })
  assert.deepEqual(extractToolParams(null), {})
  assert.deepEqual(extractToolParams([1, 2]), {})
  assert.deepEqual(extractToolParams('x'), {})
})
