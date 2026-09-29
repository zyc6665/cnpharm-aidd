# 2026-09-22 资源调度收口记录

## 1. 收口结论

截至 2026-09-22，平台资源调度地基已经完成 V1 收口，主链路可以稳定表达任务资源需求、执行器能力、动态占用、配额拒绝和资源等待状态。

当前主链路为：

Tool Contract -> Run Preparation -> Standard Artifact / ArtifactVersion -> Task Command -> Task.resource_snapshot -> TaskQueueManager -> WorkerCapabilityRegistry -> ResourceAdmissionPolicy -> Dispatch Reservation -> ResourceQuotaManager -> WorkerResourceLeaseManager -> Executor Gateway -> Result Manifest -> ArtifactVersion / Lineage。

本轮收口的目标是冻结接口和职责边界，而不是继续扩展第二套调度体系。CPU、内存和并发资源已经由动态 lease 与 scope quota 统一管理；GPU 保持 GPUAllocator + GPUAllocation 为唯一实际分配所有者。

## 2. Worker Capability

WorkerCapabilityRegistry 负责登记和筛选可用 Worker，当前能力包括：

- queue、executor_types、tiers。
- CPU、内存、GPU 静态能力。
- parallelism 并发能力。
- healthy、heartbeat、TTL 和过期回收。
- 按队列契约、执行器类型、tier 和资源需求进行静态准入。
- 在满足准入条件的 Worker 中按当前负载排序。

Worker 能力只描述可提供的资源和执行器边界，不负责持有任务级动态占用。

## 3. Dynamic Resource Lease

WorkerResourceLeaseManager 负责任务级动态资源占用，当前模型为：

- reservation：调度成功后、任务真正运行前的短期预留。
- running：Worker 接受任务后的运行中租约。
- heartbeat：延长有效期，避免长任务被误回收。
- stale reservation reclaim：回收失联或过期的预留。
- attempt isolation：不同重试 attempt 的租约相互隔离。
- cancel、retry、delete：在任务状态迁移时释放对应租约。

lease 只负责动态 CPU、内存和并发计量，并保留 GPU 请求量用于观察；GPU 的实际分配和释放不迁移到 lease 内部。

### 3.1 取消与租约释放

- PENDING 任务的 reservation 可以由取消接口立即释放。
- RUNNING 任务只写回取消状态，不在取消接口中提前删除运行中 lease。
- RUNNING 任务被管理员删除时也不提前删除运行中 lease；删除数据库记录不等于 Worker 进程已经退出。
- Worker executor 退出时通过 finally 释放 lease；如果 Worker 进程异常退出，则由 TTL 和恢复机制最终回收。
- 这样可以避免取消请求先于实际进程退出时，把仍在消耗 CPU/内存/并发的任务误计为已释放。

## 4. Scope Quota

ResourceQuotaManager 负责用户和项目 scope 的硬配额校验，当前支持：

- CPU quota。
- memory quota。
- parallelism quota。
- scope 级锁，避免并发调度下的超配。
- quota rejection counters，记录拒绝原因和维度。
- 管理端 quota snapshot，展示已用、上限和拒绝统计。

配额校验发生在动态 lease 建立前。配额拒绝会写入结构化 resource wait 信息，避免只返回不可聚合的自由文本。

## 5. Resource Wait

ResourceWait 统一资源等待语义，当前分类包括：

- quota：用户或项目配额不足。
- worker_capacity：没有满足静态能力和当前负载条件的 Worker。
- gpu：GPUAllocator 暂时无法提供满足请求的 GPU。
- scheduler：调度器或队列暂时不可用。
- resource：其他资源不足或资源释放尚未完成。

任务详情、任务列表和管理员页面同时兼容旧 resource_wait_reason，并优先展示 resource_wait_code、category、scope 和 dimension 等结构化字段。

## 6. GPU 边界

GPU 实际调度仍由 GPUAllocator + GPUAllocation 作为单一 owner 管理。ResourceLease 只记录 GPU 请求量用于任务资源快照、等待原因和管理员观察，不复制一套 Redis 或 lease 层 GPU 硬配额。

这样可以避免数据库 GPU allocation、Redis lease 和 scope quota 三套计量口径不一致。GPU scope hard quota 暂不作为 V1 阻断项；只有在确认真实多租户 GPU 配额需求后，再设计统一 owner 的配额扩展。

## 7. 管理端可观测性

当前管理端已提供以下观察面：

- Worker 资源能力、健康状态、队列和当前负载。
- 用户或项目 scope quota 使用量、上限和拒绝计数。
- pending 任务的资源等待统计。
- 按 resource_wait_category 筛选任务。
- 任务详情和任务卡片中的资源等待原因。

这些入口覆盖调度拒绝、等待堆积和 Worker 能力不匹配三类主要排障路径。

## 8. 已验证证据

本轮已完成以下验证：

- 资源调度相关回归：145 passed。
- 资源等待、管理员接口、任务详情回归：26 passed。
- 项目任务 ACL 回归：7 passed。
- TaskListCard 组件测试：5 passed。
- 纯后端 Worker 队列交接与长任务生命周期回归：覆盖 reservation、running lease、claimed 标记、heartbeat、PENDING 立即释放、RUNNING 取消/删除延迟释放和幂等清理。
- Worker 队列并发准入回归：1 passed，覆盖同一 Worker 不超配、锁竞争、释放和重试复用。
- npx vue-tsc --noEmit --pretty false：通过。
- npm run build：通过，耗时约 33 秒；仅保留既有第三方 eval 和 chunk 体积警告。
- python -m compileall -q backend/app test：通过。
- git diff --check：通过。

全量 pytest 尚未形成干净、可复用的完成记录，原因是环境中存在本轮之前遗留的测试进程。本记录不把未完成的全量回归误报为通过。

## 9. 发布前动作

在正式发布或演示前，仍需完成：

1. 在无历史残留测试进程的干净环境执行一次全量后端回归。
2. 以纯后端调度和 Worker 队列完成当前可执行验收：能力注册、队列准入、资源预留、running lease、heartbeat、stale reclaim、PENDING 取消释放、RUNNING 取消延迟释放、重试释放、优先级 aging、quota 拒绝和 resource wait 归因。
3. 用真实 GPU 多租户场景评估是否需要统一 GPU lease owner 和 scope quota。
4. 保持 ResourceLease、ResourceQuota、ResourceWait、WorkerCapability 的接口文档与实现同步。
5. 若调度语义继续变化，先更新本记录、平台功能地基设计和 V1 验收索引，再修改前后端实现。

## 10. 非阻断限制

以下事项当前不阻断 V1 资源调度地基收口：

- GPU scope hard quota 尚未复制到 ResourceLease 层。
- K8s / Slurm 当前只有 Executor Adapter 设计，没有可用的真实或等价集群环境；生产验证延后，不阻断当前 V1 后端调度地基。
- 历史测试进程导致全量回归尚未形成干净证据。
- 自动扩缩容、容量趋势和更复杂的调度策略属于后续运营增强。
