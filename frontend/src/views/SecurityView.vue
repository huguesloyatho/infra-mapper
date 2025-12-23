<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

// État
const loading = ref(false)
const error = ref('')
const success = ref('')

// 2FA Setup
const setupStep = ref('idle') // idle, setup, verify, done
const qrCode = ref('')
const secret = ref('')
const backupCodes = ref([])
const verifyCode = ref('')

// Disable 2FA
const showDisableModal = ref(false)
const disablePassword = ref('')

// Regenerate backup codes
const showRegenerateModal = ref(false)
const regenerateCode = ref('')
const newBackupCodes = ref([])

// Change password
const showPasswordModal = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

const is2FAEnabled = computed(() => authStore.user?.totp_enabled)

// 2FA Setup Flow
async function startSetup() {
  loading.value = true
  error.value = ''

  try {
    const data = await authStore.setup2FA()
    qrCode.value = data.qr_code
    secret.value = data.secret
    backupCodes.value = data.backup_codes
    setupStep.value = 'setup'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function verifyAndEnable() {
  if (!verifyCode.value || verifyCode.value.length < 6) {
    error.value = 'Veuillez entrer un code à 6 chiffres'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await authStore.enable2FA(verifyCode.value)
    setupStep.value = 'done'
    success.value = '2FA activé avec succès!'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function cancelSetup() {
  setupStep.value = 'idle'
  qrCode.value = ''
  secret.value = ''
  backupCodes.value = []
  verifyCode.value = ''
  error.value = ''
}

function finishSetup() {
  setupStep.value = 'idle'
  qrCode.value = ''
  secret.value = ''
  backupCodes.value = []
  verifyCode.value = ''
}

// Disable 2FA
async function disable2FA() {
  if (!disablePassword.value) {
    error.value = 'Veuillez entrer votre mot de passe'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await authStore.disable2FA(disablePassword.value)
    showDisableModal.value = false
    disablePassword.value = ''
    success.value = '2FA désactivé'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Regenerate backup codes
async function regenerateBackupCodes() {
  if (!regenerateCode.value || regenerateCode.value.length < 6) {
    error.value = 'Veuillez entrer un code à 6 chiffres'
    return
  }

  loading.value = true
  error.value = ''

  try {
    const data = await authStore.regenerateBackupCodes(regenerateCode.value)
    newBackupCodes.value = data.backup_codes
    regenerateCode.value = ''
    success.value = 'Codes de secours régénérés'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function closeRegenerateModal() {
  showRegenerateModal.value = false
  regenerateCode.value = ''
  newBackupCodes.value = []
}

// Change password
async function changePassword() {
  error.value = ''

  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    error.value = 'Veuillez remplir tous les champs'
    return
  }

  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Les mots de passe ne correspondent pas'
    return
  }

  if (newPassword.value.length < 8) {
    error.value = 'Le mot de passe doit faire au moins 8 caractères'
    return
  }

  loading.value = true

  try {
    await authStore.changePassword(currentPassword.value, newPassword.value)
    showPasswordModal.value = false
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    success.value = 'Mot de passe modifié avec succès'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text)
  success.value = 'Copié dans le presse-papiers'
  setTimeout(() => success.value = '', 2000)
}

function copyAllBackupCodes(codes) {
  const text = codes.join('\n')
  navigator.clipboard.writeText(text)
  success.value = 'Codes copiés dans le presse-papiers'
  setTimeout(() => success.value = '', 2000)
}

onMounted(() => {
  // Refresh user data
  authStore.fetchCurrentUser()
})
</script>

<template>
  <div class="h-full overflow-auto bg-gray-900 p-6">
    <div class="max-w-2xl mx-auto space-y-6">
      <!-- Header -->
      <div>
        <h1 class="text-2xl font-bold text-white">Sécurité du compte</h1>
        <p class="mt-1 text-gray-400">Gérez la sécurité de votre compte</p>
      </div>

      <!-- Success message -->
      <div
        v-if="success"
        class="bg-green-900/50 border border-green-500 text-green-300 px-4 py-3 rounded flex items-center justify-between"
      >
        <span>{{ success }}</span>
        <button @click="success = ''" class="text-green-400 hover:text-green-300">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Error message -->
      <div
        v-if="error"
        class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded flex items-center justify-between"
      >
        <span>{{ error }}</span>
        <button @click="error = ''" class="text-red-400 hover:text-red-300">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 2FA Section -->
      <div class="bg-gray-800 rounded-lg p-6">
        <div class="flex items-start justify-between">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-10 h-10 rounded-full flex items-center justify-center"
                   :class="is2FAEnabled ? 'bg-green-900/50' : 'bg-gray-700'">
                <svg class="w-5 h-5" :class="is2FAEnabled ? 'text-green-400' : 'text-gray-400'"
                     fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <h2 class="text-lg font-medium text-white">Authentification à deux facteurs (2FA)</h2>
              <p class="text-sm text-gray-400">
                {{ is2FAEnabled
                  ? 'Votre compte est protégé par une authentification à deux facteurs'
                  : 'Ajoutez une couche de sécurité supplémentaire à votre compte'
                }}
              </p>
            </div>
          </div>
          <span
            class="px-2.5 py-0.5 rounded-full text-xs font-medium"
            :class="is2FAEnabled ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'"
          >
            {{ is2FAEnabled ? 'Activé' : 'Désactivé' }}
          </span>
        </div>

        <!-- 2FA Actions -->
        <div class="mt-6">
          <!-- Not enabled - show setup button -->
          <template v-if="!is2FAEnabled && setupStep === 'idle'">
            <button
              @click="startSetup"
              :disabled="loading"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md
                     disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ loading ? 'Chargement...' : 'Configurer le 2FA' }}
            </button>
          </template>

          <!-- Setup step - QR code -->
          <template v-else-if="setupStep === 'setup'">
            <div class="space-y-6">
              <div class="bg-gray-900 rounded-lg p-4">
                <h3 class="text-sm font-medium text-white mb-2">1. Scannez le QR code</h3>
                <p class="text-sm text-gray-400 mb-4">
                  Utilisez une application comme Google Authenticator, Authy ou 1Password
                </p>
                <div class="flex justify-center bg-white p-4 rounded-lg">
                  <img :src="qrCode" alt="QR Code TOTP" class="w-48 h-48" />
                </div>
              </div>

              <div class="bg-gray-900 rounded-lg p-4">
                <h3 class="text-sm font-medium text-white mb-2">Ou entrez le code manuellement</h3>
                <div class="flex items-center space-x-2">
                  <code class="flex-1 bg-gray-700 px-3 py-2 rounded text-sm text-gray-300 font-mono">
                    {{ secret }}
                  </code>
                  <button
                    @click="copyToClipboard(secret)"
                    class="p-2 text-gray-400 hover:text-white"
                    title="Copier"
                  >
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </button>
                </div>
              </div>

              <div class="bg-gray-900 rounded-lg p-4">
                <h3 class="text-sm font-medium text-white mb-2">2. Sauvegardez vos codes de secours</h3>
                <p class="text-sm text-gray-400 mb-4">
                  Ces codes vous permettront de vous connecter si vous perdez votre téléphone
                </p>
                <div class="grid grid-cols-2 gap-2 mb-4">
                  <code
                    v-for="code in backupCodes"
                    :key="code"
                    class="bg-gray-700 px-3 py-2 rounded text-sm text-gray-300 font-mono text-center"
                  >
                    {{ code }}
                  </code>
                </div>
                <button
                  @click="copyAllBackupCodes(backupCodes)"
                  class="w-full px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-300 hover:bg-gray-700"
                >
                  Copier tous les codes
                </button>
              </div>

              <div class="bg-gray-900 rounded-lg p-4">
                <h3 class="text-sm font-medium text-white mb-2">3. Vérifiez votre configuration</h3>
                <p class="text-sm text-gray-400 mb-4">
                  Entrez un code généré par votre application pour confirmer
                </p>
                <input
                  v-model="verifyCode"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  placeholder="000000"
                  class="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-md
                         text-white text-center text-xl tracking-widest
                         focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div class="flex space-x-4">
                <button
                  @click="cancelSetup"
                  class="flex-1 px-4 py-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700"
                >
                  Annuler
                </button>
                <button
                  @click="verifyAndEnable"
                  :disabled="loading || verifyCode.length < 6"
                  class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md
                         disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {{ loading ? 'Vérification...' : 'Activer le 2FA' }}
                </button>
              </div>
            </div>
          </template>

          <!-- Done step - Success -->
          <template v-else-if="setupStep === 'done'">
            <div class="text-center py-6">
              <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-900/50 mb-4">
                <svg class="h-6 w-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 class="text-lg font-medium text-white mb-2">2FA activé!</h3>
              <p class="text-gray-400 mb-6">
                Votre compte est maintenant protégé par l'authentification à deux facteurs
              </p>
              <button
                @click="finishSetup"
                class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md"
              >
                Terminé
              </button>
            </div>
          </template>

          <!-- Enabled - show manage options -->
          <template v-else-if="is2FAEnabled">
            <div class="space-y-4">
              <button
                @click="showRegenerateModal = true"
                class="w-full text-left px-4 py-3 bg-gray-900 rounded-lg flex items-center justify-between
                       hover:bg-gray-700 transition-colors"
              >
                <div class="flex items-center">
                  <svg class="w-5 h-5 text-gray-400 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <div>
                    <p class="text-white font-medium">Régénérer les codes de secours</p>
                    <p class="text-sm text-gray-400">Créer de nouveaux codes de secours</p>
                  </div>
                </div>
                <svg class="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </button>

              <button
                @click="showDisableModal = true"
                class="w-full text-left px-4 py-3 bg-gray-900 rounded-lg flex items-center justify-between
                       hover:bg-red-900/30 transition-colors group"
              >
                <div class="flex items-center">
                  <svg class="w-5 h-5 text-red-400 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                  </svg>
                  <div>
                    <p class="text-white font-medium">Désactiver le 2FA</p>
                    <p class="text-sm text-gray-400">Supprimer l'authentification à deux facteurs</p>
                  </div>
                </div>
                <svg class="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </template>
        </div>
      </div>

      <!-- Password Section -->
      <div class="bg-gray-800 rounded-lg p-6">
        <div class="flex items-start justify-between">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center">
                <svg class="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <h2 class="text-lg font-medium text-white">Mot de passe</h2>
              <p class="text-sm text-gray-400">Modifiez votre mot de passe</p>
            </div>
          </div>
        </div>
        <div class="mt-6">
          <button
            @click="showPasswordModal = true"
            class="px-4 py-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700"
          >
            Changer le mot de passe
          </button>
        </div>
      </div>
    </div>

    <!-- Modal: Disable 2FA -->
    <div
      v-if="showDisableModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="showDisableModal = false"
    >
      <div class="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-medium text-white mb-4">Désactiver le 2FA</h3>
        <p class="text-gray-400 mb-4">
          Entrez votre mot de passe pour confirmer la désactivation du 2FA
        </p>
        <input
          v-model="disablePassword"
          type="password"
          placeholder="Mot de passe"
          class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-md
                 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div class="mt-6 flex space-x-4">
          <button
            @click="showDisableModal = false; disablePassword = ''"
            class="flex-1 px-4 py-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700"
          >
            Annuler
          </button>
          <button
            @click="disable2FA"
            :disabled="loading"
            class="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ loading ? 'Désactivation...' : 'Désactiver' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal: Regenerate backup codes -->
    <div
      v-if="showRegenerateModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="closeRegenerateModal"
    >
      <div class="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <template v-if="newBackupCodes.length === 0">
          <h3 class="text-lg font-medium text-white mb-4">Régénérer les codes de secours</h3>
          <p class="text-gray-400 mb-4">
            Entrez un code TOTP pour confirmer. Les anciens codes seront invalidés.
          </p>
          <input
            v-model="regenerateCode"
            type="text"
            inputmode="numeric"
            maxlength="6"
            placeholder="000000"
            class="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-md
                   text-white text-center text-xl tracking-widest
                   focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div class="mt-6 flex space-x-4">
            <button
              @click="closeRegenerateModal"
              class="flex-1 px-4 py-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700"
            >
              Annuler
            </button>
            <button
              @click="regenerateBackupCodes"
              :disabled="loading || regenerateCode.length < 6"
              class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md
                     disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ loading ? 'Génération...' : 'Régénérer' }}
            </button>
          </div>
        </template>
        <template v-else>
          <h3 class="text-lg font-medium text-white mb-4">Nouveaux codes de secours</h3>
          <p class="text-gray-400 mb-4">
            Sauvegardez ces codes dans un endroit sûr
          </p>
          <div class="grid grid-cols-2 gap-2 mb-4">
            <code
              v-for="code in newBackupCodes"
              :key="code"
              class="bg-gray-700 px-3 py-2 rounded text-sm text-gray-300 font-mono text-center"
            >
              {{ code }}
            </code>
          </div>
          <button
            @click="copyAllBackupCodes(newBackupCodes)"
            class="w-full px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-300 hover:bg-gray-700 mb-4"
          >
            Copier tous les codes
          </button>
          <button
            @click="closeRegenerateModal"
            class="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md"
          >
            Terminé
          </button>
        </template>
      </div>
    </div>

    <!-- Modal: Change password -->
    <div
      v-if="showPasswordModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="showPasswordModal = false"
    >
      <div class="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-medium text-white mb-4">Changer le mot de passe</h3>
        <div class="space-y-4">
          <input
            v-model="currentPassword"
            type="password"
            placeholder="Mot de passe actuel"
            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-md
                   text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            v-model="newPassword"
            type="password"
            placeholder="Nouveau mot de passe"
            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-md
                   text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            v-model="confirmPassword"
            type="password"
            placeholder="Confirmer le nouveau mot de passe"
            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-md
                   text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div class="mt-6 flex space-x-4">
          <button
            @click="showPasswordModal = false; currentPassword = ''; newPassword = ''; confirmPassword = ''"
            class="flex-1 px-4 py-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700"
          >
            Annuler
          </button>
          <button
            @click="changePassword"
            :disabled="loading"
            class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ loading ? 'Modification...' : 'Modifier' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
