# 工具创建和测试指南

本指南帮助你在SciTool平台上快速创建和测试新工具。

---

## 📋 准备工作

### 1. 需要的信息

在创建工具前，请准备以下信息：

- **API URL**: 工具的API端点（例如：`https://api.example.com/predict`）
- **HTTP方法**: GET或POST
- **输入Schema**: API接受的参数结构（JSON Schema格式）
- **输出Schema**: API返回的数据结构（JSON Schema格式）
- **认证信息**: 如果API需要认证，准备好headers

### 2. 文件清单

- `create_tool.py` - 工具创建脚本
- `tool_config_template.json` - 工具配置模板
- `test_params_template.json` - 测试参数模板

---

## 🚀 快速开始

### 步骤1: 创建工具配置文件

复制模板并根据你的API修改：

```bash
cp tool_config_template.json my_tool.json
```

编辑`my_tool.json`，填入你的工具信息：

```json
{
  "name": "我的API工具",
  "slug": "my-api-tool",
  "description": "工具功能描述",
  "icon": "🔬",
  "category": "ai-model",
  "version": "1.0.0",
  "changelog": "首次发布",
  "tool_config": {
    "type": "remote_api",
    "endpoint": "你的API URL",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer YOUR_TOKEN"  // 如果需要
    },
    "timeout_sec": 300,
    "input_schema": {
      "type": "object",
      "properties": {
        "input": {
          "type": "string",
          "description": "输入参数说明"
        }
      },
      "required": ["input"]
    },
    "output_schema": {
      "type": "object",
      "properties": {
        "output": {
          "type": "string",
          "description": "输出说明"
        }
      }
    }
  }
}
```

### 步骤2: 创建测试参数

复制测试参数模板：

```bash
cp test_params_template.json my_test_params.json
```

编辑`my_test_params.json`，填入测试数据：

```json
{
  "input": "测试输入内容"
}
```

### 步骤3: 创建工具

运行创建脚本：

```bash
python create_tool.py --config my_tool.json
```

成功后会显示：
```
✅ 工具创建成功: 我的API工具 (ID: xxx-xxx-xxx)
✅ 工具版本创建成功: 1.0.0 (ID: yyy-yyy-yyy)

工具信息:
  名称: 我的API工具
  Slug: my-api-tool
  ID: xxx-xxx-xxx
  版本ID: yyy-yyy-yyy
  类型: remote_api
```

### 步骤4: 测试工具

创建并测试：

```bash
python create_tool.py \
  --config my_tool.json \
  --test \
  --test-params my_test_params.json
```

---

## 📝 配置说明

### tool_config字段详解

#### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | 工具类型：`remote_api`、`docker_image`、`python_script` |
| timeout_sec | number | 超时时间（秒） |
| input_schema | object | 输入参数的JSON Schema |
| output_schema | object | 输出结果的JSON Schema |

#### remote_api类型特有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| endpoint | string | API端点URL |
| method | string | HTTP方法：GET或POST |
| headers | object | HTTP请求头 |

#### docker_image类型特有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| image | string | Docker镜像名 |
| command | array | 容器启动命令 |
| gpu_required | boolean | 是否需要GPU |
| memory_limit | string | 内存限制（如"4g"） |
| cpu_limit | number | CPU核心数限制 |

#### python_script类型特有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| script_path | string | 脚本文件路径 |
| script_content | string | 脚本内容（二选一） |

---

## 🧪 测试示例

### 示例1: 简单的文本处理API

**配置文件** (`text_processor.json`):
```json
{
  "name": "文本处理工具",
  "slug": "text-processor",
  "description": "处理和分析文本",
  "icon": "📝",
  "category": "nlp",
  "version": "1.0.0",
  "tool_config": {
    "type": "remote_api",
    "endpoint": "https://api.textanalyzer.com/process",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json"
    },
    "timeout_sec": 60,
    "input_schema": {
      "type": "object",
      "properties": {
        "text": {
          "type": "string",
          "description": "要处理的文本"
        },
        "language": {
          "type": "string",
          "enum": ["en", "zh"],
          "default": "zh",
          "description": "语言"
        }
      },
      "required": ["text"]
    },
    "output_schema": {
      "type": "object",
      "properties": {
        "processed_text": {
          "type": "string"
        },
        "word_count": {
          "type": "number"
        },
        "sentiment": {
          "type": "string",
          "enum": ["positive", "negative", "neutral"]
        }
      }
    }
  }
}
```

**测试参数** (`text_processor_test.json`):
```json
{
  "text": "这是一段测试文本，用于验证文本处理功能。",
  "language": "zh"
}
```

### 示例2: 图像分类API

**配置文件** (`image_classifier.json`):
```json
{
  "name": "图像分类工具",
  "slug": "image-classifier",
  "description": "使用AI模型对图像进行分类",
  "icon": "🖼️",
  "category": "computer-vision",
  "version": "1.0.0",
  "tool_config": {
    "type": "remote_api",
    "endpoint": "https://api.vision.com/classify",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "API-Key": "your-api-key"
    },
    "timeout_sec": 120,
    "input_schema": {
      "type": "object",
      "properties": {
        "image_url": {
          "type": "string",
          "format": "uri",
          "description": "图像URL"
        },
        "top_k": {
          "type": "number",
          "default": 5,
          "description": "返回前K个分类"
        }
      },
      "required": ["image_url"]
    },
    "output_schema": {
      "type": "object",
      "properties": {
        "predictions": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "label": {"type": "string"},
              "confidence": {"type": "number"}
            }
          }
        }
      }
    }
  }
}
```

---

## 🔧 高级用法

### 使用环境变量

在配置中可以使用环境变量：

```json
{
  "tool_config": {
    "endpoint": "${API_ENDPOINT}",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}"
    }
  }
}
```

### 文件上传支持

如果API支持文件上传，在input_schema中定义：

```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "file": {
        "type": "string",
        "format": "binary",
        "description": "上传的文件"
      }
    }
  }
}
```

### 自定义错误处理

在tool_config中添加error_handling配置：

```json
{
  "tool_config": {
    "error_handling": {
      "retry_count": 3,
      "retry_delay": 5,
      "timeout_action": "fail"
    }
  }
}
```

---

## ❓ 常见问题

### Q: 如何查看创建的工具？

A: 使用数据库查询：
```bash
sqlite3 backend/storage/scitool.db \
  "SELECT id, name, slug, status FROM tools;"
```

### Q: 如何修改工具配置？

A: 创建新版本或更新现有版本的config字段

### Q: 测试失败怎么办？

A: 检查：
1. API URL是否正确
2. 网络是否可达
3. 参数格式是否匹配input_schema
4. 查看详细错误信息

### Q: 如何删除测试工具？

A: 使用SQL删除：
```bash
sqlite3 backend/storage/scitool.db \
  "DELETE FROM tools WHERE slug='my-test-tool';"
```

---

## 📚 参考资源

- [JSON Schema规范](https://json-schema.org/)
- [HTTP方法说明](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Methods)
- [SciTool API文档](docs/design/03-接口规格说明书.md)

---

**准备好了吗？** 请提供你的API信息，我们开始创建工具！
