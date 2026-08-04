import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

export default pinia

export { useUserStore } from './user'
export { useAppStore } from './app'
export { useToolsStore } from './tools'
export { useTasksStore } from './tasks'
export { useArtifactsStore } from './artifacts'
export { useWorkflowStore } from './workflow'
export { useWorkflowDefinitionsStore } from './workflow-definitions'
