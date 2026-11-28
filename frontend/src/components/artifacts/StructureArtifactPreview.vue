<template>
  <div v-if="scene" class="structure-artifact-preview" data-testid="structure-artifact-preview">
    <component
      :is="MoleculeViewer"
      :scene="scene"
      :mode="resolvedMode"
      :frame-times-ps="frameTimesPs"
      :can-export-movie="canExportMovie"
      @export-movie="emit('export-movie')"
      @entry-unavailable="handleEntryUnavailable"
    />
  </div>
  <a-alert
    v-else-if="hasFiles || versionUnavailable"
    type="warning"
    show-icon
    class="structure-artifact-preview__unavailable"
    data-testid="structure-preview-unavailable"
    :message="t('artifactAssets.structurePreview.unavailable')"
  />
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import {
  createVisualizationScene,
  detectVisualizationFormat,
  resolveMolstarStructureArtifactMode,
  type MolstarViewerMode,
  type VisualizationSceneEntry,
} from '@/domain/tasks'
import type { ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'

const props = withDefaults(
  defineProps<{
    artifact: TypedArtifact
    role?: VisualizationSceneEntry['role']
    mode?: MolstarViewerMode
    preferredFileRoles?: string[]
    /** 每一 movie 帧对应的物理时间（ps），透传给 MoleculeViewer 的播放条。 */
    frameTimesPs?: number[] | null
    /** 是否允许导出 movie（存在 `trajectory_movie_pdb` 时为 true）。 */
    canExportMovie?: boolean
  }>(),
  {
    role: 'structure',
    frameTimesPs: null,
    canExportMovie: false,
  }
)

interface MovieSource {
  artifactId: string
  versionId: string
}

const emit = defineEmits<{
  'export-movie': []
  'movie-unavailable': [source: MovieSource]
  'movie-available': [source: MovieSource]
}>()

const { t } = useI18n()

const MoleculeViewer = defineAsyncComponent(() => import('@/components/tasks/MoleculeViewer.vue'))

/** 文件身份：优先 role，缺省时退回 file_id/文件名，保证同一文件只会被标记失败一次。 */
function fileIdentity(file: ArtifactVersionFile): string {
  return file.role || file.file_id || file.id || file.filename || ''
}

/**
 * 已确认无法加载的文件身份。
 *
 * 首选文件（如多帧 PDB-movie）可能是空文件/404/内容损坏：MoleculeViewer 对
 * `fallbackOnFailure` 条目不中断整场景，而是发出 `entry-unavailable`，这里记下
 * 失败的候选并重算 scene，自动回退到下一个候选（如 topology_pdb）；全部候选
 * 都失败时 scene 为 null，显示「无法预览」而不是一块空白画布。
 */
const failedFiles = ref<string[]>([])

/**
 * 版本级下载地址（`latest_version.files` 为空时的回退候选）失败。
 * 该候选没有 role 文件可记录，必须单独标记，否则 `hasFiles` 为 false 会让
 * 模板既不渲染查看器、也不渲染降级提示，留下一块空白。
 */
const versionUnavailable = ref(false)

/**
 * 每次父组件换入新的 artifact 对象（刷新、同版本重新拉取都算）就开启新一代加载。
 * 旧一代的失败回调可能晚于新对象到达（下载/解析是异步的），只用版本号比对无法区分
 * 「同版本的新一次尝试」，因此在 entry key 里带上代次，旧事件自然失配被忽略。
 */
const loadAttempt = ref(0)

watch(
  () => props.artifact,
  () => {
    loadAttempt.value += 1
    failedFiles.value = []
    versionUnavailable.value = false
  },
  // flush: 'sync' 保证父组件刚把新对象传进来的同一轮事件循环里 key 就已换代，
  // 不给旧一代的迟到失败留出「仍匹配当前 key」的窗口。
  { flush: 'sync' }
)

const files = computed<ArtifactVersionFile[]>(() => props.artifact.latest_version.files ?? [])

const hasFiles = computed(() => files.value.length > 0)

const selectedRoleFile = computed<ArtifactVersionFile | null>(() => {
  if (!files.value.length) {
    return null
  }

  const failed = new Set(failedFiles.value)
  for (const role of props.preferredFileRoles ?? []) {
    const match = files.value.find(
      file => file.role === role && file.download_url && !failed.has(fileIdentity(file))
    )
    if (match) {
      return match
    }
  }

  const usable = files.value.filter(file => !failed.has(fileIdentity(file)))
  return usable.find(file => file.is_primary && file.download_url) || usable[0] || null
})

/**
 * 当前候选条目的唯一 key（带文件身份）。
 * 失败事件的 key 与之比对后才记为失败，避免旧场景的迟到事件污染新选中的文件。
 */
const entryKey = computed(
  () =>
    `artifact-${props.artifact.id}@${props.artifact.latest_version.id}#${loadAttempt.value}-${
      selectedRoleFile.value ? fileIdentity(selectedRoleFile.value) : 'version'
    }`
)

const fileRef = computed(() => ({
  id: selectedRoleFile.value?.file_id || props.artifact.latest_version.id,
  filename: selectedRoleFile.value?.filename || props.artifact.latest_version.filename,
  content_type:
    selectedRoleFile.value?.content_type || props.artifact.latest_version.content_type || undefined,
  url:
    selectedRoleFile.value?.download_url ||
    buildArtifactVersionDownloadUrl(props.artifact.id, props.artifact.latest_version.id),
}))

const detectedFormat = computed(() => detectVisualizationFormat(fileRef.value))

const resolvedMode = computed(() =>
  resolveMolstarStructureArtifactMode({
    explicitMode: props.mode,
    role: props.role,
    artifactType: props.artifact.artifact_type,
    format: detectedFormat.value,
  })
)

/** 事件携带源版本，父页面据此忽略「刷新前那一代」的迟到失败。 */
function movieSource(): MovieSource {
  return { artifactId: props.artifact.id, versionId: props.artifact.latest_version.id }
}

function handleEntryUnavailable(key: string): void {
  if (key !== entryKey.value) return
  const failedFile = selectedRoleFile.value
  if (!failedFile) {
    versionUnavailable.value = true
    return
  }
  const identity = fileIdentity(failedFile)
  if (!failedFiles.value.includes(identity)) {
    failedFiles.value = [...failedFiles.value, identity]
  }
  if (failedFile.role === 'trajectory_movie_pdb') {
    emit('movie-unavailable', movieSource())
  }
}

const scene = computed(() => {
  // 有候选文件但全部加载失败，或版本级回退地址也失败：不再生成不可用条目，
  // 交给模板显示降级提示。
  if ((hasFiles.value && !selectedRoleFile.value) || versionUnavailable.value) {
    return null
  }

  const format = detectedFormat.value
  if (!format) {
    return null
  }

  const extension = `.${format === 'mmcif' ? 'cif' : format}`
  const selectedRole = selectedRoleFile.value?.role
  const entry: VisualizationSceneEntry = {
    key: entryKey.value,
    url: fileRef.value.url,
    label: props.artifact.name,
    source: 'output',
    role: props.role,
    format,
    extension,
    // 命中多帧 movie 时用 polymer-and-ligand 保留配体/小分子；回退 topology_pdb 时为 false。
    preferComplexRepresentation: selectedRole === 'trajectory_movie_pdb',
    // 单条加载失败时回退给上层换下一个候选，而不是整块画布空白。
    fallbackOnFailure: true,
  }

  return createVisualizationScene([], [entry], [])
})

/**
 * 影片重新被选中（首次加载、失败后回退、刷新后重选）时通知父页面。
 * 父页面据此清掉「影片不可用」的降级状态：同一版本的 artifact 重新拉取后，
 * 影片可能已恢复，而父页面只按版本号变化重置是看不到这种情况的。
 */
const movieSelected = computed(
  () => scene.value !== null && selectedRoleFile.value?.role === 'trajectory_movie_pdb'
)

watch(movieSelected, selected => {
  if (selected) {
    emit('movie-available', movieSource())
  }
})
</script>

<style scoped lang="less">
.structure-artifact-preview {
  min-height: 360px;
}

.structure-artifact-preview__unavailable {
  border-radius: 8px;
}
</style>
