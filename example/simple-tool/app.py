"""
简单的文本处理工具 - 用于测试平台集成
功能：接收文本输入，进行简单的处理（转大写、统计字数等）
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import uvicorn
import time

app = FastAPI(
    title="Simple Text Tool",
    description="简单的文本处理工具，用于测试SciTool平台集成",
    version="1.0.0"
)


# ==================== 数据模型 ====================

class TextProcessRequest(BaseModel):
    """文本处理请求"""
    task_id: str = Field(..., description="任务ID")
    params: dict = Field(..., description="处理参数")
    input_files: Optional[dict] = Field(None, description="输入文件（可选）")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "test-123",
                "params": {
                    "text": "Hello World",
                    "operation": "uppercase",
                    "add_stats": True
                },
                "input_files": {}
            }
        }


class TextProcessResponse(BaseModel):
    """文本处理响应"""
    success: bool = Field(..., description="是否成功")
    task_id: str = Field(..., description="任务ID")
    result: Optional[dict] = Field(None, description="处理结果")
    error: Optional[dict] = Field(None, description="错误信息")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "task_id": "test-123",
                "result": {
                    "processed_text": "HELLO WORLD",
                    "statistics": {
                        "char_count": 11,
                        "word_count": 2
                    }
                },
                "error": None
            }
        }


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    version: str


# ==================== API 端点 ====================

@app.get("/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "simple-text-tool",
        "version": "1.0.0"
    }


@app.post("/process", response_model=TextProcessResponse, tags=["文本处理"])
async def process_text(request: TextProcessRequest):
    """
    处理文本

    支持的操作：
    - uppercase: 转换为大写
    - lowercase: 转换为小写
    - reverse: 反转文本
    - stats: 统计信息
    """
    try:
        # 提取参数
        text = request.params.get("text", "")
        operation = request.params.get("operation", "uppercase")
        add_stats = request.params.get("add_stats", False)

        # 验证输入
        if not text:
            raise ValueError("文本内容不能为空")

        # 模拟处理时间
        time.sleep(0.5)

        # 执行操作
        processed_text = text
        if operation == "uppercase":
            processed_text = text.upper()
        elif operation == "lowercase":
            processed_text = text.lower()
        elif operation == "reverse":
            processed_text = text[::-1]
        elif operation == "stats":
            processed_text = text
        else:
            raise ValueError(f"不支持的操作: {operation}")

        # 构建结果
        result = {
            "processed_text": processed_text,
            "operation": operation
        }

        # 添加统计信息
        if add_stats:
            result["statistics"] = {
                "char_count": len(text),
                "word_count": len(text.split()),
                "line_count": len(text.splitlines())
            }

        return {
            "success": True,
            "task_id": request.task_id,
            "result": result,
            "error": None
        }

    except ValueError as e:
        return {
            "success": False,
            "task_id": request.task_id,
            "result": None,
            "error": {
                "code": 1001,
                "message": str(e)
            }
        }
    except Exception as e:
        return {
            "success": False,
            "task_id": request.task_id,
            "result": None,
            "error": {
                "code": 1000,
                "message": f"处理失败: {str(e)}"
            }
        }


if __name__ == "__main__":
    uvicorn.run(
        app="app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
