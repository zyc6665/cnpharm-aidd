<template>
  <div class="research-page">
    <header class="research-header">
      <router-link to="/workspace" class="back-link" aria-label="返回工作台"><ArrowLeftOutlined /></router-link>
      <div><strong>{{ store.project?.name || '研究项目' }}</strong><span>{{ activeConversation?.title || '研究会话' }}</span></div>
      <span :class="['connection-state', { online: stream.connected.value }]">
        {{ stream.connected.value ? '实时连接' : stream.reconnecting.value ? '正在重连' : '已保存' }}
      </span>
    </header>

    <div v-if="store.loading" class="center-state"><a-skeleton active /></div>
    <div v-else-if="store.error" class="center-state error-state">
      <strong>项目研究数据加载失败</strong><span>{{ store.error }}</span>
      <a-button @click="reload">重试</a-button>
    </div>
    <div v-else class="research-layout">
      <ConversationSidebar
        :conversations="store.conversations"
        :active-id="store.activeConversationId"
        @select="selectConversation"
        @create="createConversation"
      />
      <main class="conversation-main">
        <div class="conversation-scroll">
          <MessageTimeline
            :messages="store.messages"
            :can-run="store.canRun"
            @approve="decidePlan($event, 'approve')"
            @reject="decidePlan($event, 'reject')"
            @branch="branchMessage"
          />
          <AgentTrace :events="store.events" :show-retry="runFailed" @retry="retryRun" />
        </div>
        <MessageComposer
          :disabled="sending"
          :editing="Boolean(branchSource)"
          :initial-text="branchSource?.plain_text"
          v-model:protein-artifact-version-id="selectedProteinArtifactVersionId"
          :protein-artifact-options="proteinArtifactOptions"
          @submit="sendMessage"
          @stop="stopRun"
          @regenerate="regenerateRun"
          @cancel-edit="branchSource = null"
        />
      </main>
      <ProjectInspector :project="store.project" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { getProjectArtifacts } from '@/api/artifacts'
import {
  cancelProjectAgentRun,
  createProjectConversation,
  startProjectAgentRun,
} from '@/api/conversations'
import ConversationSidebar from '@/components/conversation/ConversationSidebar.vue'
import MessageTimeline from '@/components/conversation/MessageTimeline.vue'
import MessageComposer from '@/components/conversation/MessageComposer.vue'
import AgentTrace from '@/components/conversation/AgentTrace.vue'
import ProjectInspector from '@/components/conversation/ProjectInspector.vue'
import { useAgentEventStream } from '@/composables/useAgentEventStream'
import { useProjectConversationStore } from '@/stores/project-conversation'
import type { TypedArtifact } from '@/types/artifacts'
import type { ConversationMessage } from '@/types/conversations'

const route = useRoute()
const router = useRouter()
const store = useProjectConversationStore()
const stream = useAgentEventStream()
const sending = ref(false)
const branchSource = ref<ConversationMessage | null>(null)
const proteinArtifacts = ref<TypedArtifact[]>([])
const selectedProteinArtifactVersionId = ref<string | undefined>()
const projectId = computed(() => String(route.params.projectId || ''))
const activeConversation = computed(() => store.conversations.find(item => item.id === store.activeConversationId))
const runFailed = computed(() => store.events.some(event => event.event_type.includes('fail')))
const latestUserMessage = computed(() => [...store.messages].reverse().find(message => message.role === 'user'))
const proteinArtifactOptions = computed(() => proteinArtifacts.value.map(artifact => ({
  value: artifact.latest_version.id,
  label: `${artifact.latest_version.filename || artifact.name} · v${artifact.latest_version.version}`,
})))

async function reload() {
  await Promise.all([
    store.loadProject(projectId.value, String(route.params.conversationId || '')),
    loadProteinArtifacts(),
  ])
}

function isProteinArtifact(artifact: TypedArtifact): boolean {
  const semanticType = artifact.semantic_type
  const standardType = artifact.standard_type
  return (
    semanticType === 'protein_pdb' ||
    semanticType === 'protein_structure' ||
    semanticType === 'protein_structure@1' ||
    standardType === 'protein_structure'
  )
}

async function loadProteinArtifacts() {
  if (!projectId.value) {
    proteinArtifacts.value = []
    selectedProteinArtifactVersionId.value = undefined
    return
  }

  const response = await getProjectArtifacts(projectId.value)
  proteinArtifacts.value = response.data.items.filter(isProteinArtifact)
  const optionValues = new Set(proteinArtifactOptions.value.map(option => option.value))
  if (
    !selectedProteinArtifactVersionId.value ||
    !optionValues.has(selectedProteinArtifactVersionId.value)
  ) {
    selectedProteinArtifactVersionId.value = proteinArtifactOptions.value[0]?.value
  }
}

async function selectConversation(conversationId: string) {
  store.resetEvents()
  await store.loadMessages(conversationId)
  await router.push({ name: 'ProjectResearch', params: { projectId: projectId.value, conversationId } })
}

async function createConversation() {
  const response = await createProjectConversation(projectId.value, `研究会话 ${store.conversations.length + 1}`)
  store.conversations.unshift(response.data)
  await selectConversation(response.data.id)
}

async function sendMessage(text: string) {
  sending.value = true
  try {
    if (branchSource.value) {
      await store.branchFromMessage(branchSource.value, text)
      branchSource.value = null
    } else {
      await store.sendMessage(text)
    }
    await startRun(text)
  } finally {
    sending.value = false
  }
}

async function startRun(message: string) {
  if (!store.activeConversationId) return
  const response = await startProjectAgentRun(projectId.value, store.activeConversationId, {
    goal: message,
    protein_artifact_version_id: selectedProteinArtifactVersionId.value,
  })
  stream.connect(response.data.id)
}

async function stopRun() {
  if (!store.activeRunId) return
  await cancelProjectAgentRun(projectId.value, store.activeRunId)
  stream.disconnect()
}

async function regenerateRun() {
  if (latestUserMessage.value) await startRun(latestUserMessage.value.plain_text)
}

async function retryRun() {
  if (latestUserMessage.value) await startRun(latestUserMessage.value.plain_text)
}

async function branchMessage(message: ConversationMessage) {
  branchSource.value = message
}

async function decidePlan(planId: string, decision: 'approve' | 'reject') {
  if (!store.canRun) return
  await store.decidePlan(planId, decision)
}

watch(
  () => store.activeRunId,
  runId => {
    if (runId) stream.connect(runId)
  },
)

onMounted(reload)
</script>

<style scoped lang="less">
.research-page { height: 100vh; min-height: 620px; display: grid; grid-template-rows: 50px minmax(0, 1fr); background: @bg-body; color: @text-primary; overflow: hidden; }
.research-header { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 0 16px; border-bottom: 1px solid @border-color; background: @bg-surface; }
.research-header div { min-width: 0; display: flex; align-items: baseline; gap: 10px; }.research-header div span { overflow: hidden; color: @text-tertiary; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.back-link { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 5px; color: @text-secondary; }.back-link:hover { background: @bg-hover; color: @text-primary; }
.connection-state { display: flex; align-items: center; gap: 6px; font-size: 12px; color: @text-tertiary; }.connection-state::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: @text-tertiary; }.connection-state.online::before { background: @success-color; }
.research-layout { min-height: 0; display: grid; grid-template-columns: 220px minmax(480px, 1fr) 260px; }
.conversation-main { position: relative; min-width: 0; min-height: 0; }.conversation-scroll { box-sizing: border-box; height: 100%; padding-bottom: 150px; overflow-y: auto; }
.center-state { width: min(720px, calc(100% - 40px)); margin: 70px auto; }.error-state { display: grid; justify-items: start; gap: 10px; }.error-state span { color: @text-secondary; }
@media (max-width: 1180px) { .research-layout { grid-template-columns: 200px minmax(420px, 1fr); }.research-layout > :last-child { display: none; } }
@media (max-width: @screen-md) { .research-page { min-height: 100dvh; height: 100dvh; }.research-layout { grid-template-columns: 1fr; }.research-layout > :first-child { display: none; } }
</style>
