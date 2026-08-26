# Remote API 自注册协议

## 1. 目标

Remote API 自注册协议用于让远端模型服务按平台标准暴露 manifest。平台管理员只需要提供 base URL，平台即可拉取工具契约、样例、端点能力并完成注册、冒烟测试和工作流兼容。

该协议适合模型团队自行部署服务，平台负责统一注册、任务提交、状态查询、日志、取消、结果收集和 Artifact 持久化。

## 2. 设计原则

1. 远端服务适配平台，不让平台为每个远端服务写适配器。
2. 第一版不需要认证，默认远端服务部署在受控内网。
3. 必须异步执行。
4. 必须支持查询、日志和取消。
5. 输入输出必须使用标准 Artifact 契约。
6. 结果必须返回 result.v2 或可转换为标准 Artifact 输出。

## 3. 服务端点

远端服务应提供：

| Endpoint | 方法 | 说明 |
| --- | --- | --- |
| `/manifest` | GET | 返回工具 manifest |
| `/examples` | GET | 返回样例参数和样例 Artifact |
| `/invoke` | POST | 提交异步任务 |
| `/status/{remote_task_id}` | GET | 查询任务状态 |
| `/logs/{remote_task_id}` | GET | 查询日志 |
| `/cancel/{remote_task_id}` | POST | 取消任务 |
| `/artifacts/{remote_task_id}` | GET | 查询结果 manifest 和文件 URL |
| `/health` | GET | 健康检查 |

manifest 中允许端点自定义路径，但必须是同服务相对路径。

## 4. Manifest 结构

```json
{
  "api_version": "aidd.sciminer/remote-tool.v1",
  "kind": "RemoteTool",
  "metadata": {
    "slug": "my-pocket-model",
    "name": "My Pocket Model",
    "version": "1.0.0",
    "description": "Predict binding pockets from protein structures."
  },
  "artifacts": {
    "inputs": [
      {
        "name": "protein",
        "type": "protein_structure@1",
        "required": true,
        "role_preferences": ["prepared_pdb", "structure_file"],
        "required_roles": [],
        "readiness_policy": "prefer_prepared_warn_raw",
        "suggested_preparation_tool": "builtin-protein-preparation"
      }
    ],
    "outputs": [
      {
        "name": "pocket",
        "type": "binding_pocket@1",
        "cardinality": "one",
        "required": true,
        "provided_roles": ["residue_pocket_pdb", "atom_pocket_pdb", "pocket_metadata_json"]
      }
    ]
  },
  "parameters_schema": {
    "type": "object",
    "properties": {
      "threshold": { "type": "number", "default": 0.5 }
    }
  },
  "endpoints": {
    "invoke": "/invoke",
    "status": "/status/{remote_task_id}",
    "logs": "/logs/{remote_task_id}",
    "cancel": "/cancel/{remote_task_id}",
    "artifacts": "/artifacts/{remote_task_id}",
    "examples": "/examples",
    "health": "/health"
  },
  "capabilities": {
    "async": true,
    "logs": true,
    "cancel": true,
    "progress": true
  },
  "examples": []
}
```

## 5. Invoke 请求

平台向远端发送标准请求。推荐结构：

```json
{
  "request_version": "aidd.sciminer/request.v1",
  "task": {
    "id": "platform-task-id",
    "tool_slug": "my-pocket-model",
    "tool_version": "1.0.0"
  },
  "inputs": {
    "protein": {
      "source": "artifact_version",
      "artifact_version_id": "artifact-version-id",
      "type": "protein_structure@1",
      "files": {
        "structure_file": {
          "url": "https://platform/files/input.pdb",
          "sha256": "...",
          "content_type": "chemical/x-pdb"
        }
      },
      "metadata": {}
    }
  },
  "parameters": {
    "threshold": 0.5
  },
  "callback": null
}
```

第一版可不做 callback，平台使用异步轮询。

## 6. Invoke 响应

```json
{
  "remote_task_id": "remote-123",
  "status": "queued",
  "message": "Task accepted"
}
```

规则：

- `remote_task_id` 必须稳定。
- 不应同步返回完整结果。
- 远端服务应尽快返回。

## 7. Status 响应

```json
{
  "remote_task_id": "remote-123",
  "status": "running",
  "progress": 42,
  "message": "Predicting pockets",
  "started_at": "2026-08-22T00:00:00Z",
  "finished_at": null,
  "error": null
}
```

状态枚举：

- `queued`
- `running`
- `success`
- `failure`
- `cancelled`

## 8. Logs 响应

```json
{
  "remote_task_id": "remote-123",
  "logs": [
    {
      "timestamp": "2026-08-22T00:00:01Z",
      "level": "info",
      "message": "Model loaded"
    }
  ]
}
```

## 9. Cancel 响应

```json
{
  "remote_task_id": "remote-123",
  "status": "cancelled",
  "message": "Task cancelled"
}
```

规则：

- cancel 必须幂等。
- 已完成任务 cancel 返回当前终态即可。

## 10. Artifacts 响应

远端任务成功后返回标准结果：

```json
{
  "result_version": "aidd.sciminer/result.v2",
  "artifacts": {
    "pocket": {
      "type": "binding_pocket@1",
      "name": "Predicted pocket",
      "files": {
        "residue_pocket_pdb": {
          "url": "https://remote/files/residue_pocket.pdb",
          "sha256": "...",
          "content_type": "chemical/x-pdb"
        },
        "atom_pocket_pdb": {
          "url": "https://remote/files/atom_pocket.pdb",
          "sha256": "...",
          "content_type": "chemical/x-pdb"
        },
        "pocket_metadata_json": {
          "url": "https://remote/files/metadata.json",
          "sha256": "...",
          "content_type": "application/json"
        }
      },
      "metadata": {
        "center": [0, 0, 0],
        "bbox": [10, 10, 10],
        "residue_ids": [],
        "atom_ids": [],
        "source_protein_ref": "protein"
      },
      "summary": {},
      "metrics": {}
    }
  },
  "relations": [],
  "summary": {},
  "metrics": {}
}
```

平台职责：

- 下载远端文件。
- 校验 sha256。
- 保存到平台对象存储。
- 按 manifest `artifacts.outputs` 持久化 Standard Artifact。
- 记录 TaskOutput 和谱系。

## 11. Examples 响应

```json
{
  "examples": [
    {
      "name": "smoke",
      "description": "Small protein smoke test",
      "smoke": true,
      "parameters": { "threshold": 0.5 },
      "input_artifacts": {
        "protein": {
          "type": "protein_structure@1",
          "files": {
            "structure_file": {
              "filename": "example.pdb",
              "url": "https://remote/examples/example.pdb",
              "sha256": "...",
              "content_type": "chemical/x-pdb"
            }
          },
          "metadata": {}
        }
      }
    }
  ]
}
```

## 12. 注册流程

```text
管理员输入 base_url
  │
  ▼
平台 GET /manifest
  │
  ▼
校验 manifest
  │
  ▼
拉取 examples
  │
  ▼
生成 Tool + ToolVersion + ToolContract
  │
  ▼
执行 smoke test
  │
  ▼
发布到工具库和工作流节点库
```

## 13. 冒烟测试

冒烟测试必须验证：

- manifest 可拉取。
- health 正常。
- example 可解析。
- invoke 能返回 remote_task_id。
- status 能到达 success/failure 终态。
- logs 可查询。
- artifacts 返回结果满足输出契约。
- 文件 URL 可下载且 sha256 匹配。

## 14. 错误处理

| 错误 | 平台处理 |
| --- | --- |
| manifest 无法访问 | 注册失败 |
| manifest schema 不合法 | 注册失败并展示字段错误 |
| Artifact type 未注册 | 注册失败 |
| health 失败 | 允许保存草稿，不允许发布 |
| smoke test 失败 | 标记未通过，管理员可查看日志 |
| status 超时 | 平台任务失败或继续轮询，取决于 timeout |
| artifacts sha256 不匹配 | 任务失败，不保存 Artifact |

## 15. 安全边界

第一版不做认证，但仍要求：

- 服务部署在平台可控网络。
- 只有管理员或具备工具发布权限的用户可以注册 Remote API URL。
- 注册 URL 必须通过协议白名单和 host allowlist 校验。
- 禁止访问 loopback、link-local、metadata service、私有保留地址以外的未授权网段。
- 禁止跟随跨 host 重定向，避免 DNS rebinding 和 SSRF。
- manifest、examples、result manifest 和结果文件下载必须有大小限制和超时限制。
- manifest 不包含明文密钥。
- endpoints 必须是相对路径。
- 文件 URL 必须可由平台 worker 访问。
- 平台不信任远端结果，必须校验 schema 和 checksum。
- 结果文件入库前必须重新计算 sha256，并与远端 manifest 对比。
- 远端服务只能提供数据文件，不能要求平台执行远端返回的命令。

后续版本可增加：

- HMAC 签名。
- mTLS。
- Token 认证。
- IP allowlist。
- 结果回调签名。

## 16. 与工作流兼容

Remote API 工具注册后必须被转换成 Tool Contract。只要：

- `artifacts.inputs` 完整。
- `artifacts.outputs` 完整。
- `capabilities.async = true`。
- `capabilities.cancel = true`。
- `validation.status = valid`。

它就应自动进入工作流节点库，并通过标准 Artifact 类型参与连线匹配。

## 17. 禁止事项

- 禁止平台为每个 Remote API 写私有 adapter。
- 禁止远端服务只返回非结构化 zip 而没有 result.v2。
- 禁止结果文件无 sha256。
- 禁止 manifest endpoints 使用跨域绝对 URL。
- 禁止远端服务假装同步执行长任务。
