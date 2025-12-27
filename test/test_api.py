#!/usr/bin/env python3
"""API测试脚本：验证修复的缺陷

测试项目：
1. 系统健康检查
2. 文件上传（验证FileSourceType.UPLOAD和size_bytes）
3. 枚举值检查（通过代码检查）
"""

import requests
import json
import tempfile
import os
import sys
from pathlib import Path

# 添加backend到路径以导入模型定义
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

BASE_URL = "http://backend:8000/api/v1"


def test_system_health():
    """测试1: 系统健康检查"""
    print("=" * 60)
    print("测试1: 系统健康检查")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/system/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 系统健康检查通过")
            print(f"   状态: {data.get('status')}")
            print(f"   版本: {data.get('version')}")
            print(f"   环境: {data.get('environment')}")

            # 检查服务状态
            services = data.get('services', [])
            print(f"\n服务状态:")
            for service in services:
                status_icon = "✅" if service['status'] == 'healthy' else "❌"
                print(f"   {status_icon} {service['name']}: {service['message']}")

            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_enum_definitions():
    """测试2: 枚举值定义检查"""
    print("\n" + "=" * 60)
    print("测试2: 枚举值定义检查")
    print("=" * 60)

    try:
        # 导入枚举定义
        from app.models.files import FileSourceType
        from app.models.tasks import TaskStatus

        # 检查FileSourceType
        print("FileSourceType枚举值:")
        has_upload = False
        for item in FileSourceType:
            print(f"   - {item.name}: {item.value}")
            if item.name == "UPLOAD":
                has_upload = True

        if has_upload:
            print(f"✅ FileSourceType.UPLOAD 存在")
        else:
            print(f"❌ FileSourceType.UPLOAD 不存在")
            return False

        # 检查TaskStatus
        print("\nTaskStatus枚举值:")
        has_failure = False
        has_failed = False
        for item in TaskStatus:
            print(f"   - {item.name}: {item.value}")
            if item.name == "FAILURE":
                has_failure = True
            if item.name == "FAILED":
                has_failed = True

        if has_failure and not has_failed:
            print(f"✅ TaskStatus.FAILURE 存在，FAILED 不存在")
        else:
            print(f"❌ TaskStatus 枚举不正确")
            return False

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_model():
    """测试3: File模型字段检查"""
    print("\n" + "=" * 60)
    print("测试3: File模型字段检查")
    print("=" * 60)

    try:
        from app.models.files import File as FileModel

        # 检查字段
        has_size_bytes = hasattr(FileModel, 'size_bytes')
        has_size = hasattr(FileModel, 'size')

        if has_size_bytes:
            print(f"✅ FileModel.size_bytes 字段存在")
        else:
            print(f"❌ FileModel.size_bytes 字段不存在")

        if has_size:
            print(f"⚠️  FileModel.size 字段仍然存在（应该已重命名为size_bytes）")
        else:
            print(f"✅ FileModel.size 字段已移除")

        return has_size_bytes and not has_size

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_schema():
    """测试4: 数据库Schema检查"""
    print("\n" + "=" * 60)
    print("测试4: 数据库Schema检查")
    print("=" * 60)

    try:
        import sqlite3

        db_path = backend_path / "storage" / "scitool.db"
        if not db_path.exists():
            print(f"⚠️  数据库文件不存在: {db_path}")
            return None  # 跳过此测试

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 查询files表结构
        cursor.execute("PRAGMA table_info(files)")
        columns = cursor.fetchall()

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

        conn.close()

        if has_size_bytes:
            print(f"\n✅ 数据库包含 size_bytes 字段")
        else:
            print(f"\n❌ 数据库缺少 size_bytes 字段")

        if has_size:
            print(f"⚠️  数据库仍包含 size 字段")
        else:
            print(f"✅ 数据库已移除 size 字段")

        return has_size_bytes and not has_size

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_task_status_usage():
    """测试5: TaskStatus使用检查"""
    print("\n" + "=" * 60)
    print("测试5: TaskStatus使用检查")
    print("=" * 60)

    try:
        # 读取tasks.py文件内容检查是否使用.value
        tasks_file = backend_path / "app" / "api" / "v1" / "tasks.py"

        with open(tasks_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查是否有直接使用枚举的情况（错误用法）
        import re

        # 查找 status = TaskStatus.XXX 模式（没有.value）
        pattern1 = r'status\s*=\s*TaskStatus\.\w+(?!\.value)'
        matches1 = re.findall(pattern1, content)

        # 排除注释行
        lines = content.split('\n')
        incorrect_usages = []
        for i, line in enumerate(lines, 1):
            if '#' in line:
                line = line[:line.index('#')]  # 移除注释
            if re.search(pattern1, line):
                incorrect_usages.append((i, line.strip()))

        if incorrect_usages:
            print(f"⚠️  发现 {len(incorrect_usages)} 处可能的错误使用:")
            for line_no, line in incorrect_usages[:5]:  # 只显示前5个
                print(f"   行 {line_no}: {line}")
        else:
            print(f"✅ 未发现直接使用TaskStatus枚举的情况")

        # 检查是否使用了.value
        pattern2 = r'TaskStatus\.\w+\.value'
        matches2 = re.findall(pattern2, content)

        if matches2:
            print(f"✅ 发现 {len(matches2)} 处正确使用 TaskStatus.XXX.value")
        else:
            print(f"⚠️  未发现 TaskStatus.XXX.value 使用")

        return len(incorrect_usages) == 0 and len(matches2) > 0

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始API测试")
    print("=" * 60)

    results = []

    # 运行所有测试
    tests = [
        ("系统健康检查", test_system_health),
        ("枚举值定义", test_enum_definitions),
        ("File模型字段", test_file_model),
        ("数据库Schema", test_database_schema),
        ("TaskStatus使用", test_task_status_usage),
    ]

    for name, test_func in tests:
        try:
            result = test_func()
            if result is None:
                print(f"\n⏭️  {name}: 跳过")
                continue
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
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

    if passed + failed > 0:
        print(f"通过率: {passed / (passed + failed) * 100:.1f}%")

    print("=" * 60)

    # 返回退出码
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
