/**
 * 产物（Artifact）的**展示口径**：把「机器标识」翻成用户能读懂的一句话。
 *
 * 背景：产物列表里原先直接渲染 `artifact.name`，而多数任务产出的 `name` 就是
 * 文件名（`cb_data_result.csv`），类型则显示成 `molecule_table@1` 这种协议标识。
 * 用户看到一行 `cb_data_result.csv` + `molecule_table@1` 无法判断「这是什么、
 * 是哪一步产出的、能不能直接用」。
 *
 * 这里统一三件事：
 * 1. **类型码 → 中文名**（`ARTIFACT_TYPE_LABEL_KEYS`，由 i18n 提供文案）；
 * 2. **标题**：优先用后端给的可读 `name`；若 `name` 只是文件名，则退化成
 *    「类型名 · v版本号」——因为把文件名当标题等于没有标题；
 * 3. **文件名**永远保留为次要信息（等宽小字），不能丢：下载、跟别人对数时
 *    用户还是要靠它。
 *
 * 纯函数、不依赖 Vue，便于单测与在多个页面复用。
 */

import type { AssetArtifactType } from '@/types/artifacts'

/** 受控资产类型 → i18n 键。新增类型时 TypeScript 会在此处报缺失。 */
export const ARTIFACT_TYPE_LABEL_KEYS: Record<AssetArtifactType, string> = {
  compound_set: 'artifacts.type.compoundSet',
  protein_structure: 'artifacts.type.proteinStructure',
  binding_pocket: 'artifacts.type.bindingPocket',
  ligand_structure: 'artifacts.type.ligandStructure',
  molecule_table: 'artifacts.type.moleculeTable',
  md_trajectory: 'artifacts.type.mdTrajectory',
  run_report: 'artifacts.type.runReport',
  dataset: 'artifacts.type.dataset'
}

const KNOWN_TYPES = new Set<string>(Object.keys(ARTIFACT_TYPE_LABEL_KEYS))

/** 去掉历史 `type@version` 写法里的 `@version`。 */
export function normalizeArtifactTypeCode(value?: string | null): string {
  if (!value) return ''
  return value.split('@', 1)[0]?.trim() ?? ''
}

/**
 * 类型码 → i18n 键。未知类型返回 `artifacts.type.unknown`，调用方照常渲染，
 * 不需要在模板里写分支。
 */
export function artifactTypeLabelKey(value?: string | null): string {
  const code = normalizeArtifactTypeCode(value)
  return KNOWN_TYPES.has(code) ? ARTIFACT_TYPE_LABEL_KEYS[code as AssetArtifactType] : 'artifacts.type.unknown'
}

/**
 * 判断一个名字是不是「文件名」而不是「标题」。
 *
 * 判据：带扩展名（`.csv` / `.pdb` / `.sdf` …）且不含空格。人的标题几乎不会长成
 * `xxx.csv` 的样子；反过来 `对接结果-1uw6` 这种是标题，不该被丢掉。
 */
export function isFileNameLike(value?: string | null): boolean {
  const text = (value ?? '').trim()
  if (!text) return false
  return /\.[A-Za-z0-9]{1,8}$/.test(text) && !/\s/.test(text)
}

export interface ArtifactDisplayInput {
  /** 后端 `Artifact.name`，可能是标题，也可能是文件名，也可能为空。 */
  name?: string | null
  artifactType?: string | null
  semanticType?: string | null
  standardType?: string | null
  version?: number | null
  /** 版本上的真实文件名（`ArtifactVersion.filename`）。 */
  filename?: string | null
}

export interface ArtifactDisplay {
  /** i18n 键，交给调用方 `t()`，避免本模块依赖 i18n 实例。 */
  typeKey: string
  /** 原始类型码，供 `title`/调试/tooltip 使用。 */
  typeCode: string
  /** 事实上的标题：可读名，或「类型名 · vN」。 */
  title: string
  /** 次要信息：真实文件名（可能为 null）。 */
  fileName: string | null
}

/**
 * 组装展示信息。
 *
 * @param input 产物或其版本字段
 * @param translate i18n 翻译函数（页面里传 `t`，测试里传假函数）
 */
export function buildArtifactDisplay(
  input: ArtifactDisplayInput,
  translate: (key: string) => string
): ArtifactDisplay {
  const typeCode =
    normalizeArtifactTypeCode(input.standardType) ||
    normalizeArtifactTypeCode(input.semanticType) ||
    normalizeArtifactTypeCode(input.artifactType)
  const typeKey = artifactTypeLabelKey(typeCode || input.artifactType)
  const typeLabel = translate(typeKey)

  const rawName = (input.name ?? '').trim()
  const fileNameGuess = (input.filename ?? '').trim() || (isFileNameLike(rawName) ? rawName : '')

  const versionSuffix = input.version ? ` · v${input.version}` : ''
  const title = rawName && !isFileNameLike(rawName) ? rawName : `${typeLabel}${versionSuffix}`

  return {
    typeKey,
    typeCode,
    title,
    fileName: fileNameGuess || null
  }
}
