# Janus-QUBO 平台上传示例

本目录给平台接入和联调用的最小上传样例。

## 文件说明

- `params_ga_default.json`：默认 GA 生成示例，不需要上传任何输入文件。
- `params_ga_with_qubo_upload.json`：GA 生成并上传自定义 QUBO CSV 的示例。
- `params_kaiwu_optional.json`：Kaiwu 可选分支示例，需要用户填写真实 `user_id` 和 `sdk_code`。
- `input/qubo_128.csv`：GA 可选上传文件，128 x 128 QUBO 矩阵，可直接用于 128-bit Block_bAE 解码。
- `input/ising_129.csv`：Kaiwu 可选上传文件示例，129 x 129 Ising 矩阵；前 128 位对应 latent，最后 1 位是辅助 spin。

## 上传规则

默认 GA 模式不需要上传文件，平台会使用仓库内置：

- `Qmol_FM/example_data/qubo_128.csv`
- `recon_loss=0.0043.ckpt`

如果需要自定义 QUBO，只上传：

- `input/qubo_128.csv`

如果需要 Kaiwu，只上传：

- `input/ising_129.csv`

并在参数里填写：

- `method`: `kaiwu`
- `user_id`: Kaiwu 用户 ID
- `sdk_code`: Kaiwu SDK 授权码

当前环境已安装 `kaiwu-community==1.0.4`，但原始代码 `Qmol_FM/sample.py` 需要 `kaiwu.classical` API。真实 Kaiwu 求解需在运行环境安装匹配该 API 的 Kaiwu SDK。

