## 背景和目标

- 

## 改动范围

- 

## 影响模块

- [ ] 后端 API
- [ ] Tool Contract / 工具注册
- [ ] Standard Artifact / 文件 / 结果持久化
- [ ] Run Preparation / BindingDecision
- [ ] Task / Executor / Worker
- [ ] Workflow / 节点 / 保存加载
- [ ] 前端工具中心 / 任务中心 / 工作台
- [ ] Renderer / 可视化
- [ ] 管理后台 / 治理 / 审计
- [ ] 部署 / CI / 配置
- [ ] 文档

## 测试结果

- [ ] `python -m pytest test/ -v`
- [ ] `python -m flake8 backend/app --select F401`
- [ ] `cd frontend && npm run test`
- [ ] `cd frontend && npm run build`
- [ ] `cd frontend && npm run test:e2e -- --project=chromium --reporter=list --workers=1`
- [ ] 手工验证：Fetch PDB -> Protein Preparation -> LVpocket
- [ ] 手工验证：PubChem -> Ligand Preparation -> RDKit Properties -> ADMET
- [ ] 未运行项已说明原因

## 风险和回滚

- 风险：
- 回滚方式：

## 文档

- [ ] 已更新相关文档
- [ ] 不需要更新文档，原因：

## Review 关注点

- 
