<template>
  <div class="task-parameter-table" data-testid="task-parameter-table">
    <template v-if="groups.length">
      <section
        v-for="group in groups"
        :key="group.id"
        class="parameter-group"
        :data-testid="`task-parameter-group-${group.id}`"
      >
        <h4 class="parameter-group-title">{{ t(group.titleKey) }}</h4>
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item v-for="field in group.fields" :key="field.key">
            <template #label>
              <span class="parameter-label">
                {{ field.label }}
                <span v-if="field.required" class="parameter-required">*</span>
                <span v-if="field.range" class="parameter-range">{{ field.range }}</span>
              </span>
            </template>
            <div class="parameter-value" :class="{ 'is-default': field.fromDefault }">
              <span :data-testid="`task-parameter-value-${field.key}`">{{ field.display }}</span>
              <span v-if="field.options?.length" class="parameter-options">
                {{ t('tasks.parameters.options', { options: field.options.join(' / ') }) }}
              </span>
            </div>
          </a-descriptions-item>
        </a-descriptions>
      </section>

      <AppRawJson
        :value="extractToolParams(props.params)"
        :title="t('tasks.parameters.rawJson')"
        test-id="task-parameter-raw"
      />
    </template>

    <p v-else class="parameter-empty" data-testid="task-parameter-empty">
      {{ t('tasks.parameters.empty') }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { buildParameterGroups, extractToolParams } from '@/domain/tasks/parameters'
import AppRawJson from '@/components/common/AppRawJson.vue'

const props = defineProps<{
  params?: Record<string, unknown> | null
  schema?: Record<string, unknown> | null
}>()

const { t, locale } = useI18n()

const groups = computed(() =>
  buildParameterGroups(extractToolParams(props.params), props.schema, {
    locale: locale.value,
    unsetText: t('tasks.parameters.unset'),
    booleanText: { yes: t('tasks.parameters.yes'), no: t('tasks.parameters.no') },
    defaultPrefix: t('tasks.parameters.defaultPrefix'),
  }),
)

</script>

<style scoped>
.task-parameter-table {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.parameter-group-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.parameter-label {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}

.parameter-required {
  color: var(--color-danger, #cf1322);
}

.parameter-range {
  font-size: 12px;
  color: var(--color-text-tertiary, #8c8c8c);
}

.parameter-value {
  display: flex;
  flex-direction: column;
  gap: 2px;
  word-break: break-all;
}

.parameter-value.is-default {
  color: var(--color-text-tertiary, #8c8c8c);
}

.parameter-options {
  font-size: 12px;
  color: var(--color-text-tertiary, #8c8c8c);
}

.parameter-empty {
  margin: 0;
  color: var(--color-text-tertiary, #8c8c8c);
}

.parameter-raw {
  margin-top: 4px;
}

</style>
