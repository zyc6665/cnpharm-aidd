export type ProjectStatus = 'draft' | 'active' | 'completed' | 'archived' | 'frozen'
export type ProjectRole = 'owner' | 'editor' | 'runner' | 'viewer'

export interface ProjectMembership {
  id: string
  role: ProjectRole
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

