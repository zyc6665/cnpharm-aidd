# 设计 Token 速查表（阶段 1）

> 单一真源：`frontend/src/assets/styles/variables.less`（LESS 变量）+ `frontend/src/assets/styles/global.less`（`--theme-*` CSS 自定义属性）。
> 暗色为默认；`[data-theme="light"]` 在 `global.less` 逐项覆盖。视图层只引用下表 token，不再写裸十六进制色值。
> 图表色同时镜像到 `frontend/src/utils/chartTheme.ts`，改色时两处同步。

## 表面 Surface

| Token | 用途 | 暗色 | 浅色 |
| --- | --- | --- | --- |
| `@surface-base` / `--theme-surface-base` | 页面底色 | `#09090b` | `#f8fafc` |
| `@surface-elevated` / `--theme-surface-elevated` | 卡片 / 浮层 | `#1a1a21` | `#ffffff` |
| `@surface-sunken` / `--theme-surface-sunken` | 表格斑马纹 / 输入底 | `#0d0d11` | `#f1f5f9` |

> 兼容别名：`@bg-body`=`@surface-base`，`@bg-surface`（#131318 侧栏色）、`@bg-elevated`=`@surface-elevated`。

## 文本 Text

| Token | 用途 | 暗色 | 浅色 |
| --- | --- | --- | --- |
| `@text-primary` / `--theme-text-primary` | 主文本 / 标题 | `#f1f5f9` | `#0f172a` |
| `@text-secondary` / `--theme-text-secondary` | 次级文本 / 标签 | `#94a3b8` | `#475569` |
| `@text-tertiary` / `--theme-text-tertiary` | 辅助 / 占位说明 | `#64748b` | `#94a3b8` |
| `@text-disabled` / `--theme-text-disabled` | 禁用态 | `#475569` | `#cbd5e1` |
| `@text-inverse` / `--theme-text-inverse` | 反色文本（浅底上用） | `#0b1120` | `#ffffff` |

## 边框 Border

| Token | 用途 | 暗色 | 浅色 |
| --- | --- | --- | --- |
| `@border-base` / `--theme-border` | 默认边框 / 分隔线 | `rgba(255,255,255,.06)` | `#e2e8f0` |
| `@border-strong` / `--theme-border-strong` | 强调边框 / hover | `rgba(255,255,255,.14)` | `#cbd5e1` |
| `@border-subtle` / `--theme-border-subtle` | 极弱分隔（卡片头底边） | `rgba(255,255,255,.03)` | `#eef2f7` |

> 兼容别名：`@border-color`=`@border-base`，`@border-color-hover`、`@border-color-strong`。

## 状态弱底 Status Background

| Token | 用途 | 暗色 | 浅色 |
| --- | --- | --- | --- |
| `@success-bg` / `--theme-success-bg` | 成功弱底 | `rgba(34,197,94,.12)` | `rgba(34,197,94,.10)` |
| `@warning-bg` / `--theme-warning-bg` | 警告弱底 | `rgba(245,158,11,.12)` | `rgba(245,158,11,.12)` |
| `@error-bg` / `--theme-error-bg` | 错误弱底 | `rgba(239,68,68,.12)` | `rgba(239,68,68,.10)` |
| `@info-bg` / `--theme-info-bg` | 信息弱底 | `rgba(59,130,246,.12)` | `rgba(59,130,246,.10)` |

> 前景色沿用 `@success-color #22c55e` / `@warning-color #f59e0b` / `@error-color #ef4444` / `@info-color #3B82F6`。
> 对应工具类：`.status-bg-success` / `.status-bg-warning` / `.status-bg-error` / `.status-bg-info`。

## 图表色 Chart（暗 / 浅共用）

| Token | 用途 | 值 |
| --- | --- | --- |
| `@chart-1` / `chartPalette[0]` | 主蓝（主折线 / 主柱） | `#5b8ff9` |
| `@chart-2` / `chartPalette[1]` | 青绿 | `#61ddaa` |
| `@chart-3` / `chartPalette[2]` | 金 / 提示 | `#f6bd16` |
| `@chart-4` / `chartPalette[3]` | 橙 | `#ff9845` |
| `@chart-5` / `chartPalette[4]` | 紫 | `#7262fd` |
| `@chart-6` / `chartPalette[5]` | 浅紫 / 次要序列 | `#9270ca` |
| `@chart-7` / `chartPalette[6]` | 绿（正向 / 达标） | `#52c41a` |
| `@chart-8` / `chartPalette[7]` | 红（负向 / 告警） | `#f5222d` |

> TS 侧：`import { chartPalette, chartColors, chartColorAt } from '@/utils/chartTheme'`。
> `chartColors` 提供语义别名：`primary / positive / negative / warning / purple / primaryArea / positiveArea`。

## 其他固定 Token

| Token | 用途 | 值（暗 / 浅一致） |
| --- | --- | --- |
| `@terminal-bg` / `--theme-terminal-bg` | 终端日志块底 | `#1e1e1e` |
| `@terminal-fg` / `--theme-terminal-fg` | 终端日志块文本 | `#f8f8f2` |

> 工具类 `.terminal-block` 封装终端日志块（背景、等宽字体、圆角、内边距）。

## 密度 / 间距（既有，未改动）

| Token | 值 |
| --- | --- |
| `@spacing-xs / sm / md / lg / xl / xxl` | 4 / 8 / 16 / 24 / 32 / 48 px |
| `@border-radius-sm / md / lg` | 4 / 8 / 12 px |
| `@font-size-xs / sm / md` | 12 / 14 / 16 px（表格行 13px） |
| `@font-weight-medium / semibold` | 500 / 600 |

组件密度统一覆写在 `antd-override.less`：卡片（圆角 8、内边距 24、标题 16/600）、表格（13px、`tabular-nums`）、表单（标签 13px）。
数字列右对齐：给列定义 `align: 'right'`，或给单元格加 `.num-cell`。
