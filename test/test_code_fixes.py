#!/usr/bin/env python3
"""代码修复验证测试 - 不需要数据库连接"""

import sys
from pathlib import Path

# 添加backend路径
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))


def test_file_source_type_enum():
    """测试1: FileSourceType.UPLOAD枚举值"""
    print("=" * 60)
    print("测试1: FileSourceType.UPLOAD枚举值")
    print("=" * 60)

    try:
        # 读取文件内容
        files_model = backend_path / "app" / "models" / "files.py"
        with open(files_model, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查UPLOAD枚举定义
        if 'UPLOAD = "upload"' in content:
            print("✅ FileSourceType.UPLOAD 枚举已定义")

            # 提取枚举定义部分
            import re
            enum_match = re.search(
                r'class FileSourceType.*?:\s*""".*?"""(.*?)(?=\n\nclass|\nclass)',
                content,
                re.DOTALL
            )

            if enum_match:
                enum_content = enum_match.group(1)
                enums = re.findall(r'(\w+)\s*=\s*"([^"]+)"', enum_content)
                print("\n所有枚举值:")
                for name, value in enums:
                    print(f"   - {name}: {value}")

            return True
        else:
            print("❌ FileSourceType.UPLOAD 枚举未定义")
            return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_file_model_field():
    """测试2: File.size_bytes字段"""
    print("\n" + "=" * 60)
    print("测试2: File.size_bytes字段")
    print("=" * 60)

    try:
        files_model = backend_path / "app" / "models" / "files.py"
        with open(files_model, "r", encoding="utf-8") as f:
            content = f.read()

        has_size_bytes = 'size_bytes = Column' in content
        has_size = 'size = Column' in content and 'size_bytes' not in content.split('size = Column')[0]

        if has_size_bytes:
            print("✅ File.size_bytes 字段存在")
        else:
            print("❌ File.size_bytes 字段不存在")

        if has_size:
            print("⚠️  File.size 字段仍存在")
        else:
            print("✅ File.size 字段已移除")

        # 查找字段定义
        import re
        size_match = re.search(r'(size_bytes|size)\s*=\s*Column\([^)]+\)', content)
        if size_match:
            print(f"\n字段定义: {size_match.group(0)}")

        return has_size_bytes and not has_size

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_task_status_enum():
    """测试3: TaskStatus枚举"""
    print("\n" + "=" * 60)
    print("测试3: TaskStatus枚举")
    print("=" * 60)

    try:
        tasks_model = backend_path / "app" / "models" / "tasks.py"
        with open(tasks_model, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取TaskStatus枚举
        import re
        enum_match = re.search(
            r'class TaskStatus.*?:\s*""".*?"""(.*?)(?=\n\nclass|\nclass)',
            content,
            re.DOTALL
        )

        if enum_match:
            enum_content = enum_match.group(1)
            enums = re.findall(r'(\w+)\s*=\s*"([^"]+)"', enum_content)

            print("所有TaskStatus枚举:")
            has_failure = False
            has_failed = False

            for name, value in enums:
                print(f"   - {name}: {value}")
                if name == "FAILURE":
                    has_failure = True
                if name == "FAILED":
                    has_failed = True

            if has_failure:
                print("\n✅ TaskStatus.FAILURE 存在")
            else:
                print("\n❌ TaskStatus.FAILURE 不存在")

            if has_failed:
                print("❌ TaskStatus.FAILED 存在（应该是FAILURE）")
                return False
            else:
                print("✅ TaskStatus.FAILED 不存在")

            return has_failure and not has_failed
        else:
            print("❌ 无法解析TaskStatus枚举")
            return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_task_status_usage():
    """测试4: TaskStatus使用检查"""
    print("\n" + "=" * 60)
    print("测试4: TaskStatus.value使用检查")
    print("=" * 60)

    try:
        tasks_api = backend_path / "app" / "api" / "v1" / "tasks.py"
        with open(tasks_api, "r", encoding="utf-8") as f:
            content = f.read()

        import re

        # 查找所有 .value 使用
        value_usages = re.findall(r'TaskStatus\.\w+\.value', content)

        print(f"✅ 发现 {len(value_usages)} 处使用 TaskStatus.XXX.value")

        # 显示前几个示例
        unique_usages = list(set(value_usages))[:5]
        for usage in unique_usages:
            print(f"   - {usage}")

        # 检查monitoring/alert_rules.py
        alert_rules = backend_path / "app" / "monitoring" / "alert_rules.py"
        if alert_rules.exists():
            with open(alert_rules, "r", encoding="utf-8") as f:
                alert_content = f.read()

            if "TaskStatus.FAILED" in alert_content:
                print("\n❌ alert_rules.py 使用了 TaskStatus.FAILED")
                return False
            elif "TaskStatus.FAILURE.value" in alert_content:
                print("\n✅ alert_rules.py 正确使用 TaskStatus.FAILURE.value")
            else:
                print("\n⚠️  alert_rules.py 未使用TaskStatus")

        return len(value_usages) > 0

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_executor_implementation():
    """测试5: 执行器文件处理实现"""
    print("\n" + "=" * 60)
    print("测试5: 执行器文件处理实现")
    print("=" * 60)

    try:
        executor_file = backend_path / "app" / "tasks" / "executor.py"
        with open(executor_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查方法实现
        methods = [
            ('_prepare_input_files', 'shutil.copy2'),
            ('_collect_output_files', 'FileModel'),
            ('_process_output_files', 'httpx.AsyncClient'),
        ]

        all_implemented = True

        for method_name, keyword in methods:
            # 查找方法定义
            import re
            pattern = rf'async def {method_name}\(.*?\):(.*?)(?=\n    async def |\n    def |\nclass |\Z)'
            match = re.search(pattern, content, re.DOTALL)

            if match:
                method_body = match.group(1)

                # 检查是否是占位实现
                if 'pass' in method_body and len(method_body.strip()) < 50:
                    print(f"⚠️  {method_name} 是占位实现")
                    all_implemented = False
                elif keyword in method_body:
                    print(f"✅ {method_name} 已实现（包含 {keyword}）")
                else:
                    print(f"⚠️  {method_name} 可能未完全实现")
            else:
                print(f"❌ {method_name} 未找到")
                all_implemented = False

        return all_implemented

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_schema():
    """测试6: 数据库Schema"""
    print("\n" + "=" * 60)
    print("测试6: 数据库Schema")
    print("=" * 60)

    try:
        import sqlite3

        db_path = backend_path / "storage" / "scitool.db"
        if not db_path.exists():
            print("⚠️  数据库文件不存在，跳过此测试")
            return None

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(files)")
        columns = cursor.fetchall()

        has_size_bytes = False
        has_size = False

        print("Files表关键字段:")
        for col in columns:
            col_name = col[1]
            if col_name in ['size_bytes', 'size', 'filename', 'source_type']:
                print(f"   - {col_name}: {col[2]}")

            if col_name == "size_bytes":
                has_size_bytes = True
            if col_name == "size":
                has_size = True

        conn.close()

        if has_size_bytes:
            print("\n✅ 数据库有 size_bytes 字段")
        else:
            print("\n❌ 数据库缺少 size_bytes 字段")

        if has_size:
            print("⚠️  数据库仍有 size 字段")
        else:
            print("✅ 数据库无 size 字段")

        return has_size_bytes and not has_size

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("代码修复验证测试")
    print("=" * 60)

    tests = [
        ("FileSourceType.UPLOAD", test_file_source_type_enum),
        ("File.size_bytes字段", test_file_model_field),
        ("TaskStatus枚举", test_task_status_enum),
        ("TaskStatus.value使用", test_task_status_usage),
        ("执行器实现", test_executor_implementation),
        ("数据库Schema", test_database_schema),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            if result is None:
                continue
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            results.append((name, False))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")

    print("\n" + "=" * 60)
    print(f"通过: {passed}/{len(results)}")
    print(f"失败: {failed}/{len(results)}")
    if results:
        print(f"通过率: {passed/len(results)*100:.0f}%")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
