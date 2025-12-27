#!/usr/bin/env python3
"""
工具创建助手脚本

使用方法:
    python create_tool.py --config tool_config.json
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# 切换到脚本所在目录
script_dir = Path(__file__).parent
os.chdir(script_dir / "backend")

sys.path.insert(0, str(script_dir / "backend"))


async def create_tool_from_config(config_file: str):
    """从配置文件创建工具"""
    from app.database.session import get_db
    from app.models.tools import Tool, ToolVersion, ToolStatus, ToolProviderType, ToolReviewStatus
    from app.models.users import User
    from sqlalchemy import select

    # 读取配置（使用绝对路径）
    config_path = script_dir / config_file
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    async for db in get_db():
        try:
            # 获取管理员用户作为owner（或创建测试用户）
            result = await db.execute(
                select(User).where(User.role == "admin").limit(1)
            )
            owner = result.scalar_one_or_none()

            if not owner:
                print("❌ 未找到管理员用户，请先创建用户")
                return False

            # 检查工具是否已存在
            result = await db.execute(
                select(Tool).where(Tool.slug == config["slug"])
            )
            existing_tool = result.scalar_one_or_none()

            if existing_tool:
                print(f"ℹ️  工具已存在: {existing_tool.name} (ID: {existing_tool.id})")
                tool = existing_tool
            else:
                # 创建工具
                tool = Tool(
                    owner_id=owner.id,
                    name=config["name"],
                    slug=config["slug"],
                    description=config.get("description", ""),
                    icon=config.get("icon", "🔧"),
                    category=config.get("category", "test"),
                    status=ToolStatus.PUBLISHED.value,
                    is_public=True,
                    provider_type=ToolProviderType.PLATFORM.value,
                    review_status=ToolReviewStatus.NOT_REQUIRED.value
                )

                db.add(tool)
                await db.flush()

                print(f"✅ 工具创建成功: {tool.name} (ID: {tool.id})")

            # 创建工具版本
            tool_version = ToolVersion(
                tool_id=tool.id,
                version=config.get("version", "1.0.0"),
                changelog=config.get("changelog", "Initial version"),
                config=config["tool_config"],
                is_active=True
            )

            db.add(tool_version)
            await db.flush()

            # 设置为当前版本
            tool.current_version_id = tool_version.id

            await db.commit()
            await db.refresh(tool)
            await db.refresh(tool_version)

            print(f"✅ 工具版本创建成功: {tool_version.version} (ID: {tool_version.id})")
            print(f"\n工具信息:")
            print(f"  名称: {tool.name}")
            print(f"  Slug: {tool.slug}")
            print(f"  ID: {tool.id}")
            print(f"  版本ID: {tool_version.id}")
            print(f"  类型: {config['tool_config']['type']}")

            return {
                "tool_id": tool.id,
                "version_id": tool_version.id,
                "tool": tool,
                "version": tool_version
            }

        except Exception as e:
            print(f"❌ 创建失败: {e}")
            await db.rollback()
            import traceback
            traceback.print_exc()
            return False


async def test_tool(tool_id: str, version_id: str, test_params: dict):
    """测试工具"""
    from app.tasks.executor import TaskExecutor
    from app.models.tasks import Task, TaskInput, TaskStatus
    from app.models.tools import ToolVersion
    from app.database.session import get_db
    from sqlalchemy import select

    async for db in get_db():
        try:
            # 获取工具版本
            result = await db.execute(
                select(ToolVersion).where(ToolVersion.id == version_id)
            )
            tool_version = result.scalar_one_or_none()

            if not tool_version:
                print(f"❌ 工具版本不存在: {version_id}")
                return False

            # 创建测试任务
            task = Task(
                tool_id=tool_id,
                tool_version_id=version_id,
                status=TaskStatus.PENDING.value,
                priority="normal"
            )

            db.add(task)
            await db.flush()

            # 创建任务输入
            task_input = TaskInput(
                task_id=task.id,
                params=test_params
            )

            db.add(task_input)
            task.inputs = task_input
            await db.commit()
            await db.refresh(task)

            print(f"\n🧪 测试任务创建成功: {task.id}")
            print(f"   工具: {tool_version.tool.name}")
            print(f"   版本: {tool_version.version}")
            print(f"   参数: {json.dumps(test_params, indent=2, ensure_ascii=False)}")

            # 执行任务
            print(f"\n⏳ 开始执行任务...")
            executor = TaskExecutor(task, tool_version)

            try:
                result = await executor.execute()

                print(f"\n✅ 任务执行成功!")
                print(f"   结果: {json.dumps(result, indent=2, ensure_ascii=False)}")

                return True

            except Exception as e:
                print(f"\n❌ 任务执行失败: {e}")
                import traceback
                traceback.print_exc()
                return False

        except Exception as e:
            print(f"❌ 测试失败: {e}")
            await db.rollback()
            import traceback
            traceback.print_exc()
            return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="工具创建和测试助手")
    parser.add_argument("--config", required=True, help="工具配置文件路径")
    parser.add_argument("--test", action="store_true", help="创建后立即测试")
    parser.add_argument("--test-params", help="测试参数JSON文件")

    args = parser.parse_args()

    # 创建工具
    result = asyncio.run(create_tool_from_config(args.config))

    if not result:
        sys.exit(1)

    # 测试工具
    if args.test and args.test_params:
        # 使用绝对路径读取测试参数
        test_params_path = script_dir / args.test_params
        with open(test_params_path, "r", encoding="utf-8") as f:
            test_params = json.load(f)

        success = asyncio.run(test_tool(
            result["tool_id"],
            result["version_id"],
            test_params
        ))

        sys.exit(0 if success else 1)

    sys.exit(0)


if __name__ == "__main__":
    main()
