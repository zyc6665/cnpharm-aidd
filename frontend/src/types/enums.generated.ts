// AUTO-GENERATED FILE — DO NOT EDIT BY HAND.
// Source: backend/app/common/enums.py
// Regenerate: python scripts/gen_frontend_enums.py
/* eslint-disable */

export const PROJECT_STATUS = ["draft", "active", "completed", "archived", "frozen", "paused"] as const
export type ProjectStatus = (typeof PROJECT_STATUS)[number]

export const PROJECT_ROLE = ["owner", "editor", "runner", "viewer"] as const
export type ProjectRole = (typeof PROJECT_ROLE)[number]

export const TASK_PRIORITY = ["low", "normal", "high"] as const
export type TaskPriority = (typeof TASK_PRIORITY)[number]

export const TASK_STATUS = ["PENDING", "REJECTED", "QUEUED", "RUNNING", "SUCCESS", "FAILURE", "TIMEOUT", "CANCELED"] as const
export type TaskStatusGenerated = (typeof TASK_STATUS)[number]

export const ASSET_ARTIFACT_TYPE = ["compound_set", "protein_structure", "binding_pocket", "ligand_structure", "molecule_table", "md_trajectory", "run_report", "dataset"] as const
export type AssetArtifactType = (typeof ASSET_ARTIFACT_TYPE)[number]

export const AUDIT_ACTION = ["login", "logout", "login_failed", "password_change", "token_refresh", "create", "read", "update", "delete", "export", "import", "task_submit", "task_cancel", "task_retry", "file_upload", "file_download", "file_delete", "decision_create", "admin_user_create", "admin_user_update", "admin_user_delete", "admin_config_change", "admin_tool_create", "admin_tool_update", "system_start", "system_stop", "system_config"] as const
export type AuditAction = (typeof AUDIT_ACTION)[number]

export const AUDIT_RESULT = ["success", "failure", "denied", "error"] as const
export type AuditResult = (typeof AUDIT_RESULT)[number]

export const RESOURCE_TYPE = ["user", "task", "tool", "file", "config", "session", "system", "decision_record"] as const
export type ResourceType = (typeof RESOURCE_TYPE)[number]
