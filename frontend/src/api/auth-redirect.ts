type LoginRedirectHandler = (redirectPath: string) => void

let loginRedirectHandler: LoginRedirectHandler | null = null

export const setLoginRedirectHandler = (handler: LoginRedirectHandler) => {
  loginRedirectHandler = handler
}

export const redirectToLogin = (redirectPath: string) => {
  if (loginRedirectHandler) {
    loginRedirectHandler(redirectPath)
    return
  }

  window.location.assign(`/login?redirect=${encodeURIComponent(redirectPath)}`)
}
