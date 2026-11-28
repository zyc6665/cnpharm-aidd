<template>
  <section class="md-trajectory-artifact" data-testid="md-trajectory-artifact">
    <a-alert
      type="info"
      show-icon
      :message="noticeMessage"
    />
    <FileArtifact :artifact="artifact" />
    <StructureArtifactPreview
      :artifact="artifact"
      role="structure"
      :preferred-file-roles="trajectoryFileRoles"
      :frame-times-ps="movieUnavailable ? null : movieFrameTimesPs"
      :can-export-movie="Boolean(movieFile) && !movieUnavailable"
      @export-movie="handleExportMovie"
      @movie-unavailable="handleMovieUnavailable"
      @movie-available="handleMovieAvailable"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
 * `latest_version.metadata`，两处都做容错读取。只接受**原样的有限 number**：
 * 不做 `Number()` 强转，否则 `null`/空串会被悄悄变成 0，让帧号与时间错位。
 * 长度是否与帧数一致由 `formatTrajectoryFrameLabel` 再校验。
 */
function extractMovieFrameTimes(artifact: TypedArtifact): number[] | null {
  const version = artifact.latest_version as ArtifactVersion & { metadata?: Record<string, unknown> | null }
  for (const metadata of [version.manifest_json?.metadata, version.metadata]) {
    if (!metadata || typeof metadata !== 'object') continue
    const raw = (metadata as Record<string, unknown>).movie_time_ps
    if (!Array.isArray(raw) || raw.length === 0) continue
    const times: number[] = []
    let valid = true
    for (const value of raw) {
      if (typeof value !== 'number' || !Number.isFinite(value)) {
        valid = false
        break
      }
      times.push(value)
    }
    if (valid) return times
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

/**
 * movie 文件存在但预览加载失败（空文件、404/403、内容不是合法 PDB）时，
 * 预览会回退到 topology_pdb 并发出 `movie-unavailable`：
 * 此时不能再展示「可直接播放」的提示，也不能提供导出按钮，否则会误导用户。
 */
const movieUnavailable = ref(false)

watch(
  () => props.artifact.latest_version.id,
  () => {
    movieUnavailable.value = false
  },
)

const noticeMessage = computed(() => {
  if (movieUnavailable.value) return t('artifactAssets.mdTrajectory.movieFallbackNotice')
  return movieFile.value ? t('artifactAssets.mdTrajectory.movieNotice') : t('artifactAssets.mdTrajectory.notice')
})

interface MovieSource {
  artifactId: string
  versionId: string
}

// 预览的加载是异步的：版本刷新后，旧版本那次加载的失败事件仍可能迟到。
// 只接受与当前版本一致的事件，避免把新版本的影片重新锁成降级状态。
function isCurrentMovieSource(source?: MovieSource): boolean {
  if (!source) return true
  return (
    source.artifactId === props.artifact.id &&
    source.versionId === props.artifact.latest_version.id
  )
}

function handleMovieUnavailable(source?: MovieSource): void {
  if (!isCurrentMovieSource(source)) return
  movieUnavailable.value = true
}

// 同一版本重新拉取后影片可能恢复：预览重新选中影片时解除降级。
function handleMovieAvailable(source?: MovieSource): void {
  if (!isCurrentMovieSource(source)) return
  movieUnavailable.value = false
}

async function handleExportMovie(): Promise<void> {
  if (!movieFile.value || movieUnavailable.value) return
  try {
    await triggerProtectedFileDownload(
      {
        url: movieFile.value.download_url,
        filename: movieFile.value.filename ?? undefined,
      },
      {},
      // 影片可能是上一次失败残留的空文件：必须验证实际响应内容再交给浏览器保存。
      { requireContent: true },
    )
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
