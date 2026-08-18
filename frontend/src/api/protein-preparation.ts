import { LONG_RUNNING_TIMEOUT_MS, post } from './request'
import type { ApiResponse } from '@/types/api'

export type ProteinPreparationOutputFormat = 'prepared_pdb' | 'receptor_pdbqt' | 'prepared_pqr'

export interface ProteinPreparationOptions {
  ph: number
  remove_water: boolean
  keep_metals: boolean
  keep_cofactors: boolean
  remove_non_target_ligands: boolean
  output_formats: ProteinPreparationOutputFormat[]
}

export interface ProteinPreparationPayload {
  artifact_id: string
  artifact_version_id?: string
  source_node_id?: string
  position?: { x: number; y: number }
  preparation_profile: 'docking_v1'
  options: ProteinPreparationOptions
  advanced_options?: Record<string, unknown>
}

export interface ProteinPreparationBoardNode {
  id: string
  type: 'tool' | 'artifact'
  position: { x: number; y: number }
  tool_id?: string
  artifact_id?: string
  task_id?: string
  status?: string
  output_artifact_id?: string
}

export interface ProteinPreparationBoardEdge {
  id: string
  source: string
  target: string
  label?: string
}

export interface ProteinPreparationStartResult {
  task_id: string
  preparation_node: ProteinPreparationBoardNode
  edge?: ProteinPreparationBoardEdge | null
}

export interface ProteinPreparationSyncResult {
  preparation_node: ProteinPreparationBoardNode
  artifact_node?: ProteinPreparationBoardNode | null
  edge?: ProteinPreparationBoardEdge | null
}

export const startProteinPreparation = (
  boardId: string,
  payload: ProteinPreparationPayload
): Promise<ApiResponse<ProteinPreparationStartResult>> => {
  return post<ProteinPreparationStartResult>(
    `/research-boards/${boardId}/protein-preparations`,
    payload,
    { timeout: LONG_RUNNING_TIMEOUT_MS }
  )
}

export const syncProteinPreparation = (
  boardId: string,
  taskId: string
): Promise<ApiResponse<ProteinPreparationSyncResult>> => {
  return post<ProteinPreparationSyncResult>(
    `/research-boards/${boardId}/protein-preparations/${taskId}/sync`,
    undefined,
    { timeout: LONG_RUNNING_TIMEOUT_MS }
  )
}
