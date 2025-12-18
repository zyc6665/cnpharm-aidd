# LVPocket Service 架构设计文档

**版本**: v1.0
**最后更新**: 2025-12-17
**适用对象**: 开发者、运维人员

---

## 1. 系统概述

LVPocket Service 是基于 LV_NET 深度学习模型的蛋白质结合口袋预测服务，以 Docker 容器形式部署，通过 RESTful API 对外提供服务。

### 1.1 核心功能

- 蛋白质结合口袋位置预测
- 多种输出格式支持（MOL2、CMAP、CUBE）
- 批量预测处理
- 文件格式转换
- **多模型支持**：根据蛋白质二级结构（SCOP 分类）选择最优模型

### 1.2 技术栈

| 组件 | 技术选型 | 版本 |
|------|----------|------|
| Web 框架 | FastAPI | 0.68.x |
| 深度学习 | TensorFlow-GPU | 1.15 |
| 模型架构 | LV_NET (3D CNN + Transformer) | - |
| 容器运行时 | NVIDIA Docker | CUDA 10.0 |
| Python | Python | 3.7 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         平台侧（已有）                           │
│  ┌──────────────┐    ┌──────────┐    ┌───────────────────┐     │
│  │   平台 API    │───▶│  Redis   │───▶│   Celery Worker   │     │
│  │  (任务调度)   │    │  (队列)   │    │    (任务执行)      │     │
│  └──────────────┘    └──────────┘    └─────────┬─────────┘     │
└────────────────────────────────────────────────┼───────────────┘
                                                 │ HTTP Request
                                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LVPocket Service Container                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                      FastAPI Application                    │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐   │ │
│  │  │                    API Layer                         │   │ │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐  │   │ │
│  │  │  │ /health │ │/predict │ │ /batch  │ │ /convert  │  │   │ │
│  │  │  └─────────┘ └─────────┘ └─────────┘ └───────────┘  │   │ │
│  │  └──────────────────────────┬──────────────────────────┘   │ │
│  │                             │                               │ │
│  │  ┌──────────────────────────▼──────────────────────────┐   │ │
│  │  │                    Core Layer                        │   │ │
│  │  │  ┌─────────────────┐  ┌─────────────────────────┐   │   │ │
│  │  │  │  LVPocket Core  │  │    File Handler         │   │   │ │
│  │  │  │  (模型推理封装)  │  │  (文件上传/下载/临时)    │   │   │ │
│  │  │  └────────┬────────┘  └─────────────────────────┘   │   │ │
│  │  │           │                                          │   │ │
│  │  │  ┌────────▼────────┐  ┌─────────────────────────┐   │   │ │
│  │  │  │   Model Pool    │  │     Converters          │   │   │ │
│  │  │  │  (模型预加载)    │  │  (MOL2/CMAP/CUBE)       │   │   │ │
│  │  │  └─────────────────┘  └─────────────────────────┘   │   │ │
│  │  └──────────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Infrastructure Layer                     │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │ │
│  │  │  CUDA Runtime   │  │  TensorFlow 1.15│  │  OpenBabel │  │ │
│  │  │    (GPU 加速)    │  │   (深度学习)     │  │ (分子处理) │  │ │
│  │  └─────────────────┘  └─────────────────┘  └────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 组件说明

#### API Layer（API 层）

| 组件 | 职责 |
|------|------|
| Routes | 定义 HTTP 端点和请求处理逻辑 |
| Schemas | Pydantic 数据模型，请求/响应验证 |
| Dependencies | FastAPI 依赖注入，模型加载器等 |

#### Core Layer（核心层）

| 组件 | 职责 |
|------|------|
| LVPocket Core | 封装 LV_NET 模型，提供预测接口 |
| File Handler | 处理文件上传、下载、临时文件管理 |
| Model Pool | 模型预加载和生命周期管理 |
| Converters | 输出格式转换（MOL2、CMAP、CUBE） |

#### Infrastructure Layer（基础设施层）

| 组件 | 职责 |
|------|------|
| CUDA Runtime | GPU 计算加速支持 |
| TensorFlow 1.15 | 深度学习推理引擎 |
| OpenBabel | 分子文件格式处理 |

---

## 3. 数据流

### 3.1 单次预测流程

```
┌────────┐     ┌─────────┐     ┌──────────┐     ┌─────────┐
│ Client │────▶│ /predict│────▶│ Validate │────▶│  Parse  │
│        │     │ endpoint│     │  Input   │     │  File   │
└────────┘     └─────────┘     └──────────┘     └────┬────┘
                                                     │
    ┌────────────────────────────────────────────────┘
    │
    ▼
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌────────┐
│ Feature │────▶│  Model   │────▶│  Post    │────▶│ Format │
│ Extract │     │ Predict  │     │ Process  │     │ Output │
└─────────┘     └──────────┘     └──────────┘     └───┬────┘
                                                      │
    ┌─────────────────────────────────────────────────┘
    │
    ▼
┌──────────┐
│ Response │
│  JSON    │
└──────────┘
```

### 3.2 数据流详解

1. **输入验证**: 检查文件格式、大小、必填参数
2. **文件解析**: 使用 OpenBabel 解析 PDB/MOL2 文件
3. **特征提取**: 使用 tfbio.Featurizer 生成 4D 特征图
4. **模型预测**: LV_NET 前向传播，输出口袋密度
5. **后处理**: 阈值过滤、连通域分析、口袋中心提取
6. **格式化输出**: 根据请求转换为指定格式

---

## 4. 部署架构

### 4.1 容器配置

```yaml
# Docker 资源配置
resources:
  gpu: 1                    # GPU 数量
  gpu_memory: 8GB          # GPU 显存
  cpu: 4                   # CPU 核心数
  memory: 16GB             # 内存
```

### 4.2 网络配置

```
┌─────────────────────────────────────┐
│          Docker Network             │
│                                     │
│  ┌─────────────────────────────┐   │
│  │    lvpocket-service         │   │
│  │    Port: 8000               │   │
│  │    Protocol: HTTP           │   │
│  └─────────────────────────────┘   │
│                                     │
└─────────────────────────────────────┘
         │
         │ Port Mapping: 8000:8000
         ▼
    Host Network
```

### 4.3 数据卷挂载

| 容器路径 | 宿主机路径 | 用途 |
|----------|------------|------|
| `/app/model` | `./model` | 模型文件 |
| `/app/data/input` | `./data/input` | 输入文件 |
| `/app/data/output` | `./data/output` | 输出文件 |
| `/tmp/lvpocket` | - | 临时文件（tmpfs） |

---

## 5. 模型管理

### 5.1 多模型支持（SCOP 结构分类）

LVPocket Service 支持根据蛋白质二级结构选择对应的预训练模型，以获得更好的预测效果。

**SCOP 结构分类说明**:

| 分类 | 模型文件 | 说明 |
|------|----------|------|
| `baseline` | `scale_0.5_1.h5` | 基线模型，适用于所有蛋白质（默认） |
| `alpha` | `alpha_model.h5` | α 类蛋白质，主要由 α 螺旋组成 |
| `beta` | `beta_model.h5` | β 类蛋白质，主要由 β 折叠组成 |
| `alpha_beta` | `alpha_beta_model.h5` | α/β 类蛋白质，α 螺旋和 β 折叠交替排列 |
| `alpha_plus_beta` | `alpha_plus_beta_model.h5` | α+β 类蛋白质，α 螺旋和 β 折叠分离排列 |

### 5.2 模型加载策略

```python
# 启动时预加载默认模型，支持动态切换
class ModelManager:
    def __init__(self):
        self.predictor = None
        self.load_on_startup()

    def load_on_startup(self):
        """应用启动时加载默认模型到 GPU"""
        self.predictor = LVPocketPredictor(
            model_path=None,  # 使用 structure_class 自动选择
            scale=settings.SCALE,
            max_dist=settings.MAX_DIST,
            structure_class=settings.DEFAULT_MODEL  # 默认 baseline
        )

# 预测时动态切换模型
result = predictor.predict(
    protein_file=protein_path,
    threshold=0.5,
    structure_class="alpha"  # 切换到 α 类模型
)
```

### 5.3 模型缓存机制

预测器内部维护模型缓存，已加载的模型会被保存在内存中，避免重复加载：

```
┌─────────────────────────────────────────────┐
│              Model Cache                     │
│                                              │
│  ┌──────────────┐  ┌──────────────┐         │
│  │   baseline   │  │    alpha     │  ...    │
│  │  (已加载)    │  │  (按需加载)   │         │
│  └──────────────┘  └──────────────┘         │
│                                              │
│  切换模型时：                                 │
│  1. 检查缓存是否存在                          │
│  2. 存在则直接使用                            │
│  3. 不存在则加载并缓存                        │
└─────────────────────────────────────────────┘
```

### 5.4 模型版本管理

支持通过环境变量配置模型版本：

```bash
MODEL_DIR=/app/model/LVpocket/trained_model  # 模型目录
MODEL_PATH=/app/model/LVpocket/trained_model/scale_0.5_1.h5  # 默认模型（兼容）
MODEL_VERSION=1.0.0                           # 模型版本标识
DEFAULT_STRUCTURE_CLASS=baseline              # 默认结构分类
```

---

## 6. 错误处理

### 6.1 错误码定义

| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| 1001 | 400 | 无效的输入文件格式 |
| 1002 | 400 | 文件大小超出限制 |
| 1003 | 400 | 缺少必填参数 |
| 2001 | 500 | 模型加载失败 |
| 2002 | 500 | 预测过程出错 |
| 2003 | 500 | 输出格式转换失败 |
| 3001 | 503 | 服务不可用（GPU 异常） |

### 6.2 错误响应格式

```json
{
  "success": false,
  "error": {
    "code": 1001,
    "message": "Invalid input file format. Expected PDB or MOL2.",
    "details": {
      "received_format": "xyz",
      "supported_formats": ["pdb", "mol2"]
    }
  }
}
```

---

## 7. 性能优化

### 7.1 优化策略

| 策略 | 说明 |
|------|------|
| 模型预加载 | 启动时加载模型，避免请求时延迟 |
| GPU 内存优化 | 配置 TF 按需分配 GPU 内存 |
| 异步文件 IO | 使用 aiofiles 异步处理文件 |
| 连接池 | 复用模型会话，减少创建开销 |

### 7.2 性能指标

| 指标 | 目标值 |
|------|--------|
| 单次预测延迟 | < 5s（中等大小蛋白） |
| 批量吞吐量 | > 10 个/分钟 |
| GPU 利用率 | > 70% |
| 内存占用 | < 8GB |

---

## 8. 安全考虑

### 8.1 输入验证

- 文件大小限制（默认 50MB）
- 文件格式白名单
- 参数范围校验

### 8.2 资源限制

- 请求超时（默认 300s）
- 并发请求限制
- GPU 显存限制

---

## 9. 监控与日志

### 9.1 健康检查端点

```
GET /health
Response: {
  "status": "healthy",
  "model_loaded": true,
  "gpu_available": true,
  "version": "1.0.0"
}
```

### 9.2 日志格式

```
2025-12-17 10:30:00 | INFO | predict | task_id=xxx | Processing protein.pdb
2025-12-17 10:30:03 | INFO | predict | task_id=xxx | Found 3 pockets
2025-12-17 10:30:03 | INFO | predict | task_id=xxx | Completed in 3.2s
```

---

## 附录 A：环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MODEL_DIR` | `/app/model/LVpocket/trained_model` | 模型目录 |
| `MODEL_PATH` | `/app/model/LVpocket/trained_model/scale_0.5_1.h5` | 默认模型文件路径 |
| `DEFAULT_STRUCTURE_CLASS` | `baseline` | 默认结构分类模型 |
| `SCALE` | `0.5` | 体素分辨率 (Å) |
| `MAX_DIST` | `35.0` | 最大距离阈值 |
| `DEFAULT_THRESHOLD` | `0.5` | 口袋预测阈值 |
| `DEFAULT_MIN_SIZE` | `50` | 最小口袋体素数 |
| `MAX_FILE_SIZE` | `52428800` | 最大文件大小 (50MB) |
| `REQUEST_TIMEOUT` | `300` | 请求超时时间 (秒) |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 附录 B：参考资源

- [LVPocket 原始论文](https://example.com/lvpocket-paper)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- [平台工具添加指南](../../docs/guides/工具添加指南.md)
