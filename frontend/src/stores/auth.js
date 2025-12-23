/**
 * Store d'authentification Pinia.
 * Gère les tokens, l'utilisateur courant et les providers SSO.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref(null)
  const accessToken = ref(null)
  const refreshToken = ref(null)
  const providers = ref([])
  const localAuthEnabled = ref(false)  // Auth locale activée (depuis backend) - défaut false pour permettre le bypass
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref(null)

  // 2FA State
  const requires2FA = ref(false)
  const tempToken = ref(null)

  // Computed
  const isAuthenticated = computed(() => !!user.value && !!accessToken.value)

  const isSuperAdmin = computed(() => user.value?.role === 'super_admin')

  const isAdmin = computed(() =>
    user.value?.role === 'super_admin' || user.value?.role === 'admin'
  )

  const isOperator = computed(() =>
    user.value?.role === 'super_admin' || user.value?.role === 'admin' || user.value?.role === 'operator'
  )

  const userDisplayName = computed(() =>
    user.value?.display_name || user.value?.username || 'Utilisateur'
  )

  const authEnabled = computed(() => {
    // Auth activée si local_enabled=true ou s'il y a des providers SSO
    return localAuthEnabled.value || providers.value.length > 0
  })

  // Helpers
  function getStoredTokens() {
    try {
      return {
        access: localStorage.getItem('access_token'),
        refresh: localStorage.getItem('refresh_token')
      }
    } catch {
      return { access: null, refresh: null }
    }
  }

  function storeTokens(access, refresh) {
    try {
      if (access) localStorage.setItem('access_token', access)
      if (refresh) localStorage.setItem('refresh_token', refresh)
      accessToken.value = access
      refreshToken.value = refresh
    } catch (e) {
      console.error('Erreur stockage tokens:', e)
    }
  }

  function clearTokens() {
    try {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    } catch (e) {
      console.error('Erreur suppression tokens:', e)
    }
    accessToken.value = null
    refreshToken.value = null
    user.value = null
  }

  // Flag pour éviter les initialisations parallèles
  let initializingPromise = null

  // Actions

  /**
   * Initialise le store au démarrage de l'app.
   * Charge les tokens stockés et récupère l'utilisateur si possible.
   */
  async function initialize() {
    // Déjà initialisé
    if (initialized.value) return

    // Si une initialisation est déjà en cours, attendre sa fin
    if (initializingPromise) {
      return initializingPromise
    }

    initializingPromise = (async () => {
      loading.value = true
      error.value = null

      try {
        // Charger les providers disponibles
        await fetchProviders()

        // Charger les tokens stockés
        const stored = getStoredTokens()
        if (stored.access) {
          accessToken.value = stored.access
          refreshToken.value = stored.refresh

          // Tenter de récupérer l'utilisateur
          try {
            await fetchCurrentUser()
          } catch (e) {
            // Token invalide, tenter un refresh
            if (stored.refresh) {
              try {
                await refreshAccessToken()
                await fetchCurrentUser()
              } catch {
                // Refresh échoué, nettoyer
                clearTokens()
              }
            } else {
              clearTokens()
            }
          }
        }
      } catch (e) {
        console.error('Erreur initialisation auth:', e)
        error.value = e.message
      } finally {
        initialized.value = true
        loading.value = false
        initializingPromise = null
      }
    })()

    return initializingPromise
  }

  /**
   * Récupère les providers SSO disponibles et l'état de l'auth.
   */
  async function fetchProviders() {
    try {
      const response = await fetch('/api/v1/auth/providers')
      if (response.ok) {
        const data = await response.json()
        providers.value = data.providers || []
        localAuthEnabled.value = data.local_enabled !== false
      }
    } catch (e) {
      console.error('Erreur fetch providers:', e)
      providers.value = []
      // En cas d'erreur, on considère l'auth désactivée pour permettre l'accès
      localAuthEnabled.value = false
    }
  }

  /**
   * Connexion locale avec username/password.
   * Si l'utilisateur a le 2FA activé, retourne { requires2FA: true }
   */
  async function login(username, password) {
    loading.value = true
    error.value = null
    requires2FA.value = false
    tempToken.value = null

    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Identifiants invalides')
      }

      const data = await response.json()

      // Vérifier si 2FA requis
      if (data.requires_2fa) {
        requires2FA.value = true
        tempToken.value = data.temp_token
        return { requires2FA: true }
      }

      // Pas de 2FA, connexion directe
      storeTokens(data.access_token, data.refresh_token)
      await fetchCurrentUser()

      return { requires2FA: false }
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * Complète la connexion avec le code 2FA.
   */
  async function verify2FA(code) {
    if (!tempToken.value) {
      throw new Error('Pas de session 2FA en cours')
    }

    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/v1/auth/login/2fa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          temp_token: tempToken.value,
          code: code
        })
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Code 2FA invalide')
      }

      const data = await response.json()
      storeTokens(data.access_token, data.refresh_token)
      await fetchCurrentUser()

      // Nettoyer l'état 2FA
      requires2FA.value = false
      tempToken.value = null

      return data
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * Annule le processus 2FA.
   */
  function cancel2FA() {
    requires2FA.value = false
    tempToken.value = null
    error.value = null
  }

  /**
   * Déconnexion (révoque la session courante).
   */
  async function logout() {
    loading.value = true

    try {
      if (accessToken.value) {
        await authFetch('/api/v1/auth/logout', { method: 'POST' })
      }
    } catch (e) {
      console.error('Erreur logout:', e)
    } finally {
      clearTokens()
      loading.value = false
    }
  }

  /**
   * Déconnexion de toutes les sessions.
   */
  async function logoutAll() {
    loading.value = true

    try {
      if (accessToken.value) {
        await authFetch('/api/v1/auth/logout-all', { method: 'POST' })
      }
    } catch (e) {
      console.error('Erreur logout all:', e)
    } finally {
      clearTokens()
      loading.value = false
    }
  }

  /**
   * Rafraîchit le token d'accès.
   */
  async function refreshAccessToken() {
    if (!refreshToken.value) {
      throw new Error('No refresh token')
    }

    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken.value })
    })

    if (!response.ok) {
      clearTokens()
      throw new Error('Refresh failed')
    }

    const data = await response.json()
    storeTokens(data.access_token, data.refresh_token)

    return data
  }

  /**
   * Récupère l'utilisateur courant.
   * Note: N'utilise pas authFetch pour éviter la récursion lors de l'initialisation.
   */
  async function fetchCurrentUser() {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    const response = await fetch('/api/v1/auth/me', {
      headers: {
        'Authorization': `Bearer ${accessToken.value}`
      }
    })

    if (!response.ok) {
      throw new Error('Failed to fetch user')
    }

    user.value = await response.json()
    return user.value
  }

  /**
   * Récupère les sessions de l'utilisateur.
   */
  async function fetchSessions() {
    const response = await authFetch('/api/v1/auth/sessions')

    if (!response.ok) {
      throw new Error('Failed to fetch sessions')
    }

    return await response.json()
  }

  /**
   * Révoque une session.
   */
  async function revokeSession(sessionId) {
    const response = await authFetch(`/api/v1/auth/sessions/${sessionId}`, {
      method: 'DELETE'
    })

    if (!response.ok) {
      throw new Error('Failed to revoke session')
    }
  }

  /**
   * Change le mot de passe.
   */
  async function changePassword(currentPassword, newPassword) {
    const response = await authFetch('/api/v1/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword
      })
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur changement mot de passe')
    }
  }

  /**
   * Initie une connexion SSO (OIDC).
   */
  async function loginWithSSO(providerId) {
    try {
      const redirectUri = `${window.location.origin}/auth/callback`
      const response = await fetch(
        `/api/v1/auth/sso/oidc/${providerId}/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`
      )

      if (!response.ok) {
        throw new Error('Erreur initialisation SSO')
      }

      const data = await response.json()

      // Stocker le state pour vérification au retour
      sessionStorage.setItem('sso_state', data.state)
      sessionStorage.setItem('sso_provider', providerId)

      // Rediriger vers l'IdP
      window.location.href = data.authorization_url
    } catch (e) {
      error.value = e.message
      throw e
    }
  }

  /**
   * Gère le callback SSO (appelé depuis SsoCallbackView).
   */
  async function handleSSOCallback(code, state, providerId) {
    loading.value = true
    error.value = null

    try {
      // Vérifier le state
      const storedState = sessionStorage.getItem('sso_state')
      if (state !== storedState) {
        throw new Error('State SSO invalide')
      }

      const redirectUri = `${window.location.origin}/auth/callback`
      const response = await fetch(
        `/api/v1/auth/sso/oidc/${providerId}/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}&redirect_uri=${encodeURIComponent(redirectUri)}`
      )

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Erreur authentification SSO')
      }

      const data = await response.json()
      storeTokens(data.access_token, data.refresh_token)
      user.value = data.user

      // Nettoyer
      sessionStorage.removeItem('sso_state')
      sessionStorage.removeItem('sso_provider')

      return data
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch avec authentification automatique et refresh token.
   * Utiliser cette fonction pour tous les appels API authentifiés.
   * Si l'auth n'est pas activée (AUTH_ENABLED=false), fait un fetch normal.
   */
  async function authFetch(url, options = {}) {
    // S'assurer que le store est initialisé pour connaître l'état de l'auth
    if (!initialized.value) {
      await initialize()
    }

    // Si pas de token, vérifier si l'auth est activée
    if (!accessToken.value) {
      // Auth désactivée = faire un fetch normal sans token
      if (!authEnabled.value) {
        return await fetch(url, options)
      }
      throw new Error('Not authenticated')
    }

    const headers = {
      ...options.headers,
      'Authorization': `Bearer ${accessToken.value}`
    }

    let response = await fetch(url, { ...options, headers })

    // Si 401, tenter un refresh
    if (response.status === 401 && refreshToken.value) {
      try {
        await refreshAccessToken()
        headers['Authorization'] = `Bearer ${accessToken.value}`
        response = await fetch(url, { ...options, headers })
      } catch {
        // Refresh échoué, nettoyer et propager
        clearTokens()
        throw new Error('Session expirée')
      }
    }

    return response
  }

  function clearError() {
    error.value = null
  }

  // === 2FA Management ===

  /**
   * Initie la configuration 2FA.
   * Retourne le QR code, secret et codes de secours.
   */
  async function setup2FA() {
    const response = await authFetch('/api/v1/auth/2fa/setup', {
      method: 'POST'
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur configuration 2FA')
    }

    return await response.json()
  }

  /**
   * Active le 2FA après vérification d'un code.
   */
  async function enable2FA(code) {
    const response = await authFetch('/api/v1/auth/2fa/enable', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur activation 2FA')
    }

    // Mettre à jour l'utilisateur
    if (user.value) {
      user.value.totp_enabled = true
    }

    return await response.json()
  }

  /**
   * Désactive le 2FA.
   */
  async function disable2FA(password) {
    const response = await authFetch('/api/v1/auth/2fa/disable', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur désactivation 2FA')
    }

    // Mettre à jour l'utilisateur
    if (user.value) {
      user.value.totp_enabled = false
    }

    return await response.json()
  }

  /**
   * Régénère les codes de secours.
   */
  async function regenerateBackupCodes(code) {
    const response = await authFetch('/api/v1/auth/2fa/regenerate-backup-codes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur régénération codes')
    }

    return await response.json()
  }

  return {
    // State
    user,
    accessToken,
    refreshToken,
    providers,
    initialized,
    loading,
    error,
    requires2FA,
    tempToken,
    // Computed
    isAuthenticated,
    isSuperAdmin,
    isAdmin,
    isOperator,
    userDisplayName,
    authEnabled,
    // Actions
    initialize,
    fetchProviders,
    login,
    verify2FA,
    cancel2FA,
    logout,
    logoutAll,
    refreshAccessToken,
    fetchCurrentUser,
    fetchSessions,
    revokeSession,
    changePassword,
    loginWithSSO,
    handleSSOCallback,
    authFetch,
    clearError,
    // 2FA Management
    setup2FA,
    enable2FA,
    disable2FA,
    regenerateBackupCodes,
  }
})
