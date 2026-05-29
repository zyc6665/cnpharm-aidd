"""输入输出 Schema 定义。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PredictionParams(BaseModel):
    """示例参数模型。

    AI 或管理员应根据实际模型交付物替换该结构。
    """

    sample_id: str = Field(..., description="样本标识")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="阈值参数")
    top_k: int = Field(default=5, ge=1, le=100, description="返回结果数量")


class PredictionInputFiles(BaseModel):
    """示例文件输入模型。"""

    input_file: Optional[str] = Field(default=None, description="输入文件下载 URL")


class PredictRequest(BaseModel):
    """统一预测请求体。"""

    task_id: str = Field(..., description="平台任务 ID")
    params: PredictionParams = Field(..., description="业务参数")
    input_files: Optional[PredictionInputFiles] = Field(default=None, description="输入文件 URL 集合")


class OutputFile(BaseModel):
    """输出文件描述。"""

    name: str = Field(..., description="输出文件名")
    url: str = Field(..., description="输出文件下载 URL")
    size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="文件 MIME 类型")


class PredictionResult(BaseModel):
    """示例结果模型。

    AI 或管理员应根据真实模型输出替换该结构。
    """

    summary: str = Field(..., description="结果摘要")
    score: float = Field(..., description="示例分数")
    top_k: int = Field(..., description="实际使用的 top_k")
    used_files: List[str] = Field(default_factory=list, description="参与计算的本地文件路径")


class ErrorInfo(BaseModel):
    """标准错误结构。"""

    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误信息")


class PredictResponse(BaseModel):
    """统一预测响应体。"""

    success: bool = Field(..., description="是否成功")
    task_id: str = Field(..., description="平台任务 ID")
    result: Optional[PredictionResult] = Field(default=None, description="预测结果")
    output_files: List[OutputFile] = Field(default_factory=list, description="输出文件列表")
    error: Optional[ErrorInfo] = Field(default=None, description="错误信息")


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(..., description="健康状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="服务版本")
