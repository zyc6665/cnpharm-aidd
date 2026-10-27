<template>
  <div class="admin-compute">
    <AppPageHeader :title="t('admin.compute.title')" :subtitle="t('admin.compute.subtitle')">
      <template #actions>
        <a-button @click="refreshComputeData" :loading="loading">
          <ReloadOutlined /> {{ t('common.refresh') }}
        </a-button>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="compute-empty"
      type="error"
      show-icon
      :message="t('admin.compute.loadError')"
    />

    <a-alert
      v-else-if="!loading && overview && !overview.configured"
      class="compute-empty"
      type="info"
      show-icon
      :message="t('admin.compute.emptyState')"
    />

    <a-row :gutter="[16, 16]" class="compute-stats">
      <a-col :xs="24" :sm="12" :xl="6">
        <a-card :loading="loading">
          <a-statistic :title="t('admin.compute.totalSlots')" :value="capacity.totalSlots" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :xl="6">
        <a-card :loading="loading">
          <a-statistic :title="t('admin.compute.schedulableSlots')" :value="capacity.schedulableSlots" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="24" :xl="12">
        <a-card :title="t('admin.compute.byVendor')" :loading="loading">
          <div v-if="vendorEntries.length > 0" class="compute-vendors">
            <a-tag v-for="[vendor, count] in vendorEntries" :key="vendor" color="blue">
              {{ vendor }}: {{ count }}
            </a-tag>
          </div>
          <AppEmptyState
            v-else
            size="compact"
            :title="t('admin.compute.emptyVendorTitle')"
            :description="t('admin.compute.emptyVendorHint')"
          />
        </a-card>
      </a-col>
    </a-row>

    <a-card :title="t('admin.compute.slotState')" :loading="loading" class="compute-state-card">
      <a-row :gutter="[12, 12]">
        <a-col v-for="state in SLOT_STATES" :key="state" :xs="12" :sm="8" :xl="4">
          <div class="compute-state">
            <a-badge :status="SLOT_STATE_TONES[state]" :text="t(`admin.compute.state.${state}`)" />
            <span class="compute-state__count">{{ stateCounts[state] }}</span>
          </div>
        </a-col>
      </a-row>
    </a-card>

    <a-spin :spinning="loading">
      <section v-for="node in overview?.nodes ?? []" :key="node.id" class="compute-node">
        <header class="compute-node__header">
          <h3>{{ node.hostname || node.id }}</h3>
          <p class="compute-node__meta">
            <span>{{ t('admin.compute.nodeId') }}: {{ node.id }}</span>
            <span>{{ t('admin.compute.gpuCount') }}: {{ node.gpu_count }}</span>
            <span v-if="node.agent_endpoint">{{ t('admin.compute.agentEndpoint') }}: {{ node.agent_endpoint }}</span>
          </p>
        </header>

        <AppEmptyState
          v-if="node.slots.length === 0"
          size="compact"
          :title="t('admin.compute.emptyNodeTitle')"
          :description="t('admin.compute.emptyNodeHint')"
        />

        <div v-else class="compute-slots">
          <article v-for="slot in node.slots" :key="slot.slot_id || slot.slot_identifier" class="compute-slot">
            <div class="compute-slot__head">
              <span class="compute-slot__id">{{ formatSlotIdentifier(slot) }}</span>
              <a-tag :color="toneToTagColor(SLOT_STATE_TONES[slot.state])">{{ t(`admin.compute.state.${slot.state}`) }}</a-tag>
              <span v-if="slot.state === 'UNKNOWN'" class="compute-slot__raw">
                {{ t('admin.compute.rawState') }}: {{ slot.raw_state }}
              </span>
            </div>
            <dl class="compute-slot__meta">
              <div>
                <dt>{{ t('admin.compute.acceleratorModel') }}</dt>
                <dd>{{ slot.accelerator_model || '-' }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.compute.acceleratorVendor') }}</dt>
                <dd>{{ slot.accelerator_vendor || '-' }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.compute.deviceCount') }}</dt>
                <dd>{{ slot.device_count }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.compute.schedulable') }}</dt>
                <dd>{{ slot.schedulable ? t('admin.compute.yes') : t('admin.compute.no') }}</dd>
              </div>
            </dl>
            <p v-if="slot.state_message" class="compute-slot__message">{{ slot.state_message }}</p>
          </article>
        </div>
      </section>

      <AppEmptyState
        v-if="!loading && (overview?.nodes.length ?? 0) === 0"
        :title="t('admin.compute.emptyTitle')"
        :description="t('admin.compute.emptyHint')"
      />
    </a-spin>

    <a-card :title="t('admin.compute.allocations')" class="compute-allocations">
      <a-table
        :scroll="{ x: 900 }"
        :columns="allocationColumns"
        :data-source="allocations"
        :loading="allocationLoading"
        :pagination="false"
        :locale="{ emptyText: t('admin.compute.noAllocations') }"
        row-key="id"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'task_id'">
            <span>{{ record.task_id || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'slot_id'">
            <span>{{ record.slot_id || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'gpu_node_id'">
            <span>{{ record.gpu_node_id || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'accelerator_model'">
            <span>{{ record.accelerator_model || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'gpu_index'">
            <span>{{ record.gpu_index === null ? '-' : `#${record.gpu_index}` }}</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'active' ? 'processing' : 'default'">{{ record.status }}</a-tag>
          </template>
          <template v-else-if="column.key === 'allocated_at'">
            <span>{{ formatAdminDateTime(record.allocated_at) }}</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined } from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import { getGpuSlotOverview, listGpuAllocations } from '@/api/gpu'
import {
  SLOT_STATES,
  SLOT_STATE_TONES,
  countSlotsByState,
  formatSlotIdentifier,
  summarizeSlotCapacity
} from '@/domain/admin/compute'
import { formatAdminDateTime } from '@/domain/admin/system-health'
import type { GpuAllocation, GpuSlotOverview } from '@/types/gpu'

const { t } = useI18n()

const loading = ref(false)
const loadError = ref(false)
const overview = ref<GpuSlotOverview | null>(null)
const allocationLoading = ref(false)
const allocations = ref<GpuAllocation[]>([])

const allSlots = computed(() => (overview.value?.nodes ?? []).flatMap(node => node.slots))
const stateCounts = computed(() => countSlotsByState(allSlots.value))
const capacity = computed(() => summarizeSlotCapacity(overview.value?.nodes ?? []))
const vendorEntries = computed(() => Object.entries(capacity.value.byVendor))

const allocationColumns = computed(() => [
  { title: t('admin.compute.taskId'), key: 'task_id', dataIndex: 'task_id', width: 220 },
  { title: t('admin.compute.slot'), key: 'slot_id', dataIndex: 'slot_id', width: 200 },
  { title: t('admin.compute.gpuNode'), key: 'gpu_node_id', dataIndex: 'gpu_node_id', width: 180 },
  { title: t('admin.compute.gpuIndex'), key: 'gpu_index', dataIndex: 'gpu_index', width: 110 },
  { title: t('admin.compute.acceleratorModel'), key: 'accelerator_model', dataIndex: 'accelerator_model', width: 180 },
  { title: t('common.status'), key: 'status', dataIndex: 'status', width: 120 },
  { title: t('admin.compute.allocatedAt'), key: 'allocated_at', dataIndex: 'allocated_at', width: 190 }
])

const toneToTagColor = (tone: 'success' | 'processing' | 'warning' | 'error' | 'default'): string => {
  switch (tone) {
    case 'success':
      return 'green'
    case 'processing':
      return 'blue'
    case 'warning':
      return 'orange'
    case 'error':
      return 'red'
    default:
      return 'default'
  }
}

const fetchOverview = async (): Promise<void> => {
  loading.value = true
  try {
    const response = await getGpuSlotOverview()
    overview.value = response.data ?? null
    loadError.value = false
  } catch {
    overview.value = null
    loadError.value = true
  } finally {
    loading.value = false
  }
}

const fetchAllocations = async (): Promise<void> => {
  allocationLoading.value = true
  try {
    const response = await listGpuAllocations()
    allocations.value = response.data ?? []
  } catch {
    allocations.value = []
  } finally {
    allocationLoading.value = false
  }
}

const refreshComputeData = async (): Promise<void> => {
  await Promise.all([fetchOverview(), fetchAllocations()])
}

onMounted(refreshComputeData)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-compute {
  .compute-empty {
    margin-bottom: @spacing-lg;
  }

  .compute-stats {
    margin-bottom: @spacing-lg;
  }

  .compute-vendors {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-sm;
  }

  .compute-state-card {
    margin-bottom: @spacing-lg;
  }

  .compute-state {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: 8px;
  }

  .compute-state__count {
    font-size: @font-size-lg;
    font-weight: 600;
    color: @text-color-light-primary;
  }

  .compute-node {
    padding: @spacing-lg;
    margin-bottom: @spacing-lg;
    border: 1px solid @border-color-light;
    border-radius: 12px;
  }

  .compute-node__header {
    margin-bottom: @spacing-md;

    h3 {
      margin: 0;
      font-size: @font-size-lg;
      color: @text-color-light-primary;
    }
  }

  .compute-node__meta {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-md;
    margin: @spacing-xs 0 0;
    font-size: @font-size-xs;
    color: @text-color-light-secondary;
  }

  .compute-slots {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: @spacing-md;
  }

  .compute-slot {
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: 10px;
  }

  .compute-slot__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    margin-bottom: @spacing-sm;
  }

  .compute-slot__id {
    font-weight: 600;
    color: @text-color-light-primary;
    word-break: break-all;
  }

  .compute-slot__meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-xs @spacing-md;
    margin: 0;

    div {
      min-width: 0;
    }

    dt {
      font-size: @font-size-xs;
      color: @text-color-light-tertiary;
    }

    dd {
      margin: 0;
      font-size: @font-size-sm;
      color: @text-color-light-secondary;
      word-break: break-all;
    }
  }

  .compute-slot__message {
    margin: @spacing-sm 0 0;
    font-size: @font-size-xs;
    color: @text-color-light-tertiary;
  }

  .compute-allocations {
    margin-top: @spacing-lg;
  }
}
</style>
