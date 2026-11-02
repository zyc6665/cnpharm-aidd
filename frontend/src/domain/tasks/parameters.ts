/**
 * 任务输入参数的可读化渲染。
 *
 * 背景：任务详情页原先把 `task.inputs.params` 直接按「键名 → 值」平铺，键名是
 * 工具契约里的英文标识（`n_samples`、`exhaustiveness`、`center_x`），值里的
 * 布尔是 `true/false`、数字没有单位、嵌套结构整段 JSON。对使用者来说这等于没解释。
 *
 * 做法：以工具版本 config 里的 `parameters_schema`（JSON Schema）为唯一依据，
 * 按 schema 的 properties 顺序出字段，用 schema 声明的 type / enum / minimum /
 * maximum / default 决定怎么显示；schema 里没有的键归到「未声明参数」分组，
 * 不隐藏——隐藏会让人以为参数没生效。
 *
 * 刻意不做的事：
 * - 不改写后端契约，不往 params 里塞展示字段；
 * - 不做单位换算，只把单位标出来（换算需要工具自己声明基准，平台猜会猜错）；
 * - 不做参数校验，校验是提交时的事，这里只负责把已提交的值讲清楚。
 */

export type ParameterValueType =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'enum'
  | 'object'
  | 'array'
  | 'null'

export interface ParameterField {
  key: string
  /** 已翻译的字段名；未收录的键退化为「把下划线换成空格」的可读形态。 */
  label: string
  type: ParameterValueType
  /** 已格式化的值文本，例如 `8`、`是`、`-8.5 kcal/mol`、`未设置`。 */
  display: string
  /** 取值来自 schema 的 default 而非用户提交（用于弱化显示）。 */
  fromDefault: boolean
  /** schema 里标记为 required。 */
  required: boolean
  /** 数值型字段的取值范围描述，如 `1 ~ 256`。 */
  range?: string
  /** 枚举字段可选项的可读列表。 */
  options?: string[]
  /** 原始值，供「查看原始 JSON」之外的排障场景使用。 */
  value: unknown
}

export interface ParameterGroup {
  id: string
  titleKey: string
  fields: ParameterField[]
}

/** 常见参数的字段名。没收录的键会退化为 `camelCase → 空格分词`，不会显示空白。 */
export const PARAMETER_LABELS: Record<string, { zh: string; en: string }> = {
  n_samples: { zh: '生成数量', en: 'Sample count' },
  num_samples: { zh: '生成数量', en: 'Sample count' },
  timesteps: { zh: '采样步数', en: 'Timesteps' },
  resamplings: { zh: '重采样次数', en: 'Resamplings' },
  jump_length: { zh: '跳跃步长', en: 'Jump length' },
  num_nodes_lig: { zh: '配体原子数上限', en: 'Ligand atom limit' },
  sanitize: { zh: '结构清洗', en: 'Sanitize structure' },
  relax: { zh: '结构弛豫', en: 'Relax structure' },
  all_frags: { zh: '生成全部片段', en: 'Generate all fragments' },
  device: { zh: '计算设备', en: 'Compute device' },
  model_choice: { zh: '模型选择', en: 'Model choice' },
  complex_id: { zh: '复合物编号', en: 'Complex ID' },
  distance: { zh: '距离阈值', en: 'Distance threshold' },
  exhaustiveness: { zh: '搜索强度', en: 'Exhaustiveness' },
  num_modes: { zh: '输出构象数', en: 'Number of modes' },
  energy_range: { zh: '能量区间', en: 'Energy range' },
  seed: { zh: '随机种子', en: 'Random seed' },
  center_x: { zh: '对接盒中心 X', en: 'Box center X' },
  center_y: { zh: '对接盒中心 Y', en: 'Box center Y' },
  center_z: { zh: '对接盒中心 Z', en: 'Box center Z' },
  size_x: { zh: '对接盒尺寸 X', en: 'Box size X' },
  size_y: { zh: '对接盒尺寸 Y', en: 'Box size Y' },
  size_z: { zh: '对接盒尺寸 Z', en: 'Box size Z' },
  temperature: { zh: '温度', en: 'Temperature' },
  nsteps: { zh: '模拟步数', en: 'Steps' },
  dt: { zh: '步长', en: 'Time step' },
  num_recycles: { zh: '循环次数', en: 'Recycles' },
  max_recycles: { zh: '最大循环次数', en: 'Max recycles' },
  model: { zh: '模型', en: 'Model' },
  use_msa: { zh: '使用多序列比对', en: 'Use MSA' },
  plddt: { zh: 'pLDDT 阈值', en: 'pLDDT threshold' },
  num_peptides: { zh: '多肽数量', en: 'Peptide count' },
  peptide_length: { zh: '多肽长度', en: 'Peptide length' },
  filter_mw: { zh: '分子量过滤区间', en: 'Molecular weight range' },
  filter_logp: { zh: 'logP 过滤区间', en: 'logP range' },
  top_k: { zh: '保留前 K 个', en: 'Top K' },
  threshold: { zh: '阈值', en: 'Threshold' },
  mode: { zh: '运行模式', en: 'Mode' },
  chain: { zh: '蛋白链', en: 'Chain' },
  ligand_id: { zh: '配体编号', en: 'Ligand ID' },
  ligand_count: { zh: '配体数', en: 'Ligand count' },
  structure_count: { zh: '结构数', en: 'Structure count' },
  pocket_count: { zh: '口袋数', en: 'Pocket count' },
  best_affinity_pred_value: { zh: '最佳预测亲和力', en: 'Best predicted affinity' },
  sequence_length: { zh: '序列长度', en: 'Sequence length' },
  total_count: { zh: '条目总数', en: 'Total count' },
  matched_count: { zh: '匹配条数', en: 'Matched count' },
  success_count: { zh: '成功数', en: 'Success count' },
  failed_count: { zh: '失败数', en: 'Failed count' },
  duplicate_count: { zh: '去重条数', en: 'Duplicate count' },
  total_rows: { zh: '总行数', en: 'Total rows' },
}

/** 单位。只在语义明确时给出，拿不准就留空——比写错好。 */
export const PARAMETER_UNITS: Record<string, string> = {
  center_x: 'Å',
  center_y: 'Å',
  center_z: 'Å',
  size_x: 'Å',
  size_y: 'Å',
  size_z: 'Å',
  distance: 'Å',
  energy_range: 'kcal/mol',
  temperature: 'K',
  dt: 'ps',
  peptide_length: 'aa',
}

/** 枚举值的可读名。未收录时保留原值。 */
export const PARAMETER_VALUE_LABELS: Record<string, Record<string, { zh: string; en: string }>> = {
  device: {
    auto: { zh: '自动选择', en: 'Auto' },
    cpu: { zh: '仅 CPU', en: 'CPU only' },
    cuda: { zh: 'GPU (CUDA)', en: 'GPU (CUDA)' },
  },
  model_choice: {
    auto: { zh: '自动', en: 'Auto' },
    all_scpdb: { zh: '全部结构域', en: 'All SCPDB domains' },
    alpha: { zh: 'α 结构域', en: 'Alpha domain' },
    beta: { zh: 'β 结构域', en: 'Beta domain' },
    alpha_beta: { zh: 'α + β 结构域', en: 'Alpha + beta' },
    alpha_and_beta: { zh: 'α 与 β 分别预测', en: 'Alpha and beta separately' },
  },
}

const DOCKING_BOX_KEYS = new Set([
  'center_x',
  'center_y',
  'center_z',
  'size_x',
  'size_y',
  'size_z',
])

const DEVICE_KEYS = new Set(['device', 'num_gpus', 'gpu', 'cuda_device'])

const REPRODUCIBILITY_KEYS = new Set(['seed', 'random_seed'])

function humanizeKey(key: string): string {
  const spaced = key
    .replace(/[_\-.]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim()
  if (!spaced) {
    return key
  }
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function parameterLabel(key: string, locale: string): string {
  const entry = PARAMETER_LABELS[key]
  if (entry) {
    return locale.startsWith('zh') ? entry.zh : entry.en
  }
  return humanizeKey(key)
}

function valueLabel(key: string, value: string, locale: string): string {
  const entry = PARAMETER_VALUE_LABELS[key]?.[value]
  if (!entry) {
    return value
  }
  return locale.startsWith('zh') ? entry.zh : entry.en
}

function schemaTypeOf(property: Record<string, unknown> | undefined): ParameterValueType {
  if (!property) {
    return 'string'
  }
  const declared = property.type
  if (typeof declared === 'string') {
    if (declared === 'null') {
      return 'null'
    }
    if (declared === 'boolean' || declared === 'integer' || declared === 'number') {
      return declared
    }
    if (declared === 'object') {
      return 'object'
    }
    if (declared === 'array') {
      return 'array'
    }
    return Array.isArray(property.enum) ? 'enum' : 'string'
  }
  // `anyOf` 形态（如 `{"anyOf":[{"type":"integer"},{"type":"null"}]}`）取第一个非 null 分支。
  const branches = property.anyOf
  if (Array.isArray(branches)) {
    for (const branch of branches) {
      if (branch && typeof branch === 'object') {
        const branchType = (branch as Record<string, unknown>).type
        if (typeof branchType === 'string' && branchType !== 'null') {
          return schemaTypeOf({ ...(branch as Record<string, unknown>) })
        }
      }
    }
  }
  return Array.isArray(property.enum) ? 'enum' : 'string'
}

function formatScalar(raw: unknown): string {
  if (typeof raw === 'number') {
    return Number.isInteger(raw) ? String(raw) : String(Number(raw.toFixed(6)))
  }
  return String(raw)
}

/**
 * 平台提交任务时把工具参数包在 `{ params: {...}, input_files: {...} }` 里
 * （`TaskInput.params` 存的就是这个包装层，见 `backend/app/api/v1/tasks.py` 的
 * `inputs.params`）。展示时必须先剥掉包装层，否则参数表只会显示两个
 * 「params / input_files」的对象字段，真正提交的值一个都看不到。
 *
 * 只在形状确实匹配时才剥：`params` 是对象、且不含 `type` 之类的 schema 同名字段，
 * 以免把某个工具自有的 `params` 参数误当成包装层。
 */
export function extractToolParams(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {}
  }
  const record = raw as Record<string, unknown>
  const inner = record.params
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
    const rest: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(record)) {
      if (key === 'params' || key === 'input_files') {
        continue
      }
      // 包装层之外的键照常展示，避免丢掉平台额外写入的字段。
      rest[key] = value
    }
    return { ...(inner as Record<string, unknown>), ...rest }
  }
  const { input_files: _ignored, ...rest } = record
  return rest
}

export interface BuildParameterGroupsOptions {
  locale?: string
  /** 未设置、未给默认值时的占位文案。 */
  unsetText?: string
  /** 布尔真/假文案。 */
  booleanText?: { yes: string; no: string }
  /** 默认值标注前缀，如「默认」。 */
  defaultPrefix?: string
}

/**
 * 把 `params` 与 JSON Schema 合成可渲染的分组字段。
 *
 * 排序取 schema 的 properties 声明顺序（这是工具作者表达重要性的唯一渠道），
 * schema 里没有的键按原对象顺序追加到最后。
 */
export function buildParameterGroups(
  params: Record<string, unknown> | null | undefined,
  schema: Record<string, unknown> | null | undefined,
  options: BuildParameterGroupsOptions = {},
): ParameterGroup[] {
  const locale = options.locale ?? 'zh-CN'
  const unsetText = options.unsetText ?? '未设置'
  const booleanText = options.booleanText ?? { yes: '是', no: '否' }
  const defaultPrefix = options.defaultPrefix ?? '默认'

  const values = (params ?? {}) as Record<string, unknown>
  const properties =
    schema && typeof schema === 'object' && schema.properties && typeof schema.properties === 'object'
      ? (schema.properties as Record<string, Record<string, unknown>>)
      : {}
  const required = new Set(
    schema && Array.isArray(schema.required) ? (schema.required as unknown[]).map(String) : [],
  )

  // 显式声明五个键而不是用 `Record<string, ParameterField[]>`：
  // 项目开启了 noUncheckedIndexedAccess，用索引签名访问会得到 `| undefined`。
  const buckets: {
    basic: ParameterField[]
    dockingBox: ParameterField[]
    device: ParameterField[]
    reproducibility: ParameterField[]
    other: ParameterField[]
  } = {
    basic: [],
    dockingBox: [],
    device: [],
    reproducibility: [],
    other: [],
  }

  const buildField = (key: string, property: Record<string, unknown> | undefined): ParameterField => {
    const hasValue = Object.prototype.hasOwnProperty.call(values, key)
    const rawValue = hasValue ? values[key] : property?.default
    const fromDefault = !hasValue && property !== undefined && property !== null
      && Object.prototype.hasOwnProperty.call(property, 'default')
    const type = schemaTypeOf(property)

    let display: string
    if (rawValue === null || rawValue === undefined || rawValue === '') {
      display = unsetText
    } else if (type === 'boolean' || typeof rawValue === 'boolean') {
      display = rawValue ? booleanText.yes : booleanText.no
    } else if (type === 'object' || type === 'array') {
      display = JSON.stringify(rawValue)
    } else if (Array.isArray(property?.enum)) {
      display = valueLabel(key, formatScalar(rawValue), locale)
    } else {
      display = formatScalar(rawValue)
      const unit = PARAMETER_UNITS[key]
      if (unit) {
        display = `${display} ${unit}`
      }
    }

    if (fromDefault && display !== unsetText) {
      display = `${defaultPrefix} ${display}`
    }

    const minimum = property?.minimum
    const maximum = property?.maximum
    const rangeParts: string[] = []
    if (typeof minimum === 'number') {
      rangeParts.push(`≥ ${minimum}`)
    }
    if (typeof maximum === 'number') {
      rangeParts.push(`≤ ${maximum}`)
    }

    const options = Array.isArray(property?.enum)
      ? (property?.enum as unknown[])
          .filter((item) => item !== null && item !== undefined)
          .map((item) => valueLabel(key, formatScalar(item), locale))
      : undefined

    return {
      key,
      label: parameterLabel(key, locale),
      type,
      display,
      fromDefault,
      required: required.has(key),
      range: rangeParts.length ? rangeParts.join(' 且 ') : undefined,
      options,
      value: rawValue,
    }
  }

  for (const [key, property] of Object.entries(properties)) {
    const field = buildField(key, property)
    if (DOCKING_BOX_KEYS.has(key)) {
      buckets.dockingBox.push(field)
    } else if (DEVICE_KEYS.has(key)) {
      buckets.device.push(field)
    } else if (REPRODUCIBILITY_KEYS.has(key)) {
      buckets.reproducibility.push(field)
    } else {
      buckets.basic.push(field)
    }
  }

  for (const key of Object.keys(values)) {
    if (Object.prototype.hasOwnProperty.call(properties, key)) {
      continue
    }
    buckets.other.push(buildField(key, undefined))
  }

  const groups: Array<{ id: string; titleKey: string; fields: ParameterField[] }> = [
    { id: 'basic', titleKey: 'tasks.parameters.group.basic', fields: buckets.basic },
    { id: 'dockingBox', titleKey: 'tasks.parameters.group.dockingBox', fields: buckets.dockingBox },
    { id: 'device', titleKey: 'tasks.parameters.group.device', fields: buckets.device },
    {
      id: 'reproducibility',
      titleKey: 'tasks.parameters.group.reproducibility',
      fields: buckets.reproducibility,
    },
    { id: 'other', titleKey: 'tasks.parameters.group.other', fields: buckets.other },
  ]

  return groups.filter((group) => group.fields.length > 0)
}

/** 参数是否完全为空（既没有提交值也没有 schema 默认值）。 */
export function hasNoParameters(
  params: Record<string, unknown> | null | undefined,
  schema: Record<string, unknown> | null | undefined,
): boolean {
  return buildParameterGroups(params, schema).length === 0
}
