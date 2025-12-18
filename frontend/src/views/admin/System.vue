<template>
  <div class="admin-system">
    <a-tabs v-model:activeKey="activeTab">
      <!-- 基本设置 -->
      <a-tab-pane key="general" :tab="t('admin.generalSettings')">
        <a-card :title="t('admin.siteSettings')">
          <a-form
            :model="generalForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('admin.siteName')">
              <a-input v-model:value="generalForm.siteName" />
            </a-form-item>
            <a-form-item :label="t('admin.siteDescription')">
              <a-textarea v-model:value="generalForm.siteDescription" :rows="3" />
            </a-form-item>
            <a-form-item :label="t('admin.contactEmail')">
              <a-input v-model:value="generalForm.contactEmail" />
            </a-form-item>
            <a-form-item :label="t('admin.allowRegistration')">
              <a-switch v-model:checked="generalForm.allowRegistration" />
            </a-form-item>
            <a-form-item :label="t('admin.maintenanceMode')">
              <a-switch v-model:checked="generalForm.maintenanceMode" />
              <template #extra>
                {{ t('admin.maintenanceModeDesc') }}
              </template>
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-button type="primary" @click="handleSaveGeneral">
                {{ t('common.save') }}
              </a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 积分设置 -->
      <a-tab-pane key="credits" :tab="t('admin.creditsSettings')">
        <a-card :title="t('admin.creditsConfig')">
          <a-form
            :model="creditsForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('admin.signupBonus')">
              <a-input-number v-model:value="creditsForm.signupBonus" :min="0" />
              <template #extra>{{ t('admin.signupBonusDesc') }}</template>
            </a-form-item>
            <a-form-item :label="t('admin.dailySigninBonus')">
              <a-input-number v-model:value="creditsForm.dailySigninBonus" :min="0" />
            </a-form-item>
            <a-form-item :label="t('admin.inviteBonus')">
              <a-input-number v-model:value="creditsForm.inviteBonus" :min="0" />
              <template #extra>{{ t('admin.inviteBonusDesc') }}</template>
            </a-form-item>
            <a-form-item :label="t('admin.inviteRebate')">
              <a-input-number
                v-model:value="creditsForm.inviteRebate"
                :min="0"
                :max="100"
                :formatter="(value: number) => `${value}%`"
                :parser="(value: string) => Number(value.replace('%', ''))"
              />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-button type="primary" @click="handleSaveCredits">
                {{ t('common.save') }}
              </a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 任务设置 -->
      <a-tab-pane key="tasks" :tab="t('admin.taskSettings')">
        <a-card :title="t('admin.taskConfig')">
          <a-form
            :model="taskForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('admin.maxConcurrentTasks')">
              <a-input-number v-model:value="taskForm.maxConcurrentTasks" :min="1" />
              <template #extra>{{ t('admin.maxConcurrentTasksDesc') }}</template>
            </a-form-item>
            <a-form-item :label="t('admin.taskTimeout')">
              <a-input-number
                v-model:value="taskForm.taskTimeout"
                :min="1"
                :addon-after="t('admin.minutes')"
              />
            </a-form-item>
            <a-form-item :label="t('admin.maxRetries')">
              <a-input-number v-model:value="taskForm.maxRetries" :min="0" :max="10" />
            </a-form-item>
            <a-form-item :label="t('admin.cleanupDays')">
              <a-input-number
                v-model:value="taskForm.cleanupDays"
                :min="1"
                :addon-after="t('admin.days')"
              />
              <template #extra>{{ t('admin.cleanupDaysDesc') }}</template>
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-button type="primary" @click="handleSaveTasks">
                {{ t('common.save') }}
              </a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 存储设置 -->
      <a-tab-pane key="storage" :tab="t('admin.storageSettings')">
        <a-card :title="t('admin.storageConfig')">
          <a-form
            :model="storageForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('admin.storageType')">
              <a-radio-group v-model:value="storageForm.storageType">
                <a-radio value="local">{{ t('admin.localStorage') }}</a-radio>
                <a-radio value="minio">MinIO</a-radio>
                <a-radio value="s3">Amazon S3</a-radio>
              </a-radio-group>
            </a-form-item>

            <template v-if="storageForm.storageType === 'local'">
              <a-form-item :label="t('admin.storagePath')">
                <a-input v-model:value="storageForm.localPath" />
              </a-form-item>
            </template>

            <template v-if="storageForm.storageType === 'minio' || storageForm.storageType === 's3'">
              <a-form-item :label="t('admin.endpoint')">
                <a-input v-model:value="storageForm.endpoint" />
              </a-form-item>
              <a-form-item :label="t('admin.accessKey')">
                <a-input v-model:value="storageForm.accessKey" />
              </a-form-item>
              <a-form-item :label="t('admin.secretKey')">
                <a-input-password v-model:value="storageForm.secretKey" />
              </a-form-item>
              <a-form-item :label="t('admin.bucket')">
                <a-input v-model:value="storageForm.bucket" />
              </a-form-item>
            </template>

            <a-form-item :label="t('admin.maxFileSize')">
              <a-input-number
                v-model:value="storageForm.maxFileSize"
                :min="1"
                :addon-after="'MB'"
              />
            </a-form-item>

            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-space>
                <a-button type="primary" @click="handleSaveStorage">
                  {{ t('common.save') }}
                </a-button>
                <a-button @click="handleTestStorage">
                  {{ t('admin.testConnection') }}
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 邮件设置 -->
      <a-tab-pane key="email" :tab="t('admin.emailSettings')">
        <a-card :title="t('admin.smtpConfig')">
          <a-form
            :model="emailForm"
            :label-col="{ span: 6 }"
            :wrapper-col="{ span: 14 }"
          >
            <a-form-item :label="t('admin.smtpHost')">
              <a-input v-model:value="emailForm.smtpHost" placeholder="smtp.example.com" />
            </a-form-item>
            <a-form-item :label="t('admin.smtpPort')">
              <a-input-number v-model:value="emailForm.smtpPort" :min="1" :max="65535" />
            </a-form-item>
            <a-form-item :label="t('admin.smtpUser')">
              <a-input v-model:value="emailForm.smtpUser" />
            </a-form-item>
            <a-form-item :label="t('admin.smtpPassword')">
              <a-input-password v-model:value="emailForm.smtpPassword" />
            </a-form-item>
            <a-form-item :label="t('admin.senderName')">
              <a-input v-model:value="emailForm.senderName" />
            </a-form-item>
            <a-form-item :label="t('admin.senderEmail')">
              <a-input v-model:value="emailForm.senderEmail" />
            </a-form-item>
            <a-form-item :label="t('admin.useTLS')">
              <a-switch v-model:checked="emailForm.useTLS" />
            </a-form-item>
            <a-form-item :wrapper-col="{ offset: 6, span: 14 }">
              <a-space>
                <a-button type="primary" @click="handleSaveEmail">
                  {{ t('common.save') }}
                </a-button>
                <a-button @click="handleTestEmail">
                  {{ t('admin.sendTestEmail') }}
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 系统信息 -->
      <a-tab-pane key="info" :tab="t('admin.systemInfo')">
        <a-card :title="t('admin.systemInfo')">
          <a-descriptions :column="2" bordered>
            <a-descriptions-item :label="t('admin.version')">1.0.0</a-descriptions-item>
            <a-descriptions-item :label="t('admin.buildTime')">2024-01-15 10:00:00</a-descriptions-item>
            <a-descriptions-item :label="t('admin.pythonVersion')">3.11.6</a-descriptions-item>
            <a-descriptions-item :label="t('admin.nodeVersion')">20.10.0</a-descriptions-item>
            <a-descriptions-item :label="t('admin.os')">Linux 5.15.0</a-descriptions-item>
            <a-descriptions-item :label="t('admin.uptime')">15 days 3 hours</a-descriptions-item>
            <a-descriptions-item :label="t('admin.database')">PostgreSQL 15.4</a-descriptions-item>
            <a-descriptions-item :label="t('admin.redis')">Redis 7.2.3</a-descriptions-item>
          </a-descriptions>
        </a-card>

        <a-card :title="t('admin.gpuInfo')" style="margin-top: 16px">
          <a-table
            :columns="gpuColumns"
            :data-source="gpuInfo"
            :pagination="false"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'memory'">
                <a-progress
                  :percent="Math.round(record.memoryUsed / record.memoryTotal * 100)"
                  size="small"
                />
                <span class="memory-text">
                  {{ record.memoryUsed }}MB / {{ record.memoryTotal }}MB
                </span>
              </template>
              <template v-else-if="column.key === 'utilization'">
                <a-progress :percent="record.utilization" size="small" />
              </template>
            </template>
          </a-table>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

const { t } = useI18n()

const activeTab = ref('general')

// 基本设置
const generalForm = reactive({
  siteName: 'CPUModel',
  siteDescription: '专业的计算生物学工具平台',
  contactEmail: 'support@cpumodel.com',
  allowRegistration: true,
  maintenanceMode: false
})

// 积分设置
const creditsForm = reactive({
  signupBonus: 100,
  dailySigninBonus: 5,
  inviteBonus: 100,
  inviteRebate: 10
})

// 任务设置
const taskForm = reactive({
  maxConcurrentTasks: 10,
  taskTimeout: 60,
  maxRetries: 3,
  cleanupDays: 30
})

// 存储设置
const storageForm = reactive({
  storageType: 'local',
  localPath: '/data/storage',
  endpoint: '',
  accessKey: '',
  secretKey: '',
  bucket: '',
  maxFileSize: 100
})

// 邮件设置
const emailForm = reactive({
  smtpHost: '',
  smtpPort: 587,
  smtpUser: '',
  smtpPassword: '',
  senderName: 'CPUModel',
  senderEmail: '',
  useTLS: true
})

// GPU 信息
const gpuInfo = ref([
  { id: 0, name: 'NVIDIA GeForce RTX 4090', memoryTotal: 24576, memoryUsed: 8192, utilization: 35, temperature: 45 },
  { id: 1, name: 'NVIDIA GeForce RTX 4090', memoryTotal: 24576, memoryUsed: 12288, utilization: 68, temperature: 52 }
])

const gpuColumns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
  { title: t('admin.gpuName'), dataIndex: 'name', key: 'name' },
  { title: t('admin.gpuMemory'), key: 'memory', width: 200 },
  { title: t('admin.gpuUtilization'), key: 'utilization', width: 150 },
  { title: t('admin.gpuTemperature'), dataIndex: 'temperature', key: 'temperature', width: 100, customRender: ({ text }: { text: number }) => `${text}°C` }
]

const handleSaveGeneral = () => {
  // TODO: 保存基本设置
  message.success(t('common.success'))
}

const handleSaveCredits = () => {
  // TODO: 保存积分设置
  message.success(t('common.success'))
}

const handleSaveTasks = () => {
  // TODO: 保存任务设置
  message.success(t('common.success'))
}

const handleSaveStorage = () => {
  // TODO: 保存存储设置
  message.success(t('common.success'))
}

const handleTestStorage = () => {
  // TODO: 测试存储连接
  message.success(t('admin.connectionSuccess'))
}

const handleSaveEmail = () => {
  // TODO: 保存邮件设置
  message.success(t('common.success'))
}

const handleTestEmail = () => {
  // TODO: 发送测试邮件
  message.success(t('admin.testEmailSent'))
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-system {
  .memory-text {
    display: block;
    font-size: @font-size-sm;
    color: @text-color-light-secondary;
    margin-top: @spacing-xs;
  }
}
</style>
