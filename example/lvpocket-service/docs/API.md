# LVPocket Service API 设计文档

**版本**: v1.0
**最后更新**: 2025-12-17
**Base URL**: `http://<host>:8000`

---

## 1. API 概述

### 1.1 设计原则

- 遵循 RESTful 规范
- 兼容平台 `remote_api` 工具调用规范
- 统一的请求/响应格式
- 详细的错误信息

### 1.2 通用请求头

| Header | 必填 | 说明 |
|--------|------|------|
| `Content-Type` | 是 | `application/json` 或 `multipart/form-data` |
| `X-Task-ID` | 否 | 任务追踪 ID |
| `X-Request-ID` | 否 | 请求唯一标识 |

### 1.3 通用响应格式

**成功响应**:
```json
{
  "success": true,
  "result": { ... },
  "output_files": [ ... ]
}
```

**错误响应**:
```json
{
  "success": false,
  "error": {
    "code": 1001,
    "message": "错误描述",
    "details": { ... }
  }
}
```

---

## 2. 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/model/info` | 模型信息 |
| GET | `/formats` | 支持的格式 |
| POST | `/predict` | 单个预测 |
| POST | `/batch` | 批量预测 |
| POST | `/convert` | 格式转换 |

---

## 3. 端点详情

### 3.1 健康检查

检查服务运行状态。

**请求**:
```http
GET /health
```

**响应**:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "gpu_available": true,
  "gpu_name": "NVIDIA Tesla V100",
  "gpu_memory_total": 16384,
  "gpu_memory_used": 2048,
  "version": "1.0.0",
  "uptime": 3600
}
```

**状态码**:
- `200`: 服务健康
- `503`: 服务不可用

---

### 3.2 模型信息

获取加载的模型详细信息，包括所有可用的 SCOP 结构分类模型。

**请求**:
```http
GET /model/info
```

**响应**:
```json
{
  "success": true,
  "result": {
    "model_name": "LV_NET",
    "model_version": "1.0.0",
    "model_path": "/app/model/LVpocket/trained_model/scale_0.5_1.h5",
    "architecture": {
      "type": "LV_NET",
      "v_path": "3D CNN",
      "l_path": "Transformer",
      "num_heads": 12,
      "total_params": "3.7M"
    },
    "config": {
      "scale": 0.5,
      "max_dist": 35.0,
      "input_shape": [36, 36, 36, 18],
      "output_shape": [36, 36, 36, 1]
    },
    "supported_inputs": ["pdb", "mol2"],
    "supported_outputs": ["mol2", "cmap", "cube", "json"],
    "default_structure_class": "baseline",
    "available_models": [
      {
        "structure_class": "baseline",
        "file": "scale_0.5_1.h5",
        "path": "/app/model/LVpocket/trained_model/scale_0.5_1.h5",
        "exists": true,
        "description": "基线模型 - 通用模型，适用于所有蛋白质"
      },
      {
        "structure_class": "alpha",
        "file": "alpha_model.h5",
        "path": "/app/model/LVpocket/trained_model/alpha_model.h5",
        "exists": true,
        "description": "α 类 - 主要由 α 螺旋组成的蛋白质"
      },
      {
        "structure_class": "beta",
        "file": "beta_model.h5",
        "path": "/app/model/LVpocket/trained_model/beta_model.h5",
        "exists": true,
        "description": "β 类 - 主要由 β 折叠组成的蛋白质"
      },
      {
        "structure_class": "alpha_beta",
        "file": "alpha_beta_model.h5",
        "path": "/app/model/LVpocket/trained_model/alpha_beta_model.h5",
        "exists": true,
        "description": "α/β 类 - α 螺旋和 β 折叠交替排列"
      },
      {
        "structure_class": "alpha_plus_beta",
        "file": "alpha_plus_beta_model.h5",
        "path": "/app/model/LVpocket/trained_model/alpha_plus_beta_model.h5",
        "exists": true,
        "description": "α+β 类 - α 螺旋和 β 折叠分离排列"
      }
    ]
  }
}
```

---

### 3.3 支持的格式

获取服务支持的输入输出格式。

**请求**:
```http
GET /formats
```

**响应**:
```json
{
  "success": true,
  "result": {
    "input_formats": [
      {
        "format": "pdb",
        "extension": ".pdb",
        "mime_type": "chemical/x-pdb",
        "description": "Protein Data Bank 格式"
      },
      {
        "format": "mol2",
        "extension": ".mol2",
        "mime_type": "chemical/x-mol2",
        "description": "Tripos MOL2 格式"
      }
    ],
    "output_formats": [
      {
        "format": "json",
        "extension": ".json",
        "description": "JSON 结构化数据"
      },
      {
        "format": "mol2",
        "extension": ".mol2",
        "description": "口袋原子坐标 MOL2 格式"
      },
      {
        "format": "cmap",
        "extension": ".cmap",
        "description": "Chimera 兼容密度图"
      },
      {
        "format": "cube",
        "extension": ".cube",
        "description": "Gaussian Cube 格式密度图"
      }
    ]
  }
}
```

---

### 3.4 单个预测

执行蛋白质结合口袋预测。支持根据蛋白质二级结构选择对应的预训练模型。

**请求方式 1**: JSON（URL 引用文件）

```http
POST /predict
Content-Type: application/json

{
  "task_id": "task-123-456",
  "params": {
    "threshold": 0.5,
    "min_size": 50,
    "output_formats": ["json", "mol2"],
    "structure_class": "baseline"
  },
  "input_files": {
    "protein_file": "https://storage.example.com/proteins/1abc.pdb"
  }
}
```

**请求方式 2**: Multipart（直接上传文件）

```http
POST /predict
Content-Type: multipart/form-data

------boundary
Content-Disposition: form-data; name="protein_file"; filename="protein.pdb"
Content-Type: chemical/x-pdb

[PDB 文件内容]
------boundary
Content-Disposition: form-data; name="params"
Content-Type: application/json

{"threshold": 0.5, "min_size": 50, "output_formats": ["json", "mol2"], "structure_class": "alpha"}
------boundary--
```

**参数说明**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `protein_file` | file/url | 是 | - | 蛋白质结构文件 (PDB/MOL2) |
| `threshold` | float | 否 | 0.5 | 口袋预测阈值 (0-1) |
| `min_size` | int | 否 | 50 | 最小口袋体素数 |
| `output_formats` | array | 否 | ["json"] | 输出格式列表 |
| `structure_class` | string | 否 | "baseline" | 蛋白质结构分类（见下表） |

**结构分类 (structure_class) 说明**:

根据蛋白质的二级结构选择对应的预训练模型，可获得更好的预测效果：

| 值 | 说明 |
|----|------|
| `baseline` | 基线模型（默认），适用于所有蛋白质 |
| `alpha` | α 类蛋白质，主要由 α 螺旋组成 |
| `beta` | β 类蛋白质，主要由 β 折叠组成 |
| `alpha_beta` | α/β 类蛋白质，α 螺旋和 β 折叠交替排列 |
| `alpha_plus_beta` | α+β 类蛋白质，α 螺旋和 β 折叠分离排列 |

**响应**:
```json
{
  "success": true,
  "result": {
    "task_id": "task-123-456",
    "protein_name": "1abc",
    "num_atoms": 1542,
    "num_pockets": 3,
    "processing_time": 2.35,
    "structure_class": "baseline",
    "model_file": "scale_0.5_1.h5",
    "pockets": [
      {
        "id": 1,
        "rank": 1,
        "score": 0.92,
        "volume": 486.5,
        "center": {
          "x": 12.34,
          "y": -5.67,
          "z": 8.90
        },
        "bounding_box": {
          "min": {"x": 8.0, "y": -10.0, "z": 4.0},
          "max": {"x": 17.0, "y": -1.0, "z": 14.0}
        },
        "residues": [
          {"chain": "A", "resname": "LEU", "resid": 45},
          {"chain": "A", "resname": "VAL", "resid": 48},
          {"chain": "A", "resname": "PHE", "resid": 52}
        ]
      },
      {
        "id": 2,
        "rank": 2,
        "score": 0.78,
        "volume": 312.3,
        "center": {"x": -8.12, "y": 15.43, "z": 2.11},
        "bounding_box": {
          "min": {"x": -12.0, "y": 11.0, "z": -2.0},
          "max": {"x": -4.0, "y": 20.0, "z": 6.0}
        },
        "residues": [
          {"chain": "A", "resname": "ASP", "resid": 102},
          {"chain": "A", "resname": "ARG", "resid": 105}
        ]
      }
    ]
  },
  "output_files": [
    {
      "name": "1abc_pockets.mol2",
      "format": "mol2",
      "size": 15234,
      "url": "https://storage.example.com/output/task-123-456/1abc_pockets.mol2"
    }
  ]
}
```

---

### 3.5 批量预测

批量处理多个蛋白质文件。批量预测时，所有蛋白质将使用相同的结构分类模型。

**请求**:
```http
POST /batch
Content-Type: application/json

{
  "task_id": "batch-789",
  "params": {
    "threshold": 0.5,
    "min_size": 50,
    "output_formats": ["json"],
    "structure_class": "alpha"
  },
  "input_files": {
    "protein_files": [
      "https://storage.example.com/proteins/1abc.pdb",
      "https://storage.example.com/proteins/2xyz.pdb",
      "https://storage.example.com/proteins/3def.mol2"
    ]
  }
}
```

**响应**:
```json
{
  "success": true,
  "result": {
    "task_id": "batch-789",
    "total": 3,
    "completed": 3,
    "failed": 0,
    "processing_time": 8.72,
    "results": [
      {
        "file": "1abc.pdb",
        "success": true,
        "num_pockets": 3,
        "pockets": [ ... ]
      },
      {
        "file": "2xyz.pdb",
        "success": true,
        "num_pockets": 2,
        "pockets": [ ... ]
      },
      {
        "file": "3def.mol2",
        "success": true,
        "num_pockets": 1,
        "pockets": [ ... ]
      }
    ]
  },
  "output_files": [
    {
      "name": "batch-789_results.json",
      "format": "json",
      "url": "https://storage.example.com/output/batch-789/results.json"
    }
  ]
}
```

---

### 3.6 格式转换

将口袋预测结果转换为不同格式。

**请求**:
```http
POST /convert
Content-Type: application/json

{
  "task_id": "convert-001",
  "params": {
    "source_format": "json",
    "target_format": "mol2",
    "protein_file": "https://storage.example.com/proteins/1abc.pdb"
  },
  "input_files": {
    "prediction_file": "https://storage.example.com/output/task-123/result.json"
  }
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_format` | string | 是 | 源格式 (json) |
| `target_format` | string | 是 | 目标格式 (mol2/cmap/cube) |
| `protein_file` | url | 否 | 原始蛋白质文件（生成 MOL2 时需要） |
| `prediction_file` | url | 是 | 预测结果 JSON 文件 |

**响应**:
```json
{
  "success": true,
  "result": {
    "task_id": "convert-001",
    "source_format": "json",
    "target_format": "mol2",
    "conversion_time": 0.15
  },
  "output_files": [
    {
      "name": "1abc_pockets.mol2",
      "format": "mol2",
      "size": 15234,
      "url": "https://storage.example.com/output/convert-001/1abc_pockets.mol2"
    }
  ]
}
```

---

## 4. 错误码参考

### 4.1 客户端错误 (4xx)

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| 1001 | 400 | 无效的输入文件格式 |
| 1002 | 400 | 文件大小超出限制 |
| 1003 | 400 | 缺少必填参数 |
| 1004 | 400 | 参数值无效 |
| 1005 | 400 | 不支持的输出格式 |
| 1006 | 400 | 文件解析失败 |
| 1007 | 404 | 输入文件不存在 |

### 4.2 服务端错误 (5xx)

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| 2001 | 500 | 模型加载失败 |
| 2002 | 500 | 预测过程出错 |
| 2003 | 500 | 输出格式转换失败 |
| 2004 | 500 | 文件存储失败 |
| 3001 | 503 | 服务不可用 |
| 3002 | 503 | GPU 资源不足 |
| 3003 | 504 | 请求超时 |

### 4.3 错误响应示例

```json
{
  "success": false,
  "error": {
    "code": 1001,
    "message": "Invalid input file format",
    "details": {
      "received": "xyz",
      "supported": ["pdb", "mol2"],
      "suggestion": "Please provide a PDB or MOL2 format protein structure file"
    }
  }
}
```

---

## 5. 平台集成

### 5.1 工具配置示例

用于平台 `remote_api` 类型工具注册：

```json
{
  "type": "remote_api",
  "endpoint": "http://lvpocket-service:8000/predict",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "input_schema": {
    "type": "object",
    "required": ["protein_file"],
    "properties": {
      "protein_file": {
        "type": "string",
        "format": "file",
        "title": "蛋白质结构文件",
        "description": "PDB 或 MOL2 格式的蛋白质结构",
        "ui:accept": ".pdb,.mol2",
        "ui:maxSize": 52428800
      },
      "threshold": {
        "type": "number",
        "title": "预测阈值",
        "description": "口袋预测置信度阈值",
        "default": 0.5,
        "minimum": 0.1,
        "maximum": 0.9,
        "ui:step": 0.1
      },
      "min_size": {
        "type": "integer",
        "title": "最小口袋大小",
        "description": "过滤小于此体素数的口袋",
        "default": 50,
        "minimum": 10,
        "maximum": 500
      },
      "output_formats": {
        "type": "array",
        "title": "输出格式",
        "items": {
          "type": "string",
          "enum": ["json", "mol2", "cmap", "cube"]
        },
        "default": ["json", "mol2"],
        "ui:widget": "checkboxes"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "num_pockets": {
        "type": "integer",
        "description": "检测到的口袋数量"
      },
      "pockets": {
        "type": "array",
        "description": "口袋详细信息列表"
      },
      "output_file": {
        "type": "string",
        "format": "file",
        "description": "口袋结果文件"
      }
    }
  }
}
```

### 5.2 请求映射

平台发送的请求会被映射为：

```json
// 平台请求
{
  "task_id": "platform-task-xxx",
  "params": {
    "threshold": 0.5,
    "min_size": 50
  },
  "input_files": {
    "protein_file": "https://storage.platform.com/files/xxx.pdb"
  }
}

// 直接转发到 /predict 端点
```

---

## 6. 使用示例

### 6.1 cURL 示例

**健康检查**:
```bash
curl -X GET http://localhost:8000/health
```

**上传文件预测（使用默认模型）**:
```bash
curl -X POST http://localhost:8000/predict \
  -F "protein_file=@/path/to/protein.pdb" \
  -F 'params={"threshold": 0.5, "output_formats": ["json", "mol2"]}'
```

**上传文件预测（指定结构分类模型）**:
```bash
curl -X POST http://localhost:8000/predict \
  -F "protein_file=@/path/to/protein.pdb" \
  -F 'params={"threshold": 0.5, "structure_class": "alpha", "output_formats": ["json", "mol2"]}'
```

**URL 引用预测**:
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-001",
    "params": {"threshold": 0.5, "structure_class": "beta"},
    "input_files": {
      "protein_file": "https://files.rcsb.org/download/1ABC.pdb"
    }
  }'
```

### 6.2 Python 示例

```python
import requests

# 健康检查
response = requests.get("http://localhost:8000/health")
print(response.json())

# 上传文件预测（使用默认模型）
with open("protein.pdb", "rb") as f:
    response = requests.post(
        "http://localhost:8000/predict",
        files={"protein_file": f},
        data={"params": '{"threshold": 0.5}'}
    )
print(response.json())

# 上传文件预测（指定 α 类模型）
with open("alpha_protein.pdb", "rb") as f:
    response = requests.post(
        "http://localhost:8000/predict",
        files={"protein_file": f},
        data={"params": '{"threshold": 0.5, "structure_class": "alpha"}'}
    )
print(response.json())

# URL 引用预测（指定 β 类模型）
response = requests.post(
    "http://localhost:8000/predict",
    json={
        "task_id": "test-001",
        "params": {
            "threshold": 0.5,
            "structure_class": "beta"
        },
        "input_files": {
            "protein_file": "https://files.rcsb.org/download/1ABC.pdb"
        }
    }
)
print(response.json())

# 获取所有可用模型信息
response = requests.get("http://localhost:8000/model/info")
model_info = response.json()
print("可用模型:")
for model in model_info["result"]["available_models"]:
    status = "✓" if model["exists"] else "✗"
    print(f"  [{status}] {model['structure_class']}: {model['description']}")
```

---

## 附录 A：JSON Schema 定义

### A.1 PredictRequest Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "task_id": {
      "type": "string",
      "description": "任务唯一标识"
    },
    "params": {
      "type": "object",
      "properties": {
        "threshold": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "default": 0.5
        },
        "min_size": {
          "type": "integer",
          "minimum": 1,
          "default": 50
        },
        "output_formats": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": ["json", "mol2", "cmap", "cube"]
          },
          "default": ["json"]
        },
        "structure_class": {
          "type": "string",
          "enum": ["baseline", "alpha", "beta", "alpha_beta", "alpha_plus_beta"],
          "default": "baseline",
          "description": "蛋白质结构分类，用于选择对应的预训练模型"
        }
      }
    },
    "input_files": {
      "type": "object",
      "required": ["protein_file"],
      "properties": {
        "protein_file": {
          "type": "string",
          "format": "uri"
        }
      }
    }
  }
}
```

### A.2 PredictResponse Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": {
      "type": "boolean"
    },
    "result": {
      "type": "object",
      "properties": {
        "task_id": {"type": "string"},
        "protein_name": {"type": "string"},
        "num_atoms": {"type": "integer"},
        "num_pockets": {"type": "integer"},
        "processing_time": {"type": "number"},
        "structure_class": {
          "type": "string",
          "description": "使用的蛋白质结构分类模型"
        },
        "model_file": {
          "type": "string",
          "description": "使用的模型文件名"
        },
        "pockets": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "id": {"type": "integer"},
              "rank": {"type": "integer"},
              "score": {"type": "number"},
              "volume": {"type": "number"},
              "center": {
                "type": "object",
                "properties": {
                  "x": {"type": "number"},
                  "y": {"type": "number"},
                  "z": {"type": "number"}
                }
              }
            }
          }
        }
      }
    },
    "output_files": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "format": {"type": "string"},
          "size": {"type": "integer"},
          "url": {"type": "string", "format": "uri"}
        }
      }
    },
    "error": {
      "type": "object",
      "properties": {
        "code": {"type": "integer"},
        "message": {"type": "string"},
        "details": {"type": "object"}
      }
    }
  }
}
```
