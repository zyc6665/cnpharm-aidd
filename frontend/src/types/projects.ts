import type { TypedArtifact } from './artifacts'
import type { TaskStatus } from './models'

export type ProjectStatus = 'draft' | 'active' | 'completed' | 'archived' | 'frozen'
export type ProjectRole = 'owner' | 'editor' | 'runner' | 'viewer'

export interface ProjectMembership {
  id: string
  role: ProjectRole
}

export interface ProjectMember extends ProjectMembership {
  project_id: string
  user_id: string
  email: string
  display_name?: string | null
  created_at: string
  updated_at: string
}

export interface ResearchProject {
  id: string
  organization_id: string
  created_by: string
  name: string
  goal?: string | null
  status: ProjectStatus
  model_policy: Record<string, unknown>
  data_policy: Record<string, unknown>
  membership: ProjectMembership
  created_at: string
  updated_at: string
}

export interface ProjectCreateInput {
  name: string
  goal?: string
}

export interface ProjectMemberCreateInput {
  email: string
  role: Exclude<ProjectRole, 'owner'>
}

export interface ProjectMemberUpdateInput {
  role: Exclude<ProjectRole, 'owner'>
}

export interface ProjectOverviewCounts {
  artifacts: number
  tasks: number
  workflows: number
  /** 靶点数（docs/06 P-04 统计卡） */
  targets: number
  /** 蛋白结构数 */
  structures: number
  /** 口袋数 */
  pockets: number
}

export interface ProjectOverviewTask {
  id: string
  name?: string | null
  status: TaskStatus
  progress: number
  progress_message?: string | null
  error_message?: string | null
  tool_id: string
  tool_name?: string | null
  tool_slug?: string | null
  created_at: string
  updated_at: string
}

export interface ProjectOverviewWorkflow {
  id: string
  project_id?: string | null
  name: string
  description?: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ProjectOverview {
  project: ResearchProject
  counts: ProjectOverviewCounts
  artifacts: TypedArtifact[]
  tasks: ProjectOverviewTask[]
  workflows: ProjectOverviewWorkflow[]
}
