<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppLogo from '../components/AppLogo.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const showUserMenu = ref(false)

const currentPath = computed(() => route.path)

const navItems = computed(() => {
  const items = [
    { path: '/graph', name: 'Graphe', icon: 'graph' },
    { path: '/inventory', name: 'Inventaire', icon: 'inventory' },
    { path: '/logs', name: 'Logs', icon: 'logs' },
    { path: '/metrics', name: 'Metriques', icon: 'metrics' }
  ]

  // Ajouter Parametres pour admin/operator ou si auth desactivee
  if (!authStore.authEnabled || authStore.isOperator) {
    items.push({ path: '/settings', name: 'Parametres', icon: 'settings' })
  }

  return items
})

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

function closeUserMenu() {
  showUserMenu.value = false
}
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-900">
    <!-- Navigation bar -->
    <nav class="flex items-center justify-between bg-gray-800 border-b border-gray-700 px-4">
      <!-- Left: Logo + Navigation tabs -->
      <div class="flex items-center">
        <!-- Logo -->
        <div class="flex items-center mr-6 py-3">
          <AppLogo size="sm" />
        </div>

        <!-- Navigation tabs -->
        <div class="flex">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="px-4 py-3 text-sm font-medium transition-colors border-b-2"
            :class="currentPath === item.path || currentPath.startsWith(item.path + '/')
              ? 'text-white bg-gray-900 border-blue-500'
              : 'text-gray-400 hover:text-white hover:bg-gray-700 border-transparent'"
          >
            {{ item.name }}
          </router-link>
        </div>
      </div>

      <!-- Right: User menu -->
      <div v-if="authStore.isAuthenticated" class="relative">
        <button
          @click="showUserMenu = !showUserMenu"
          class="flex items-center space-x-2 px-3 py-2 rounded-md text-gray-300 hover:text-white hover:bg-gray-700"
        >
          <!-- Avatar placeholder -->
          <div class="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center">
            <span class="text-sm font-medium text-white">
              {{ authStore.userDisplayName.charAt(0).toUpperCase() }}
            </span>
          </div>
          <span class="hidden md:block text-sm">{{ authStore.userDisplayName }}</span>
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <!-- Dropdown menu -->
        <div
          v-if="showUserMenu"
          class="absolute right-0 mt-2 w-56 bg-gray-800 rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-50"
          @click.stop
        >
          <div class="py-1">
            <!-- User info -->
            <div class="px-4 py-3 border-b border-gray-700">
              <p class="text-sm font-medium text-white">{{ authStore.userDisplayName }}</p>
              <p class="text-xs text-gray-400">{{ authStore.user?.email }}</p>
              <span class="inline-block mt-1 px-2 py-0.5 text-xs rounded-full"
                    :class="{
                      'bg-purple-900 text-purple-300': authStore.user?.role === 'super_admin',
                      'bg-red-900 text-red-300': authStore.user?.role === 'admin',
                      'bg-blue-900 text-blue-300': authStore.user?.role === 'operator',
                      'bg-gray-600 text-gray-300': authStore.user?.role === 'viewer'
                    }">
                {{ authStore.user?.role }}
              </span>
            </div>

            <!-- Actions -->
            <router-link
              v-if="!authStore.user?.is_sso"
              to="/security"
              @click="closeUserMenu"
              class="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white flex items-center"
            >
              <svg class="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Sécurité
              <span
                v-if="authStore.user?.totp_enabled"
                class="ml-auto text-xs bg-green-900 text-green-300 px-1.5 py-0.5 rounded"
              >
                2FA
              </span>
            </router-link>

            <button
              @click="handleLogout(); closeUserMenu()"
              class="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white flex items-center"
            >
              <svg class="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              Déconnexion
            </button>
          </div>
        </div>

        <!-- Backdrop pour fermer le menu -->
        <div
          v-if="showUserMenu"
          class="fixed inset-0 z-40"
          @click="closeUserMenu"
        ></div>
      </div>
    </nav>

    <!-- Main content -->
    <div class="flex-1 overflow-hidden">
      <router-view />
    </div>
  </div>
</template>
