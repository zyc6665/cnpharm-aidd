#!/usr/bin/env python3
"""测试脚本：验证修复的缺陷和新功能

测试项目：
1. FileSourceType.UPLOAD 枚举值修复
2. File.size_bytes 字段修复
3. TaskStatus 类型使用修复
4. 执行器文件处理功能
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from sqlalchemy import select
from app.database.session import get_async_session
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task, TaskStatus
from app.models.users import User


async def test_file_source_type_enum():
    """测试1: FileSourceType.UPLOAD 枚举值存在"""
    print("=" * 60)
    print("测试1: FileSourceType.UPLOAD 枚举值")
    print("=" * 60)

    try:
        # 检查UPLOAD枚举值是否存在
        upload_value = FileSourceType.UPLOAD
        print(f"✅ FileSourceType.UPLOAD 存在")
        print(f"   值: {upload_value.value}")

        # 检查所有枚举值
        print(f"\n所有FileSourceType枚举值:")
        for item in FileSourceType:
            print(f"   - {item.name}: {item.value}")

        return True
    except AttributeError as e:
        print(f"❌ FileSourceType.UPLOAD 不存在: {e}")
        return False


async def test_file_model_field():
    """测试2: File模型的size_bytes字段"""
    print("\n" + "=" * 60)
    print("测试2: File.size_bytes 字段")
    print("=" * 60)

    try:
        # 检查FileModel是否有size_bytes属性
        if hasattr(FileModel, 'size_bytes'):
            print(f"✅ FileModel.size_bytes 字段存在")
        else:
            print(f"❌ FileModel.size_bytes 字段不存在")
            return False

        # 检查是否有旧的size字段
        if hasattr(FileModel, 'size'):
            print(f"⚠️  FileModel.size 字段仍然存在（应该已重命名）")
        else:
            print(f"✅ FileModel.size 字段已移除")

        # 尝试创建一个文件记录测试
        async for session in get_async_session():
            try:
                test_file = FileModel(
                    filename="test.txt",
                    content_type="text/plain",
                    size_bytes=1024,  # 使用size_bytes
                    sha256="test123",
                    source_type=FileSourceType.UPLOAD.value,
                    storage_backend="local",
                    storage_path="/tmp/test.txt"
                )

                session.add(test_file)
                await session.flush()

                print(f"✅ 成功创建测试文件记录")
                print(f"   ID: {test_file.id}")
                print(f"   size_bytes: {test_file.size_bytes}")
                print(f"   source_type: {test_file.source_type}")

                # 清理测试数据
                await session.delete(test_file)
                await session.commit()

                break
            except Exception as e:
                print(f"❌ 创建文件记录失败: {e}")
                await session.rollback()
                return False

        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_task_status_enum():
    """测试3: TaskStatus 枚举值使用"""
    print("\n" + "=" * 60)
    print("测试3: TaskStatus 枚举值")
    print("=" * 60)

    try:
        # 检查所有TaskStatus枚举
        print("所有TaskStatus枚举值:")
        for status in TaskStatus:
            print(f"   - {status.name}: {status.value}")

        # 检查是否有FAILED（应该是FAILURE）
        if hasattr(TaskStatus, 'FAILED'):
            print(f"❌ TaskStatus.FAILED 存在（应该是FAILURE）")
            return False
        else:
            print(f"✅ TaskStatus.FAILED 不存在（正确）")

        if hasattr(TaskStatus, 'FAILURE'):
            print(f"✅ TaskStatus.FAILURE 存在")
        else:
            print(f"❌ TaskStatus.FAILURE 不存在")
            return False

        # 测试值比较
        pending_value = TaskStatus.PENDING.value
        print(f"\n✅ TaskStatus.PENDING.value = '{pending_value}'")

        # 模拟数据库比较
        task_status_from_db = "PENDING"  # 数据库返回的字符串
        if task_status_from_db == TaskStatus.PENDING.value:
            print(f"✅ 字符串比较正确: '{task_status_from_db}' == TaskStatus.PENDING.value")
        else:
            print(f"❌ 字符串比较错误")
            return False

        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_database_schema():
    """测试4: 数据库schema验证"""
    print("\n" + "=" * 60)
    print("测试4: 数据库Schema验证")
    print("=" * 60)

    try:
        async for session in get_async_session():
            # 查询files表结构
            result = await session.execute(
                "PRAGMA table_info(files)"
            )
            columns = result.fetchall()

            print("Files表字段:")
            has_size_bytes = False
            has_size = False

            for col in columns:
                col_name = col[1]
                col_type = col[2]
                print(f"   - {col_name}: {col_type}")

                if col_name == "size_bytes":
                    has_size_bytes = True
                if col_name == "size":
                    has_size = True

            if has_size_bytes:
                print(f"\n✅ 数据库包含 size_bytes 字段")
            else:
                print(f"\n❌ 数据库缺少 size_bytes 字段")

            if has_size:
                print(f"⚠️  数据库仍包含 size 字段（应该已重命名）")
            else:
                print(f"✅ 数据库不包含 size 字段")

            break

        return has_size_bytes and not has_size

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_executor_imports():
    """测试5: 执行器文件处理功能导入"""
    print("\n" + "=" * 60)
    print("测试5: 执行器功能验证")
    print("=" * 60)

    try:
        from app.tasks.executor import (
            DockerExecutor,
            RemoteAPIExecutor,
            TaskExecutor
        )

        print("✅ 执行器模块导入成功")

        # 检查方法是否存在
        docker_methods = [
            '_prepare_input_files',
            '_collect_output_files'
        ]

        for method in docker_methods:
            if hasattr(DockerExecutor, method):
                print(f"✅ DockerExecutor.{method} 存在")
            else:
                print(f"❌ DockerExecutor.{method} 不存在")
                return False

        if hasattr(RemoteAPIExecutor, '_process_output_files'):
            print(f"✅ RemoteAPIExecutor._process_output_files 存在")
        else:
            print(f"❌ RemoteAPIExecutor._process_output_files 不存在")
            return False

        return True

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始测试修复功能")
    print("=" * 60)

    results = []

    # 运行所有测试
    tests = [
        ("FileSourceType.UPLOAD枚举", test_file_source_type_enum),
        ("File.size_bytes字段", test_file_model_field),
        ("TaskStatus枚举", test_task_status_enum),
        ("数据库Schema", test_database_schema),
        ("执行器功能", test_executor_imports),
    ]

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            results.append((name, False))

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"总计: {passed + failed} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")
    print(f"通过率: {passed / (passed + failed) * 100:.1f}%")
    print("=" * 60)

    # 返回退出码
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
