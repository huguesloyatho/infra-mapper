<script setup>
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const status = ref('processing') // processing, success, error
const errorMessage = ref('')

onMounted(async () => {
  const code = route.query.code
  const state = route.query.state
  const error = route.query.error

  // Erreur de l'IdP
  if (error) {
    status.value = 'error'
    errorMessage.value = route.query.error_description || 'Authentification refusée'
    return
  }

  // Paramètres manquants
  if (!code || !state) {
    status.value = 'error'
    errorMessage.value = 'Paramètres de callback invalides'
    return
  }

  // Récupérer le provider depuis sessionStorage
  const providerId = sessionStorage.getItem('sso_provider')
  if (!providerId) {
    status.value = 'error'
    errorMessage.value = 'Session SSO invalide'
    return
  }

  try {
    await authStore.handleSSOCallback(code, state, providerId)
    status.value = 'success'

    // Redirect vers la page demandée ou home
    const redirect = sessionStorage.getItem('redirect_after_login') || '/graph'
    sessionStorage.removeItem('redirect_after_login')

    // Petit délai pour montrer le succès
    setTimeout(() => {
      router.push(redirect)
    }, 500)
  } catch (e) {
    status.value = 'error'
    errorMessage.value = e.message || 'Erreur d\'authentification SSO'
  }
})

function goToLogin() {
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-900 px-4">
    <div class="max-w-md w-full text-center">
      <!-- Processing -->
      <div v-if="status === 'processing'" class="space-y-4">
        <svg class="animate-spin h-12 w-12 text-blue-500 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <p class="text-gray-300 text-lg">Authentification en cours...</p>
      </div>

      <!-- Success -->
      <div v-else-if="status === 'success'" class="space-y-4">
        <svg class="h-12 w-12 text-green-500 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <p class="text-gray-300 text-lg">Connexion réussie !</p>
        <p class="text-gray-400 text-sm">Redirection en cours...</p>
      </div>

      <!-- Error -->
      <div v-else-if="status === 'error'" class="space-y-6">
        <svg class="h-12 w-12 text-red-500 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        <div class="bg-gray-800 p-6 rounded-lg">
          <p class="text-red-400 text-lg font-medium">Erreur d'authentification</p>
          <p class="text-gray-400 mt-2">{{ errorMessage }}</p>
        </div>
        <button
          @click="goToLogin"
          class="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700
                 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Retour à la page de connexion
        </button>
      </div>
    </div>
  </div>
</template>
