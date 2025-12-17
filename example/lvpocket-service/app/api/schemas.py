"""
Pydantic 数据模型定义

定义 API 请求和响应的数据结构
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, validator


# ==================== SCOP 结构分类枚举 ====================

class StructureClass(str, Enum):
    """
    SCOP 蛋白质结构分类枚举

    参考 LVpocket scop_classifier/classifier.py
    不同二级结构的蛋白质使用不同的预训练模型以获得更好的预测效果
    """
    BASELINE = "baseline"           # 基线模型（默认），适用于所有蛋白质
    ALPHA = "alpha"                 # α 类 - 主要由 α 螺旋组成
    BETA = "beta"                   # β 类 - 主要由 β 折叠组成
    ALPHA_BETA = "alpha_beta"       # α/β 类 - α 螺旋和 β 折叠交替排列
    ALPHA_PLUS_BETA = "alpha_plus_beta"  # α+β 类 - α 螺旋和 β 折叠分离排列


# ==================== 通用模型 ====================

class Coordinate(BaseModel):
    """三维坐标"""
    x: float
    y: float
    z: float


class BoundingBox(BaseModel):
    """边界框"""
    min: Coordinate
    max: Coordinate


class Residue(BaseModel):
    """氨基酸残基"""
    chain: str
    resname: str
    resid: int


class OutputFile(BaseModel):
    """输出文件信息"""
    name: str
    format: str
    size: Optional[int] = None
    url: Optional[str] = None
    content: Optional[str] = None  # Base64 编码内容（小文件）


class ErrorDetail(BaseModel):
    """错误详情"""
    code: int
    message: str
    details: Optional[Dict[str, Any]] = None


# ==================== 健康检查 ====================

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态: healthy/unhealthy")
    model_loaded: bool = Field(..., description="模型是否已加载")
    gpu_available: bool = Field(..., description="GPU 是否可用")
    gpu_name: Optional[str] = Field(None, description="GPU 名称")
    gpu_memory_total: Optional[int] = Field(None, description="GPU 总显存 (MB)")
    gpu_memory_used: Optional[int] = Field(None, description="GPU 已用显存 (MB)")
    version: str = Field(..., description="服务版本")
    uptime: float = Field(..., description="运行时间 (秒)")


# ==================== 模型信息 ====================

class ModelArchitecture(BaseModel):
    """模型架构信息"""
    type: str = "LV_NET"
    v_path: str = "3D CNN"
    l_path: str = "Transformer"
    num_heads: int = 12
    total_params: str = "3.7M"


class ModelConfig(BaseModel):
    """模型配置"""
    scale: float
    max_dist: float
    input_shape: List[int]
    output_shape: List[int]


class AvailableModel(BaseModel):
    """可用模型信息"""
    structure_class: str = Field(..., description="结构分类名称")
    file: str = Field(..., description="模型文件名")
    path: str = Field(..., description="模型文件完整路径")
    exists: bool = Field(..., description="模型文件是否存在")
    description: str = Field(..., description="模型描述")


class ModelInfoResult(BaseModel):
    """模型信息结果"""
    model_name: str
    model_version: str
    model_path: str
    architecture: ModelArchitecture
    config: ModelConfig
    supported_inputs: List[str]
    supported_outputs: List[str]
    # 多模型支持
    default_structure_class: str = Field(..., description="默认使用的结构分类")
    available_models: List[AvailableModel] = Field(..., description="所有可用的模型列表")


class ModelInfoResponse(BaseModel):
    """模型信息响应"""
    success: bool = True
    result: ModelInfoResult


# ==================== 支持格式 ====================

class FormatInfo(BaseModel):
    """格式信息"""
    format: str
    extension: str
    mime_type: Optional[str] = None
    description: str


class FormatsResult(BaseModel):
    """支持格式结果"""
    input_formats: List[FormatInfo]
    output_formats: List[FormatInfo]


class FormatsResponse(BaseModel):
    """支持格式响应"""
    success: bool = True
    result: FormatsResult


# ==================== 预测请求 ====================

class PredictParams(BaseModel):
    """预测参数"""
    threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="口袋预测阈值 (0-1)"
    )
    min_size: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="最小口袋体素数"
    )
    output_formats: List[str] = Field(
        default=["json"],
        description="输出格式列表"
    )
    structure_class: StructureClass = Field(
        default=StructureClass.BASELINE,
        description="蛋白质结构分类，用于选择对应的预训练模型。"
                    "baseline: 基线模型（默认）; "
                    "alpha: α 类蛋白质; "
                    "beta: β 类蛋白质; "
                    "alpha_beta: α/β 类蛋白质; "
                    "alpha_plus_beta: α+β 类蛋白质"
    )

    @validator("output_formats")
    def validate_output_formats(cls, v):
        allowed = {"json", "mol2", "cmap", "cube"}
        for fmt in v:
            if fmt not in allowed:
                raise ValueError(f"不支持的输出格式: {fmt}，支持: {allowed}")
        return v


class InputFiles(BaseModel):
    """输入文件"""
    protein_file: str = Field(..., description="蛋白质文件 URL")


class PredictRequest(BaseModel):
    """预测请求（JSON 方式）"""
    task_id: Optional[str] = Field(None, description="任务 ID")
    params: PredictParams = Field(default_factory=PredictParams)
    input_files: InputFiles


# ==================== 预测响应 ====================

class PocketInfo(BaseModel):
    """口袋信息"""
    id: int = Field(..., description="口袋 ID")
    rank: int = Field(..., description="排名")
    score: float = Field(..., description="置信度分数")
    volume: float = Field(..., description="体积 (Å³)")
    center: Coordinate = Field(..., description="中心坐标")
    bounding_box: Optional[BoundingBox] = Field(None, description="边界框")
    residues: Optional[List[Residue]] = Field(None, description="相关残基")


class PredictResult(BaseModel):
    """预测结果"""
    task_id: Optional[str] = None
    protein_name: str
    num_atoms: int
    num_pockets: int
    processing_time: float
    structure_class: str = Field(..., description="使用的蛋白质结构分类模型")
    model_file: str = Field(..., description="使用的模型文件名")
    pockets: List[PocketInfo]


class PredictResponse(BaseModel):
    """预测响应"""
    success: bool = True
    result: Optional[PredictResult] = None
    output_files: Optional[List[OutputFile]] = None
    error: Optional[ErrorDetail] = None


# ==================== 批量预测 ====================

class BatchInputFiles(BaseModel):
    """批量输入文件"""
    protein_files: List[str] = Field(..., description="蛋白质文件 URL 列表")


class BatchRequest(BaseModel):
    """批量预测请求"""
    task_id: Optional[str] = None
    params: PredictParams = Field(default_factory=PredictParams)
    input_files: BatchInputFiles


class BatchItemResult(BaseModel):
    """批量预测单项结果"""
    file: str
    success: bool
    num_pockets: Optional[int] = None
    pockets: Optional[List[PocketInfo]] = None
    error: Optional[str] = None


class BatchResult(BaseModel):
    """批量预测结果"""
    task_id: Optional[str] = None
    total: int
    completed: int
    failed: int
    processing_time: float
    results: List[BatchItemResult]


class BatchResponse(BaseModel):
    """批量预测响应"""
    success: bool = True
    result: Optional[BatchResult] = None
    output_files: Optional[List[OutputFile]] = None
    error: Optional[ErrorDetail] = None


# ==================== 格式转换 ====================

class ConvertParams(BaseModel):
    """转换参数"""
    source_format: str = Field(..., description="源格式")
    target_format: str = Field(..., description="目标格式")
    protein_file: Optional[str] = Field(None, description="原始蛋白质文件 URL")


class ConvertInputFiles(BaseModel):
    """转换输入文件"""
    prediction_file: str = Field(..., description="预测结果 JSON 文件 URL")


class ConvertRequest(BaseModel):
    """格式转换请求"""
    task_id: Optional[str] = None
    params: ConvertParams
    input_files: ConvertInputFiles


class ConvertResult(BaseModel):
    """转换结果"""
    task_id: Optional[str] = None
    source_format: str
    target_format: str
    conversion_time: float


class ConvertResponse(BaseModel):
    """格式转换响应"""
    success: bool = True
    result: Optional[ConvertResult] = None
    output_files: Optional[List[OutputFile]] = None
    error: Optional[ErrorDetail] = None


# ==================== 通用错误响应 ====================

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: ErrorDetail
