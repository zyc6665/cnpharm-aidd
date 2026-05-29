"""模型适配层。

该文件负责把学生提交的模型代码接入统一服务模板。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.errors import ToolServiceError
from app.schemas import PredictRequest, PredictResponse, PredictionResult


class ModelAdapter:
    """统一模型适配器。

    默认实现是一个可运行的占位版本：
    - 支持下载平台传入的文件 URL
    - 返回一个可用于联调的示例结果

    真正接入新模型时，优先修改：
    1. load_model()
    2. predict()
    """

    def __init__(self) -> None:
        self._loaded = False

    def load_model(self) -> None:
        """加载模型或其他运行资源。"""
        settings.work_dir.mkdir(parents=True, exist_ok=True)
        self._loaded = True

    async def predict(self, request: PredictRequest) -> PredictResponse:
        """执行预测。"""
        if not self._loaded:
            self.load_model()

        local_files = await self._download_input_files(request)
        result = PredictionResult(
            summary=f"Template prediction for {request.params.sample_id}",
            score=request.params.threshold,
            top_k=request.params.top_k,
            used_files=list(local_files.values()),
        )

        return PredictResponse(
            success=True,
            task_id=request.task_id,
            result=result,
            output_files=[],
            error=None,
        )

    async def _download_input_files(self, request: PredictRequest) -> Dict[str, str]:
        """下载平台传入的文件 URL。"""
        if not request.input_files:
            return {}

        request_dir = settings.work_dir / request.task_id / "input"
        request_dir.mkdir(parents=True, exist_ok=True)

        downloaded_files: Dict[str, str] = {}
        async with httpx.AsyncClient(timeout=300) as client:
            for field_name, file_url in request.input_files.model_dump(exclude_none=True).items():
                filename = self._guess_filename(field_name, file_url)
                local_path = request_dir / filename

                try:
                    response = await client.get(file_url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise ToolServiceError(
                        f"下载输入文件失败: {field_name} -> {file_url}, {exc}",
                        code="INPUT_FILE_DOWNLOAD_FAILED",
                    ) from exc

                with open(local_path, "wb") as output_file:
                    output_file.write(response.content)

                downloaded_files[field_name] = str(local_path)

        return downloaded_files

    @staticmethod
    def _guess_filename(field_name: str, file_url: str) -> str:
        """根据 URL 猜测本地文件名。"""
        parsed = urlparse(file_url)
        basename = os.path.basename(parsed.path)
        if basename:
            return basename
        return f"{field_name}.dat"
