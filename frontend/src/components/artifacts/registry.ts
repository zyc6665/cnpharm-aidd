import type { Component } from 'vue'

import type { AssetArtifactType } from '@/types/artifacts'
import { ASSET_ARTIFACT_TYPE } from '@/types/enums.generated'

import CompoundSetArtifact from './CompoundSetArtifact.vue'
import DatasetArtifact from './DatasetArtifact.vue'
import FileArtifact from './FileArtifact.vue'
import LigandStructureArtifact from './LigandStructureArtifact.vue'
import MdTrajectoryArtifact from './MdTrajectoryArtifact.vue'
import PocketResultArtifact from './PocketResultArtifact.vue'
import ProteinStructureArtifact from './ProteinStructureArtifact.vue'
import RunReportArtifact from './RunReportArtifact.vue'

/**
 * 资产类型 → 渲染组件的完备映射。
 *
 * 键必须是后端的 8 个受控资产类型（``AssetArtifactType``），由 TypeScript 的
 * ``Record`` 完备性在编译期兜底；``ArtifactRenderer.spec.ts`` 里再用运行时遍历
 * ``ASSET_ARTIFACT_TYPE`` 二次守护，避免 ``as`` 之类的断言把缺口悄悄放过去。
 */
export const ARTIFACT_COMPONENTS: Record<AssetArtifactType, Component> = {
  compound_set: CompoundSetArtifact,
  protein_structure: ProteinStructureArtifact,
  binding_pocket: PocketResultArtifact,
  ligand_structure: LigandStructureArtifact,
  molecule_table: LigandStructureArtifact,
  md_trajectory: MdTrajectoryArtifact,
  run_report: RunReportArtifact,
  dataset: DatasetArtifact
}

const ASSET_ARTIFACT_TYPE_SET: ReadonlySet<string> = new Set(ASSET_ARTIFACT_TYPE)

/** 类型守卫：把 ``string`` 收窄成 ``AssetArtifactType``，不靠 ``as`` 硬转。 */
export function isAssetArtifactType(value: string): value is AssetArtifactType {
  return ASSET_ARTIFACT_TYPE_SET.has(value)
}

/** 去掉历史 ``type@version`` 写法里的 ``@version`` 后缀。 */
export function normalizeAssetArtifactType(value: string): string {
  return value.split('@', 1)[0] || value
}

/** 根据资产类型解析渲染组件；未知类型返回 ``null``，由调用方展示兜底提示。 */
export function resolveArtifactComponent(value: string): Component | null {
  const normalized = normalizeAssetArtifactType(value)
  return isAssetArtifactType(normalized) ? ARTIFACT_COMPONENTS[normalized] : null
}
