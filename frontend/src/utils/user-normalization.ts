import type { UserInfo } from '@/types/models'

export const normalizeUserInfo = (user: UserInfo | null | undefined): UserInfo | null => {
  if (!user) {
    return null
  }

  const avatarUrl = user.avatar_url ?? user.avatar ?? ''
  const avatar = user.avatar ?? user.avatar_url ?? ''
  const username = user.username ?? user.display_name ?? ''

  return {
    ...user,
    avatar_url: avatarUrl,
    avatar,
    username
  }
}
