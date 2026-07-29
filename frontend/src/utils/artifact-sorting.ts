import type { ArtifactFile } from '@/types/models'

export function sortArtifactsByCreatedAtDesc(artifacts: ArtifactFile[]): ArtifactFile[] {
  return [...artifacts].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
}
