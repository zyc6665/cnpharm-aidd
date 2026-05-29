"""从 Pydantic Schema 导出平台配置。"""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas import PredictRequest, PredictResponse


OUTPUT_PATH = Path(__file__).parent / "platform_tool.json"


def build_platform_config() -> dict:
    """构建平台导入配置。"""
    return {
        "name": "Remote API Tool Template",
        "slug": "remote-api-tool-template",
        "description": "通用 remote_api 工具服务模板",
        "icon": "🧪",
        "category": "template",
        "version": "0.1.0",
        "changelog": "Initial template version",
        "tool_config": {
            "type": "remote_api",
            "endpoint": "http://remote-api-tool-template:8000/predict",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
            },
            "timeout_sec": 600,
            "input_schema": PredictRequest.model_json_schema(),
            "output_schema": PredictResponse.model_json_schema(),
        },
    }


def main() -> None:
    """导出配置文件。"""
    config = build_platform_config()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output_file:
        json.dump(config, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    print(f"平台配置已导出到: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
