<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppLogo from '../components/AppLogo.vue'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const totpCode = ref('')
const showPassword = ref(false)
const localError = ref('')
const isLoggingIn = ref(false)

// Étape du login (credentials ou 2fa)
const step = computed(() => authStore.requires2FA ? '2fa' : 'credentials')

async function handleLogin() {
  if (!username.value || !password.value) {
    localError.value = 'Veuillez remplir tous les champs'
    return
  }

  isLoggingIn.value = true
  localError.value = ''

  try {
    const result = await authStore.login(username.value, password.value)

    // Si 2FA requis, on reste sur la page (l'UI changera)
    if (result.requires2FA) {
      // Focus sur le champ TOTP
      setTimeout(() => document.getElementById('totp-code')?.focus(), 100)
      return
    }

    // Pas de 2FA, redirect
    redirectAfterLogin()
  } catch (e) {
    localError.value = e.message || 'Erreur de connexion'
  } finally {
    isLoggingIn.value = false
  }
}

async function handleVerify2FA() {
  if (!totpCode.value || totpCode.value.length < 6) {
    localError.value = 'Veuillez entrer un code à 6 chiffres'
    return
  }

  isLoggingIn.value = true
  localError.value = ''

  try {
    await authStore.verify2FA(totpCode.value)
    redirectAfterLogin()
  } catch (e) {
    localError.value = e.message || 'Code invalide'
    totpCode.value = ''
  } finally {
    isLoggingIn.value = false
  }
}

function handleCancel2FA() {
  authStore.cancel2FA()
  totpCode.value = ''
  password.value = ''
  localError.value = ''
}

function redirectAfterLogin() {
  const redirect = sessionStorage.getItem('redirect_after_login') || '/graph'
  sessionStorage.removeItem('redirect_after_login')
  router.push(redirect)
}

async function handleSSOLogin(providerId) {
  try {
    await authStore.loginWithSSO(providerId)
  } catch (e) {
    localError.value = e.message || 'Erreur SSO'
  }
}

onMounted(() => {
  // Focus sur le champ username
  document.getElementById('username')?.focus()
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-900 px-4">
    <div class="max-w-md w-full space-y-8">
      <!-- Logo / Titre -->
      <div class="flex flex-col items-center">
        <AppLogo size="lg" />
        <p class="mt-4 text-gray-400">
          {{ step === '2fa' ? 'Vérification en deux étapes' : 'Connectez-vous pour continuer' }}
        </p>
      </div>

      <!-- Formulaire Login -->
      <form
        v-if="step === 'credentials'"
        @submit.prevent="handleLogin"
        class="mt-8 space-y-6 bg-gray-800 p-8 rounded-lg shadow-xl"
      >
        <!-- Erreur -->
        <div
          v-if="localError || authStore.error"
          class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded"
        >
          {{ localError || authStore.error }}
        </div>

        <!-- Username -->
        <div>
          <label for="username" class="block text-sm font-medium text-gray-300">
            Nom d'utilisateur
          </label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            required
            class="mt-1 block w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md
                   text-white placeholder-gray-400
                   focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="admin"
            :disabled="isLoggingIn"
          />
        </div>

        <!-- Password -->
        <div>
          <label for="password" class="block text-sm font-medium text-gray-300">
            Mot de passe
          </label>
          <div class="relative mt-1">
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              required
              class="block w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md
                     text-white placeholder-gray-400
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="********"
              :disabled="isLoggingIn"
            />
            <button
              type="button"
              @click="showPassword = !showPassword"
              class="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-white"
            >
              <svg v-if="!showPassword" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <svg v-else class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.542 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Submit -->
        <button
          type="submit"
          :disabled="isLoggingIn"
          class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md
                 shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700
                 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
                 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <svg
            v-if="isLoggingIn"
            class="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          {{ isLoggingIn ? 'Connexion...' : 'Se connecter' }}
        </button>

        <!-- Divider SSO -->
        <div v-if="authStore.providers.length > 0" class="relative">
          <div class="absolute inset-0 flex items-center">
            <div class="w-full border-t border-gray-600"></div>
          </div>
          <div class="relative flex justify-center text-sm">
            <span class="px-2 bg-gray-800 text-gray-400">Ou continuer avec</span>
          </div>
        </div>

        <!-- SSO Buttons -->
        <div v-if="authStore.providers.length > 0" class="space-y-3">
          <button
            v-for="provider in authStore.providers"
            :key="provider.id"
            type="button"
            @click="handleSSOLogin(provider.id)"
            class="w-full flex items-center justify-center px-4 py-2 border border-gray-600
                   rounded-md shadow-sm text-sm font-medium text-gray-300 bg-gray-700
                   hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-gray-500"
          >
            <!-- Icon SSO générique -->
            <svg class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            {{ provider.display_name }}
          </button>
        </div>
      </form>

      <!-- Formulaire 2FA -->
      <form
        v-else
        @submit.prevent="handleVerify2FA"
        class="mt-8 space-y-6 bg-gray-800 p-8 rounded-lg shadow-xl"
      >
        <!-- Erreur -->
        <div
          v-if="localError || authStore.error"
          class="bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded"
        >
          {{ localError || authStore.error }}
        </div>

        <!-- Info -->
        <div class="text-center">
          <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-blue-900/50">
            <svg class="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <p class="mt-4 text-gray-300">
            Entrez le code à 6 chiffres de votre application d'authentification
          </p>
          <p class="mt-1 text-sm text-gray-500">
            Vous pouvez aussi utiliser un code de secours
          </p>
        </div>

        <!-- Code TOTP -->
        <div>
          <label for="totp-code" class="sr-only">Code de vérification</label>
          <input
            id="totp-code"
            v-model="totpCode"
            type="text"
            inputmode="numeric"
            pattern="[0-9A-Za-z\-]*"
            maxlength="10"
            autocomplete="one-time-code"
            required
            class="block w-full px-3 py-3 bg-gray-700 border border-gray-600 rounded-md
                   text-white text-center text-2xl tracking-widest placeholder-gray-400
                   focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="000000"
            :disabled="isLoggingIn"
          />
        </div>

        <!-- Boutons -->
        <div class="space-y-3">
          <button
            type="submit"
            :disabled="isLoggingIn"
            class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md
                   shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700
                   focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg
              v-if="isLoggingIn"
              class="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            {{ isLoggingIn ? 'Vérification...' : 'Vérifier' }}
          </button>

          <button
            type="button"
            @click="handleCancel2FA"
            class="w-full flex justify-center py-2 px-4 border border-gray-600 rounded-md
                   shadow-sm text-sm font-medium text-gray-300 bg-transparent
                   hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-gray-500"
          >
            Annuler
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
