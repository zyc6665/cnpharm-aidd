import type { ArtifactFile } from '@/types/models'

export interface ArtifactTaskOptionGroup {
  taskId: string
  toolName: string
  latestCreatedAt: string
  artifacts: ArtifactFile[]
}

const NOISE_FILE_PATTERNS = [
  /(^|\/)(logs?|stderr|stdout)(\/|\.|$)/i,
  /(^|\/)(intermediate|tmp|temp|cache|workdir|scratch)(\/|$)/i,
  /\.(log|err|out|stderr|stdout|tmp|temp|bak|aux)$/i
]

function normalizeFilename(filename: string): string {
  return filename.trim().toLowerCase()
}

function getFileExtension(filename: string): string {
  const normalized = normalizeFilename(filename)
  const basename = normalized.split('/').pop() ?? normalized
  const dotIndex = basename.lastIndexOf('.')
  return dotIndex >= 0 ? basename.slice(dotIndex) : ''
}

function parseAcceptTokens(accept?: string): string[] {
  if (!accept) {
    return []
  }

  return accept
    .split(',')
    .map((token) => token.trim().toLowerCase())
    .filter(Boolean)
}

export function isNoiseArtifact(artifact: ArtifactFile): boolean {
  const filename = normalizeFilename(artifact.filename)
  return NOISE_FILE_PATTERNS.some((pattern) => pattern.test(filename))
}

export function isArtifactCompatibleWithAccept(artifact: ArtifactFile, accept?: string): boolean {
  const tokens = parseAcceptTokens(accept)
  if (tokens.length === 0) {
    return true
  }

  const extension = getFileExtension(artifact.filename)
  const mimeType = artifact.content_type?.toLowerCase() ?? ''

  return tokens.some((token) => {
    if (token.startsWith('.')) {
      return extension === token
    }

    if (token.endsWith('/*')) {
      return mimeType.startsWith(token.slice(0, -1))
    }

    if (token.includes('/')) {
      return mimeType === token
    }

    return extension === `.${token}`
  })
}

export function filterCompatibleArtifacts(artifacts: ArtifactFile[], accept?: string): ArtifactFile[] {
  return artifacts.filter((artifact) => {
    return !isNoiseArtifact(artifact) && isArtifactCompatibleWithAccept(artifact, accept)
  })
}

export function groupCompatibleArtifactsByTask(
  artifacts: ArtifactFile[],
  accept?: string
): ArtifactTaskOptionGroup[] {
  const taskMap = new Map<string, ArtifactFile[]>()

  for (const artifact of filterCompatibleArtifacts(artifacts, accept)) {
    const taskArtifacts = taskMap.get(artifact.task_id) ?? []
    taskArtifacts.push(artifact)
    taskMap.set(artifact.task_id, taskArtifacts)
  }

  return Array.from(taskMap.entries())
    .map(([taskId, taskArtifacts]) => {
      const sortedArtifacts = [...taskArtifacts].sort((left, right) => {
        return Date.parse(right.created_at) - Date.parse(left.created_at)
      })
      const latestArtifact = sortedArtifacts[0]

      return {
        taskId,
        toolName: latestArtifact?.tool_name ?? '-',
        latestCreatedAt: latestArtifact?.created_at ?? '',
        artifacts: sortedArtifacts
      }
    })
    .sort((left, right) => Date.parse(right.latestCreatedAt) - Date.parse(left.latestCreatedAt))
}
