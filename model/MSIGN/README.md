# MSIGN Model Runtime Package

这个包是 MSIGN 的模型侧平台化 runtime。平台只下发标准 request 和收取 `result.v2`；
本包负责把标准蛋白/配体输入适配到旧 MSIGN 入口，并把旧预测结果收敛为 `molecule_table@1`。

真实部署时通过 `MSIGN_LEGACY_ENTRYPOINT` 指向原始模型入口。该路径属于部署环境配置，
不要写入平台契约或提交到仓库。
