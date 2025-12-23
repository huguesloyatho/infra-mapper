<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const tabs = computed(() => {
  const items = []

  // VMs - admin/operator
  if (!authStore.authEnabled || authStore.isOperator) {
    items.push({
      path: '/settings/vms',
      name: 'Gestion VMs / Agents',
      icon: 'server'
    })
  }

  // Alerts - admin/operator
  if (!authStore.authEnabled || authStore.isOperator) {
    items.push({
      path: '/settings/alerts',
      name: 'Alertes',
      icon: 'bell'
    })
  }

  // Log Sinks - admin/operator
  if (!authStore.authEnabled || authStore.isOperator) {
    items.push({
      path: '/settings/log-sinks',
      name: 'Puits de Logs',
      icon: 'upload'
    })
  }

  // Agent Health - admin/operator
  if (!authStore.authEnabled || authStore.isOperator) {
    items.push({
      path: '/settings/agent-health',
      name: 'Sante Agents',
      icon: 'heart'
    })
  }

  // Admin only tabs
  if (!authStore.authEnabled || authStore.isAdmin) {
    items.push(
      { path: '/settings/users', name: 'Utilisateurs', icon: 'users' },
      { path: '/settings/iam', name: 'Fournisseurs d\'identité', icon: 'shield' },
      { path: '/settings/audit', name: 'Logs d\'audit', icon: 'clipboard' },
      { path: '/settings/backups', name: 'Sauvegardes', icon: 'database' }
    )
  }

  // Super admin only - Organizations
  if (authStore.isSuperAdmin) {
    items.push(
      { path: '/settings/organizations', name: 'Organisations', icon: 'building' }
    )
  }

  return items
})

const currentPath = computed(() => route.path)
</script>

<template>
  <div class="h-full flex">
    <!-- Sidebar navigation -->
    <div class="w-64 bg-gray-800 border-r border-gray-700 flex-shrink-0">
      <div class="p-4">
        <h2 class="text-lg font-semibold text-white mb-4">Param\u00e8tres</h2>
        <nav class="space-y-1">
          <router-link
            v-for="tab in tabs"
            :key="tab.path"
            :to="tab.path"
            class="flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors"
            :class="currentPath === tab.path || currentPath.startsWith(tab.path + '/')
              ? 'bg-gray-900 text-white'
              : 'text-gray-300 hover:bg-gray-700 hover:text-white'"
          >
            <!-- Server icon -->
            <svg v-if="tab.icon === 'server'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
            </svg>
            <!-- Users icon -->
            <svg v-else-if="tab.icon === 'users'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <!-- Shield icon -->
            <svg v-else-if="tab.icon === 'shield'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <!-- Clipboard icon -->
            <svg v-else-if="tab.icon === 'clipboard'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
            <!-- Bell icon -->
            <svg v-else-if="tab.icon === 'bell'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <!-- Database icon -->
            <svg v-else-if="tab.icon === 'database'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            <!-- Upload icon -->
            <svg v-else-if="tab.icon === 'upload'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <!-- Heart icon -->
            <svg v-else-if="tab.icon === 'heart'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
            <!-- Building icon -->
            <svg v-else-if="tab.icon === 'building'" class="w-5 h-5 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            {{ tab.name }}
          </router-link>
        </nav>
      </div>
    </div>

    <!-- Content area -->
    <div class="flex-1 overflow-hidden">
      <router-view />
    </div>
  </div>
</template>
