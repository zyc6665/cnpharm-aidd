<template>
  <section class="md-trajectory-artifact" data-testid="md-trajectory-artifact">
    <a-alert
      type="info"
      show-icon
      :message="movieFile ? t('artifactAssets.mdTrajectory.movieNotice') : t('artifactAssets.mdTrajectory.notice')"
    />
    <FileArtifact :artifact="artifact" />
    <StructureArtifactPreview
      :artifact="artifact"
      role="structure"
      :preferred-file-roles="trajectoryFileRoles"
      :frame-times-ps="movieFrameTimesPs"
      :can-export-movie="Boolean(movieFile)"
      @export-movie="handleExportMovie"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

import type { ArtifactVersion, ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'

import FileArtifact from './FileArtifact.vue'
import StructureArtifactPreview from './StructureArtifactPreview.vue'

const props = defineProps<{
  artifact: TypedArtifact
}>()

const { t } = useI18n()

const trajectoryFileRoles = ['trajectory_movie_pdb', 'topology_pdb', 'structure_file', 'structure_pdb']

const movieFile = computed<ArtifactVersionFile | null>(() => {
  const files = props.artifact.latest_version.files ?? []
  return files.find(file => file.role === 'trajectory_movie_pdb' && file.download_url) ?? null
})

/**
 * 从版本元数据读取逐帧时间（ps）。
 *
 * 后端把工具元数据挂在 `latest_version.manifest_json.metadata`（与 `FileArtifact` /
 * `api/design` 的读取口径一致）；历史/兼容响应也可能把同名字段直接放在
 * `latest_version.metadata`，两处都做容错读取。只有整组都是有限数值时才返回，
 * 避免个别脏值让帧号与时间错位。
 */
function extractMovieFrameTimes(artifact: TypedArtifact): number[] | null {
  const version = artifact.latest_version as ArtifactVersion & { metadata?: Record<string, unknown> | null }
  for (const metadata of [version.manifest_json?.metadata, version.metadata]) {
    if (!metadata || typeof metadata !== 'object') continue
    const raw = (metadata as Record<string, unknown>).movie_time_ps
    if (!Array.isArray(raw) || raw.length === 0) continue
    const times = raw.map(value => Number(value))
    if (times.every(time => Number.isFinite(time))) return times
  }
  return null
}

const frameTimesPs = computed<number[] | null>(() => extractMovieFrameTimes(props.artifact))

/**
 * 时间数组只在真正选中 movie 时透传；退回历史 `topology_pdb`（静态/拓扑）时必须为 null，
 * 否则会把 movie 的逐帧时间错配到拓扑预览的帧标签上。
 */
const movieFrameTimesPs = computed<number[] | null>(() =>
  movieFile.value ? frameTimesPs.value : null,
)

async function handleExportMovie(): Promise<void> {
  if (!movieFile.value) return
  try {
    await triggerProtectedFileDownload({
      url: movieFile.value.download_url,
      filename: movieFile.value.filename ?? undefined,
    })
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.md-trajectory-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}
</style>
