# 执行器文件处理功能实施报告

**日期**: 2024-12-20
**优先级**: P0（核心功能）
**状态**: ✅ 已完成

---

## 📋 实施概览

完成了执行器中3个占位实现的文件处理方法，使任务执行器能够正确处理输入和输出文件。

---

## ✅ 已实现的功能

### 1. DockerExecutor._prepare_input_files()

**位置**: backend/app/tasks/executor.py:309-357

**功能**: 从数据库获取任务输入文件，复制到Docker工作目录

**实现细节**:
```python
async def _prepare_input_files(self) -> None:
    """准备输入文件"""
    # 1. 检查是否有输入文件
    if not self.task.inputs or not self.task.inputs.file_ids:
        return

    # 2. 遍历文件ID列表
    for file_id in self.task.inputs.file_ids:
        # 3. 从数据库查询文件记录
        file_record = await session.execute(
            select(FileModel).where(FileModel.id == file_id)
        ).scalar_one_or_none()

        # 4. 验证文件存在
        if not file_record or not os.path.exists(file_record.storage_path):
            raise TaskExecutionError(...)

        # 5. 复制到工作目录
        dst_path = os.path.join(input_dir, file_record.filename)
        shutil.copy2(file_record.storage_path, dst_path)
```

**处理流程**:
```
任务输入文件ID列表
    ↓
查询数据库获取FileModel记录
    ↓
检查storage_path是否存在
    ↓
复制文件到 /tmp/tasks/{task_id}/input/
    ↓
Docker容器挂载 /workspace/input/
```

**错误处理**:
- 文件记录不存在 → 警告并跳过
- 存储文件缺失 → 抛出TaskExecutionError
- 复制失败 → 抛出TaskExecutionError（含详细信息）

---

### 2. DockerExecutor._collect_output_files()

**位置**: backend/app/tasks/executor.py:359-431

**功能**: 收集Docker容器输出目录的文件，上传到存储系统

**实现细节**:
```python
async def _collect_output_files(self) -> List[str]:
    """收集输出文件"""
    # 1. 扫描输出目录
    for filename in os.listdir(output_dir):
        # 2. 读取文件内容
        with open(file_path, "rb") as f:
            content = f.read()

        # 3. 计算SHA256哈希
        sha256_hash = hashlib.sha256(content).hexdigest()

        # 4. 创建文件记录
        file_record = FileModel(
            filename=filename,
            size_bytes=len(content),
            sha256=sha256_hash,
            source_type=FileSourceType.TOOL_OUTPUT.value,
            owner_id=self.task.user_id
        )

        # 5. 保存到存储
        storage_path = get_file_path(file_record.id, filename)
        shutil.copy2(file_path, str(storage_path))

        # 6. 更新数据库
        file_record.storage_path = str(storage_path)
        await session.commit()

        # 7. 返回文件ID
        uploaded_ids.append(file_record.id)
```

**处理流程**:
```
Docker输出目录: /tmp/tasks/{task_id}/output/
    ↓
扫描所有文件
    ↓
逐个处理:
  - 读取内容
  - 计算SHA256
  - 创建FileModel记录
  - 保存到 storage/{id[:2]}/{id}_{filename}
  - 提交数据库
    ↓
返回文件ID列表 → TaskOutput.output_file_ids
```

**存储路径规则**:
```python
# 使用文件ID前两位作为子目录
file_id = "abc123..."
filename = "result.txt"

# 存储路径
storage_path = "storage/ab/abc123_result.txt"
```

**错误处理**:
- 单个文件处理失败 → 记录错误并继续
- 全部失败 → 抛出TaskExecutionError
- 自动回滚事务

---

### 3. RemoteAPIExecutor._process_output_files()

**位置**: backend/app/tasks/executor.py:177-253

**功能**: 从远程API响应的URL下载输出文件，上传到存储系统

**实现细节**:
```python
async def _process_output_files(self, output_files: List[Dict]) -> List[str]:
    """处理输出文件"""
    for file_info in output_files:
        url = file_info.get("url")
        filename = file_info.get("filename", f"output_{uuid.uuid4()}.dat")

        # 1. 从远程URL下载
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(url)
            content = response.content

        # 2. 计算文件信息
        sha256_hash = hashlib.sha256(content).hexdigest()
        content_type = response.headers.get("content-type")

        # 3. 创建文件记录
        file_record = FileModel(...)

        # 4. 保存到存储
        storage_path = get_file_path(file_record.id, filename)
        with open(storage_path, "wb") as f:
            f.write(content)

        # 5. 返回文件ID
        uploaded_ids.append(file_record.id)
```

**处理流程**:
```
远程API响应:
{
  "output_files": [
    {"url": "https://api.example.com/result.zip", "filename": "result.zip"},
    {"url": "https://api.example.com/plot.png", "filename": "plot.png"}
  ]
}
    ↓
遍历每个文件:
  - HTTP GET下载文件
  - 计算SHA256和大小
  - 提取Content-Type
  - 创建FileModel记录
  - 保存到本地存储
  - 提交数据库
    ↓
返回文件ID列表
```

**超时处理**:
- 下载超时: 300秒
- 单个文件失败不影响其他文件
- HTTPError自动捕获并记录

---

## 📊 实施统计

### 代码修改

| 方法 | 修改类型 | 代码行数 | 复杂度 |
|------|----------|----------|--------|
| _prepare_input_files | 占位→完整实现 | 49行 | 中等 |
| _collect_output_files | 占位→完整实现 | 72行 | 较高 |
| _process_output_files | 占位→完整实现 | 76行 | 较高 |

**总计**: 197行新代码

### 新增依赖

```python
# 数据库操作
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_session

# 文件模型
from app.models.files import File as FileModel, FileSourceType

# 文件路径工具
from app.api.v1.files import get_file_path

# 哈希计算
import hashlib

# 文件操作
import shutil
```

---

## 🔍 关键设计决策

### 1. 数据库会话管理

**选择**: 使用`get_async_session()`独立会话

**原因**:
- 执行器可能在Celery Worker中运行
- 避免与主请求会话冲突
- 自动管理事务提交/回滚

```python
async for session in get_async_session():
    try:
        # 文件操作
        await session.commit()
        break
    except Exception as e:
        await session.rollback()
        raise
```

### 2. 错误处理策略

**级别1**: 单个文件失败
- 记录错误日志
- 继续处理其他文件
- 部分成功可接受

**级别2**: 全部失败
- 回滚数据库事务
- 抛出TaskExecutionError
- 任务状态设为FAILURE

```python
try:
    # 处理单个文件
    ...
except Exception as e:
    logger.error(f"Failed to process file: {e}")
    continue  # 继续处理其他文件
```

### 3. 存储路径设计

**规则**: 使用文件ID前两位作为子目录

**优势**:
- 避免单目录文件过多（性能问题）
- 文件均匀分布（256个子目录）
- 与上传API保持一致

```python
# 示例
file_id = "abc123def456"
filename = "data.csv"

# 子目录: ab/
# 完整路径: storage/ab/abc123def456_data.csv
```

### 4. 文件来源标识

**统一使用**: `FileSourceType.TOOL_OUTPUT.value`

**区别**:
- `USER_INPUT`: 用户直接上传
- `UPLOAD`: 通过上传API
- `TOOL_OUTPUT`: 任务执行结果 ✅
- `SYSTEM`: 系统内部文件

---

## 🧪 测试建议

### 单元测试

```python
# tests/test_executor_files.py

async def test_prepare_input_files():
    """测试输入文件准备"""
    # 1. 创建测试文件
    file_record = await create_test_file(
        filename="input.txt",
        content=b"test data"
    )

    # 2. 创建任务
    task = await create_test_task(file_ids=[file_record.id])

    # 3. 创建执行器
    executor = DockerExecutor(task, tool_version)

    # 4. 执行准备
    await executor._prepare_input_files()

    # 5. 验证文件存在
    work_dir = executor._get_work_dir()
    input_file = os.path.join(work_dir, "input", "input.txt")
    assert os.path.exists(input_file)

    # 6. 验证内容
    with open(input_file, "rb") as f:
        assert f.read() == b"test data"


async def test_collect_output_files():
    """测试输出文件收集"""
    # 1. 创建执行器
    executor = DockerExecutor(task, tool_version)
    work_dir = executor._get_work_dir()
    output_dir = os.path.join(work_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    # 2. 创建测试输出文件
    test_file = os.path.join(output_dir, "result.json")
    with open(test_file, "w") as f:
        f.write('{"status": "success"}')

    # 3. 收集文件
    file_ids = await executor._collect_output_files()

    # 4. 验证返回
    assert len(file_ids) == 1

    # 5. 验证数据库记录
    file_record = await get_file_by_id(file_ids[0])
    assert file_record.filename == "result.json"
    assert file_record.source_type == FileSourceType.TOOL_OUTPUT.value
    assert os.path.exists(file_record.storage_path)


async def test_process_output_files_from_url():
    """测试从URL处理输出文件"""
    # 1. Mock HTTP服务器
    with aioresponses() as m:
        m.get(
            "https://example.com/output.txt",
            body=b"remote content",
            headers={"content-type": "text/plain"}
        )

        # 2. 准备输出文件信息
        output_files = [
            {"url": "https://example.com/output.txt", "filename": "output.txt"}
        ]

        # 3. 创建执行器
        executor = RemoteAPIExecutor(task, tool_version)

        # 4. 处理文件
        file_ids = await executor._process_output_files(output_files)

        # 5. 验证
        assert len(file_ids) == 1
        file_record = await get_file_by_id(file_ids[0])
        assert file_record.content_type == "text/plain"

        with open(file_record.storage_path, "rb") as f:
            assert f.read() == b"remote content"
```

### 集成测试

```python
# tests/integration/test_docker_executor_files.py

async def test_full_docker_workflow_with_files():
    """测试Docker执行器完整文件工作流"""
    # 1. 创建输入文件
    input_file = await create_file(
        filename="input.csv",
        content=b"id,name\n1,Alice\n2,Bob"
    )

    # 2. 创建工具配置（处理CSV文件）
    tool_config = {
        "type": "docker_image",
        "image": "python:3.11-slim",
        "command": [
            "python", "-c",
            """
import csv
import json
with open('/workspace/input/input.csv', 'r') as f:
    reader = csv.DictReader(f)
    data = list(reader)
with open('/workspace/output/result.json', 'w') as f:
    json.dump(data, f)
            """
        ],
        "timeout_sec": 30
    }

    # 3. 创建任务
    task = await create_task(
        tool_config=tool_config,
        file_ids=[input_file.id]
    )

    # 4. 执行任务
    executor = TaskExecutor(task, tool_version)
    result = await executor.execute()

    # 5. 验证执行成功
    assert result["success"] == True

    # 6. 验证输出文件
    output_file_ids = result["result"]["output_file_ids"]
    assert len(output_file_ids) == 1

    # 7. 验证输出内容
    output_file = await get_file_by_id(output_file_ids[0])
    with open(output_file.storage_path, "r") as f:
        data = json.load(f)
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
```

---

## ⚠️ 已知限制

### 1. 大文件处理

**问题**: 一次性读取整个文件到内存

```python
# 当前实现
with open(file_path, "rb") as f:
    content = f.read()  # 全部加载到内存
```

**影响**: 处理GB级文件会导致内存溢出

**改进建议**:
```python
# 分块读取和计算SHA256
sha256_hash = hashlib.sha256()
with open(file_path, "rb") as f:
    while chunk := f.read(8192):
        sha256_hash.update(chunk)

# 分块复制文件
shutil.copyfileobj(src_file, dst_file, length=8192)
```

### 2. 并发文件处理

**问题**: 文件按顺序处理

**影响**: 多个文件时速度较慢

**改进建议**:
```python
# 使用asyncio.gather并发处理
tasks = [
    process_single_file(file_info)
    for file_info in output_files
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 3. 网络下载重试

**问题**: 远程下载失败直接跳过

**改进建议**:
```python
# 添加重试机制
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
```

---

## 🎯 后续优化

### P1 - 性能优化

1. **分块读写大文件** - 1小时
   - 避免内存溢出
   - 支持GB级文件

2. **并发文件处理** - 2小时
   - asyncio.gather
   - 提升多文件处理速度

3. **文件去重优化** - 1小时
   - 检查SHA256避免重复存储
   - 节省存储空间

### P2 - 功能增强

4. **断点续传** - 4小时
   - 下载中断恢复
   - 提高可靠性

5. **文件压缩** - 3小时
   - 自动压缩大文件
   - 节省带宽和存储

6. **文件验证** - 2小时
   - 病毒扫描
   - 文件类型验证
   - 大小限制检查

---

## ✅ 验证清单

- [x] 实现`_prepare_input_files()`
- [x] 实现`_collect_output_files()`
- [x] 实现`_process_output_files()`
- [x] 错误处理完整
- [x] 日志记录完善
- [x] 事务管理正确
- [ ] 单元测试覆盖
- [ ] 集成测试验证
- [ ] 性能测试（大文件）
- [ ] 并发测试

---

## 📚 相关文档

1. **executor_analysis_20251220.md**
   - 执行器分析报告
   - 改进建议

2. **bugfix_report_20251220.md**
   - 缺陷修复报告

3. **work_summary_20251220.md**
   - 工作总结

---

**实施完成时间**: 2024-12-20 16:00
**下一步**: 添加单元测试和集成测试
**预计测试工作量**: 4-6小时
