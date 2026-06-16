# 首页接入 PAIWSIT 设计

## 目标

在前端首页增加 `PAIWSIT` 内容入口，并调整首页中部“平台/数据底座”区块的顺序与信息架构，使其按 `PAIWSIT -> CPUPDB -> CPUModel` 的顺序传达“靶点发现 -> 结构口袋依据 -> 计算工作台执行”的研究路径。

## 现状

当前首页 `foundation-section` 只有两张卡：

- `CPUModel`
- `CPUPDB`

该区块更偏向“平台与数据底座”说明，而 `PAIWSIT` 的公开定位是病理学家标注、AI 赋能、面向肿瘤的全切片图像数据库，更适合作为首页中段的研究入口资源，而不是放入上方的 AIDD workflow 步骤中。

## 推荐方案

保留现有 `foundation-section`，把两卡结构扩展为三卡结构，并调整顺序：

1. `PAIWSIT`
2. `CPUPDB`
3. `CPUModel`

同时把区块标题和副标题从“平台模型与数据底座”调整为能够覆盖三者的新表达，例如“靶点发现与平台底座”。

## 信息设计

### PAIWSIT

- 角色：靶点发现入口
- 外链：`http://www.paiwsit.com/`
- 核心表达：病理学家标注、AI 赋能、肿瘤全切片图像数据库
- 研究语义：从组织病理表型切入，为靶点发现和机制研究提供入口

### CPUPDB

- 角色：结构与口袋数据底座
- 外链：保留现有 `https://www.cpupdb.com`
- 核心表达：结构、口袋、多构象、动力学分析
- 研究语义：把病理与生物学线索下钻到结构层

### CPUModel

- 角色：AIDD 计算工作台
- 站内链接：保留现有 `/workflow`
- 核心表达：工具分组、产物复用、任务串联
- 研究语义：把前两者沉淀的数据与线索接入实际计算流程

## 布局设计

采用 `1 + 2` 的三卡布局：

- 第一张 `PAIWSIT` 作为强调卡，视觉权重更高
- 第二、三张 `CPUPDB` 与 `CPUModel` 使用同一套较轻量卡片结构
- 移动端降为单列，顺序保持不变

这样可以在不破坏现有首页风格的情况下，明确建立阅读顺序和优先级。

## 视觉与交互

- 继续复用当前 `foundation` 区块的深色、描边、渐显动画语言
- 为 `PAIWSIT` 单独增加强调色调，建议偏病理切片相关的暖色系
- 三张卡都保留明确的 CTA 按钮，不做纯说明卡

## 文案范围

需要同步更新中英文文案：

- `home.foundation.title`
- `home.foundation.subtitle`
- `home.foundation.paiwsit.*`
- `home.foundation.cpupdb.*`
- `home.foundation.platform.*`

其中原来的 `platform` 和 `cpupdb` 内容需要根据新顺序重新编排，但现有站内/站外跳转保持不变。

## 测试

扩展首页现有表面测试，验证：

- 首页 `foundation-section` 中存在 `PAIWSIT`
- 三卡顺序为 `PAIWSIT -> CPUPDB -> CPUModel`
- 新外链 `http://www.paiwsit.com/` 存在
- 旧的双卡断言更新为三卡结构断言

## 原则

- KISS：只改首页现有 `foundation-section`，不新起整段页面
- YAGNI：不引入新数据接口，不抓取远程站点内容
- DRY：复用现有卡片与 reveal 动画结构
- SOLID：文案放在 i18n，布局逻辑留在首页组件，测试独立覆盖页面表面结构
