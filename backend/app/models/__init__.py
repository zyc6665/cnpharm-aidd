# backend/app/models/__init__.py
"""数据模型"""
from app.models.users import User
from app.models.tools import (
    Tool,
    ToolCategory,
    ToolVersion,
    Tag,
    ToolWorkbenchGroup,
    ToolWorkbenchGroupMapping,
)
from app.models.tasks import Task, TaskInput, TaskOutput, TaskLog
from app.models.files import File
from app.models.workflows import ResearchBoard, WorkflowDefinition, WorkflowRun
from app.models.verification import VerificationCode, VerificationDailyCount, VerificationPurpose
from app.models.statistics import UserStatistics, ToolStatistics, FileStatistics
from app.models.tool_capabilities import ToolCapability
from app.models.projects import Organization, Project, ProjectMember
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion, ArtifactVersionFile
from app.models.executions import ExecutionRecord
from app.models.gpu import GPUAllocation, GPUAllocationStatus
from app.models.image_assets import ImageAsset, ImageImport, ImageImportStatus
from app.models.targets import (
    Pocket,
    PocketResidue,
    Protein,
    ProteinStructure,
    Target,
)
from app.models.compounds import (
    Candidate,
    CandidateSet,
    CandidateSetItem,
    Compound,
    MoleculeFingerprint,
)
from app.models.traceability import AuditLog, TaskInputSnapshot
from app.models.decisions import DecisionItem, DecisionRecord

__all__ = [
    "User",
    "Tool", "ToolCategory", "ToolVersion", "Tag",
    "ToolWorkbenchGroup", "ToolWorkbenchGroupMapping",
    "Task", "TaskInput", "TaskOutput", "TaskLog",
    "File",
    "ResearchBoard", "WorkflowDefinition", "WorkflowRun",
    "VerificationCode", "VerificationDailyCount", "VerificationPurpose",
    "UserStatistics", "ToolStatistics", "FileStatistics",
    "ToolCapability",
    "Organization", "Project", "ProjectMember",
    "ToolPackage", "ToolPackageVersion",
    "Artifact", "ArtifactLineage", "ArtifactVersion", "ArtifactVersionFile",
    "ExecutionRecord",
    "GPUAllocation", "GPUAllocationStatus",
    "ImageAsset", "ImageImport", "ImageImportStatus",
    "Target", "Protein", "ProteinStructure", "Pocket", "PocketResidue",
    "Compound", "Candidate", "CandidateSet", "CandidateSetItem", "MoleculeFingerprint",
    "AuditLog", "TaskInputSnapshot",
    "DecisionRecord", "DecisionItem",
]
