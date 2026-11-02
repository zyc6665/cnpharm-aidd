<template>
  <div class="app-description-list" :data-testid="testId">
    <section v-for="section in sections" :key="section.key" class="app-description-section">
      <h3 v-if="section.title" class="app-description-title">{{ section.title }}</h3>
      <a-descriptions bordered :column="columns" size="small">
        <a-descriptions-item
          v-for="field in section.fields"
          :key="field.key"
          :label="field.label"
          :span="field.span"
        >
          <a-tag v-if="field.tagColor" :color="field.tagColor">{{ field.value }}</a-tag>
          <span v-else-if="field.mono" class="app-description-mono">{{ field.value }}</span>
          <template v-else>{{ field.value }}</template>
          <span v-if="field.hint" class="app-description-hint">{{ field.hint }}</span>
        </a-descriptions-item>
      </a-descriptions>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 由「分节 + 字段」数据驱动的描述表。
 *
 * 详情页各写 `<a-descriptions>` + 各自的空值/单位/枚举处理，是当前重复度最高
 * 的一块。这里只负责布局与空值兜底，字段值仍由页面（或 domain 层格式化函数）
 * 算好再传进来 —— 组件不猜业务含义。
 */
export interface DescriptionField {
  key: string
  label: string
  value: string
  /** 等宽字体（哈希、序列、SMILES、ID） */
  mono?: boolean
  /**
   * 一行灰色提示，用来表达「这个数字怎么算好」——
   * 例如 pLDDT「越高越好」、对接分「越低越好」。指标方向属于领域知识，
   * 由页面算好后传入，组件不猜。
   */
  hint?: string
  /** 有值时以 a-tag 渲染（状态枚举），颜色由页面给 */
  tagColor?: string
  span?: number
}

export interface DescriptionSection {
  key: string
  title?: string
  fields: DescriptionField[]
}

withDefaults(
  defineProps<{
    sections: DescriptionSection[]
    columns?: number
    testId?: string
  }>(),
  { columns: 2 },
)
</script>

<style scoped>
.app-description-section + .app-description-section {
  margin-top: 16px;
}

.app-description-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.app-description-hint {
  margin-left: 6px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.app-description-mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
