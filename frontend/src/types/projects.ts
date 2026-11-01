import type { TypedArtifact } from './artifacts'
import type { TaskStatus } from './models'
import type { ProjectRole, ProjectStatus } from './enums.generated'

// 契约枚举统一来自 codegen 产物（计划 §3.2，勿手改）。
export type { ProjectRole, ProjectStatus } from './enums.generated'

export interface ProjectMembership {
  id: string
  role: ProjectRole
}

export interface ProjectMember extends ProjectMembership {
  project_id: string
  user_id: string
  /** 邮箱可能为空（如 LDAP 账号未绑定邮箱） */
  email?: string | null
  username?: string | null
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
  /** Effective role of the current viewer; always a string ("admin" for platform admins without a member row). */
  role: ProjectRole | 'admin'
  /** Null only for a platform admin who is not a member of this project. */
  membership: ProjectMembership | null
  created_at: string
  updated_at: string
}

export interface ProjectCreateInput {
  name: string
  goal?: string
}

export interface ProjectMemberCreateInput {
  /** 优先按账号名邀请 */
  username: string
  /** 兼容旧版按邮箱邀请；后端仍接受 email 字段 */
  email?: string
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
  /** 候选物数（小分子与多肽，docs/06 P-04） */
  candidates: number
  /** 候选集数 */
  candidate_sets: number
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
