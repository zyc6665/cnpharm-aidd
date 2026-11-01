# 硬编码色值白名单（阶段 1）

目标：`grep -rnE '#[0-9a-fA-F]{6}' frontend/src/views` 只剩注释或本文件说明的场景。
当前实测：**0 处**（阶段 1 收口后）。

若确因第三方组件内联限制必须写十六进制色，请在此登记，并在代码处加注释说明原因。格式：

| 文件:行 | 色值 | 原因 | 替代方案 |
| --- | --- | --- | --- |
| （暂无） | | | |

## 已消除的场景与替代

| 文件 | 原写法 | 现写法 |
| --- | --- | --- |
| `frontend/src/views/demo/Achievements.vue` | ECharts itemStyle / lineStyle / color 数组写死色 | `chartColors.*` / `chartPalette[*]`（`@/utils/chartTheme`） |
| `frontend/src/views/demo/Achievements.vue` | `.selected-row{background:#e6f4ff}` / `.peptide-seq{color:#1677ff}` | `var(--theme-accent-light)` / `var(--theme-accent)` |
| `frontend/src/views/md/FreeEnergyResult.vue` | `#5b8ff9` / `#9270ca` | `chartColors.primary` / `chartColors.purple` |
| `frontend/src/views/predict/HistogramChart.vue` | `#5b8ff9` | `chartColors.primary` |
| `frontend/src/views/screening/FunnelChart.vue` | 4 色数组 | `[...chartPalette]` |
| `frontend/src/views/design/GenerationResults.vue` | `#f0f0f0` `#fff` `#595959` `#fafafa` `#bfbfbf` `#fcfcfc` `#8c8c8c` `#262626` | `@border-color` `@bg-surface` `@text-secondary` `@surface-sunken` `@text-tertiary` `@text-primary` |
| `frontend/src/views/design/MoleculeGeneration.vue` / `PeptideDesign.vue` | `#f0f0f0` `#fff` | `@border-color` `@bg-surface` |
| `frontend/src/views/design/components/PocketPicker.vue` | `#d46b08` | `@warning-color` |
| `frontend/src/views/predict/PropertyPredictResult.vue` / `PropertyPredictSubmit.vue` / `screening/ScreenConfig.vue` | `var(--ant-color-text-secondary,#8c8c8c)` 等 fallback | `var(--ant-color-text-secondary, var(--theme-text-secondary))` |
| `frontend/src/views/tasks/Detail.vue` | `a-progress` 渐变 `#108ee9/#87d068`；`pre` 的 `#1e1e1e/#f8f8f2` | 渐变改用 `theme.useToken()` 的 `colorPrimary/colorSuccess`；`pre` 改用 `@terminal-bg/@terminal-fg` |
