#!/usr/bin/env python3
"""容器内测试脚本：验证修复的缺陷和新功能"""

import asyncio
import sys
from pathlib import Path

# 确保在backend目录下运行
sys.path.insert(0, str(Path(__file__).parent))


async def test_file_source_type():
    """测试1: FileSourceType.UPLOAD 枚举值"""
    print("=" * 60)
    print("测试1: FileSourceType.UPLOAD 枚举值")
    print("=" * 60)

    from app.models.files import FileSourceType

    try:
        # 检查UPLOAD枚举
        upload = FileSourceType.UPLOAD
        print(f"✅ FileSourceType.UPLOAD 存在: {upload.value}")

        # 列出所有枚举
        print("\n所有FileSourceType枚举:")
        for item in FileSourceType:
            print(f"   - {item.name}: {item.value}")

        return True
    except AttributeError as e:
        print(f"❌ FileSourceType.UPLOAD 不存在: {e}")
        return False


async def test_file_model():
    """测试2: File模型字段"""
    print("\n" + "=" * 60)
    print("测试2: File模型字段")
    print("=" * 60)

    from app.models.files import File as FileModel

    # 检查字段
    has_size_bytes = hasattr(FileModel, 'size_bytes')
    has_size = hasattr(FileModel, 'size')

    if has_size_bytes:
        print(f"✅ FileModel.size_bytes 存在")
    else:
        print(f"❌ FileModel.size_bytes 不存在")

    if has_size:
        print(f"⚠️  FileModel.size 仍存在")
    else:
        print(f"✅ FileModel.size 已移除")

    # 尝试创建测试记录
    from app.database.session import get_async_session
    from app.models.files import FileSourceType

    async for session in get_async_session():
        try:
            test_file = FileModel(
                filename="test.txt",
                content_type="text/plain",
                size_bytes=1024,
                sha256="abc123",
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

            # 清理
            await session.delete(test_file)
            await session.commit()
            break

        except Exception as e:
            print(f"❌ 创建失败: {e}")
            await session.rollback()
            return False

    return has_size_bytes and not has_size


async def test_task_status():
    """测试3: TaskStatus 枚举"""
    print("\n" + "=" * 60)
    print("测试3: TaskStatus 枚举")
    print("=" * 60)

    from app.models.tasks import TaskStatus

    # 列出所有枚举
    print("所有TaskStatus枚举:")
    for item in TaskStatus:
        print(f"   - {item.name}: {item.value}")

    # 检查FAILURE vs FAILED
    has_failure = hasattr(TaskStatus, 'FAILURE')
    has_failed = hasattr(TaskStatus, 'FAILED')

    if has_failure:
        print(f"✅ TaskStatus.FAILURE 存在")
    else:
        print(f"❌ TaskStatus.FAILURE 不存在")

    if has_failed:
        print(f"❌ TaskStatus.FAILED 存在（应该是FAILURE）")
        return False
    else:
        print(f"✅ TaskStatus.FAILED 不存在")

    # 测试.value使用
    pending_value = TaskStatus.PENDING.value
    print(f"\n✅ TaskStatus.PENDING.value = '{pending_value}'")

    # 模拟字符串比较
    db_value = "PENDING"
    if db_value == TaskStatus.PENDING.value:
        print(f"✅ 字符串比较正确")
    else:
        print(f"❌ 字符串比较失败")
        return False

    return has_failure and not has_failed


async def test_database_schema():
    """测试4: 数据库Schema"""
    print("\n" + "=" * 60)
    print("测试4: 数据库Schema")
    print("=" * 60)

    import sqlite3
    from app.config import settings

    db_path = Path(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))

    if not db_path.exists():
        print(f"⚠️  数据库不存在: {db_path}")
        return None

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 查询files表
    cursor.execute("PRAGMA table_info(files)")
    columns = cursor.fetchall()

    print("Files表字段:")
    has_size_bytes = False
    has_size = False

    for col in columns:
        col_name = col[1]
        if col_name in ["size_bytes", "size", "filename", "sha256"]:
            print(f"   - {col_name}: {col[2]}")

        if col_name == "size_bytes":
            has_size_bytes = True
        if col_name == "size":
            has_size = True

    conn.close()

    if has_size_bytes:
        print(f"\n✅ 数据库有 size_bytes 字段")
    else:
        print(f"\n❌ 数据库缺少 size_bytes 字段")

    if has_size:
        print(f"⚠️  数据库仍有 size 字段")
    else:
        print(f"✅ 数据库无 size 字段")

    return has_size_bytes and not has_size


async def test_executor_methods():
    """测试5: 执行器方法实现"""
    print("\n" + "=" * 60)
    print("测试5: 执行器方法实现")
    print("=" * 60)

    from app.tasks.executor import DockerExecutor, RemoteAPIExecutor
    import inspect

    # 检查DockerExecutor方法
    methods_to_check = ['_prepare_input_files', '_collect_output_files']

    for method in methods_to_check:
        if hasattr(DockerExecutor, method):
            func = getattr(DockerExecutor, method)
            source = inspect.getsource(func)

            # 检查是否还是占位实现（只有pass）
            if 'pass' in source and source.count('\n') < 10:
                print(f"⚠️  {method} 可能是占位实现")
            else:
                print(f"✅ DockerExecutor.{method} 已实现")
        else:
            print(f"❌ DockerExecutor.{method} 不存在")
            return False

    # 检查RemoteAPIExecutor
    if hasattr(RemoteAPIExecutor, '_process_output_files'):
        func = getattr(RemoteAPIExecutor, '_process_output_files')
        source = inspect.getsource(func)

        if 'uuid.uuid4()' in source and 'FileModel' not in source:
            print(f"⚠️  _process_output_files 可能是占位实现")
        else:
            print(f"✅ RemoteAPIExecutor._process_output_files 已实现")
    else:
        print(f"❌ RemoteAPIExecutor._process_output_files 不存在")
        return False

    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("容器内测试开始")
    print("=" * 60)

    tests = [
        ("FileSourceType.UPLOAD", test_file_source_type),
        ("File.size_bytes字段", test_file_model),
        ("TaskStatus枚举", test_task_status),
        ("数据库Schema", test_database_schema),
        ("执行器方法", test_executor_methods),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            if result is None:
                print(f"\n⏭️  {name}: 跳过")
                continue
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")

    print("\n" + "=" * 60)
    print(f"通过: {passed}/{len(results)}")
    print(f"失败: {failed}/{len(results)}")
    if results:
        print(f"通过率: {passed/len(results)*100:.0f}%")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
