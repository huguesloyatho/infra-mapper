<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'

const authStore = useAuthStore()

onMounted(async () => {
  // Initialiser l'authentification au démarrage
  await authStore.initialize()
})
</script>

<template>
  <!-- Loading initial -->
  <div v-if="!authStore.initialized" class="h-screen flex items-center justify-center bg-gray-900">
    <div class="text-center">
      <svg class="animate-spin h-10 w-10 text-blue-500 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <p class="text-gray-400">Chargement...</p>
    </div>
  </div>

  <!-- Application -->
  <router-view v-else />
</template>
