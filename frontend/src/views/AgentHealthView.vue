<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// State
const healthSummary = ref(null)
const selectedAgent = ref(null)
const agentDetail = ref(null)
const loading = ref(false)
const checking = ref(false)
const autoRefresh = ref(true)
const refreshInterval = ref(30)

let refreshTimer = null

// Fetch health summary
async function fetchHealthSummary() {
  loading.value = true
  try {
    const response = await fetch('/api/v1/agents/health/summary')
    if (!response.ok) throw new Error('Erreur chargement')
    healthSummary.value = await response.json()
  } catch (error) {
    console.error('Erreur chargement sante agents:', error)
  } finally {
    loading.value = false
  }
}

// Fetch agent detail
async function fetchAgentDetail(hostId) {
  try {
    const response = await fetch(`/api/v1/agents/health/${hostId}`)
    if (!response.ok) throw new Error('Erreur chargement')
    agentDetail.value = await response.json()
  } catch (error) {
    console.error('Erreur chargement detail agent:', error)
  }
}

// Run health check
async function runHealthCheck() {
  checking.value = true
  try {
    const response = await fetch('/api/v1/agents/health/check', { method: 'POST' })
    if (!response.ok) throw new Error('Erreur check')
    await fetchHealthSummary()
  } catch (error) {
    console.error('Erreur check sante:', error)
  } finally {
    checking.value = false
  }
}

// Reset agent stats
async function resetAgentStats(hostId) {
  if (!confirm('Reinitialiser les statistiques de cet agent ?')) return

  try {
    const response = await fetch(`/api/v1/agents/health/${hostId}/reset`, { method: 'POST' })
    if (!response.ok) throw new Error('Erreur reset')
    await fetchHealthSummary()
    if (selectedAgent.value === hostId) {
      await fetchAgentDetail(hostId)
    }
  } catch (error) {
    console.error('Erreur reset stats:', error)
  }
}

// Select agent
function selectAgent(hostId) {
  selectedAgent.value = hostId
  fetchAgentDetail(hostId)
}

// Close detail panel
function closeDetail() {
  selectedAgent.value = null
  agentDetail.value = null
}

// Format uptime
function formatUptime(seconds) {
  if (!seconds) return '-'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)

  if (days > 0) return `${days}j ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

// Format duration
function formatDuration(ms) {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

// Format relative time
function formatRelativeTime(seconds) {
  if (!seconds && seconds !== 0) return '-'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}j`
}

// Get status color
function getStatusColor(status) {
  switch (status) {
    case 'healthy': return 'text-green-400'
    case 'degraded': return 'text-yellow-400'
    case 'unhealthy': return 'text-red-400'
    default: return 'text-gray-400'
  }
}

// Get status bg color
function getStatusBgColor(status) {
  switch (status) {
    case 'healthy': return 'bg-green-900/30 border-green-700'
    case 'degraded': return 'bg-yellow-900/30 border-yellow-700'
    case 'unhealthy': return 'bg-red-900/30 border-red-700'
    default: return 'bg-gray-800 border-gray-700'
  }
}

// Get status badge
function getStatusBadge(status) {
  switch (status) {
    case 'healthy': return 'bg-green-500'
    case 'degraded': return 'bg-yellow-500'
    case 'unhealthy': return 'bg-red-500'
    default: return 'bg-gray-500'
  }
}

// Get status label
function getStatusLabel(status) {
  switch (status) {
    case 'healthy': return 'Sain'
    case 'degraded': return 'Degrade'
    case 'unhealthy': return 'Hors ligne'
    default: return 'Inconnu'
  }
}

// Start auto-refresh
function startAutoRefresh() {
  stopAutoRefresh()
  if (autoRefresh.value) {
    refreshTimer = setInterval(fetchHealthSummary, refreshInterval.value * 1000)
  }
}

// Stop auto-refresh
function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// Initial load
onMounted(() => {
  fetchHealthSummary()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})

// Computed: all agents flattened
const allAgents = computed(() => {
  if (!healthSummary.value?.by_status) return []
  const agents = []
  for (const status of ['healthy', 'degraded', 'unhealthy', 'unknown']) {
    const statusAgents = healthSummary.value.by_status[status] || []
    agents.push(...statusAgents)
  }
  return agents
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white">
    <!-- Header -->
    <div class="p-4 border-b border-gray-700">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-xl font-semibold">Sante des Agents</h1>

        <div class="flex items-center gap-3">
          <!-- Auto-refresh -->
          <label class="flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              v-model="autoRefresh"
              @change="startAutoRefresh"
              class="w-4 h-4"
            />
            Auto ({{ refreshInterval }}s)
          </label>

          <!-- Health check button -->
          <button
            @click="runHealthCheck"
            :disabled="checking"
            class="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 rounded text-sm font-medium disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="checking" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Verifier
          </button>

          <!-- Refresh button -->
          <button
            @click="fetchHealthSummary"
            :disabled="loading"
            class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium disabled:opacity-50"
          >
            Rafraichir
          </button>
        </div>
      </div>

      <!-- Stats cards -->
      <div v-if="healthSummary" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <div class="bg-gray-800 rounded-lg p-3 border border-gray-700">
          <p class="text-xs text-gray-400 mb-1">Total</p>
          <p class="text-2xl font-bold">{{ healthSummary.total }}</p>
        </div>
        <div class="bg-green-900/30 rounded-lg p-3 border border-green-700">
          <p class="text-xs text-green-400 mb-1">Sains</p>
          <p class="text-2xl font-bold text-green-400">{{ healthSummary.stats?.healthy || 0 }}</p>
        </div>
        <div class="bg-yellow-900/30 rounded-lg p-3 border border-yellow-700">
          <p class="text-xs text-yellow-400 mb-1">Degrades</p>
          <p class="text-2xl font-bold text-yellow-400">{{ healthSummary.stats?.degraded || 0 }}</p>
        </div>
        <div class="bg-red-900/30 rounded-lg p-3 border border-red-700">
          <p class="text-xs text-red-400 mb-1">Hors ligne</p>
          <p class="text-2xl font-bold text-red-400">{{ healthSummary.stats?.unhealthy || 0 }}</p>
        </div>
        <div class="bg-gray-800 rounded-lg p-3 border border-gray-700">
          <p class="text-xs text-gray-400 mb-1">En ligne</p>
          <p class="text-2xl font-bold text-blue-400">{{ healthSummary.stats?.online || 0 }}</p>
        </div>
        <div class="bg-gray-800 rounded-lg p-3 border border-gray-700">
          <p class="text-xs text-gray-400 mb-1">Inconnus</p>
          <p class="text-2xl font-bold text-gray-400">{{ healthSummary.stats?.unknown || 0 }}</p>
        </div>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden flex">
      <!-- Agent list -->
      <div class="flex-1 overflow-auto p-4">
        <!-- Loading -->
        <div v-if="loading && !healthSummary" class="flex items-center justify-center py-12">
          <div class="flex items-center gap-3 text-gray-400">
            <svg class="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Chargement...
          </div>
        </div>

        <!-- Agents with errors -->
        <div v-if="healthSummary?.agents_with_errors?.length > 0" class="mb-6">
          <h2 class="text-lg font-medium mb-3 flex items-center gap-2">
            <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Agents avec erreurs recentes
          </h2>
          <div class="grid gap-3">
            <div
              v-for="agent in healthSummary.agents_with_errors"
              :key="agent.host_id"
              @click="selectAgent(agent.host_id)"
              class="bg-red-900/20 rounded-lg p-4 border border-red-700 cursor-pointer hover:bg-red-900/30"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <div class="w-3 h-3 rounded-full" :class="getStatusBadge(agent.agent_health)"></div>
                  <div>
                    <h3 class="font-medium">{{ agent.hostname }}</h3>
                    <p class="text-sm text-gray-400">{{ agent.last_error }}</p>
                  </div>
                </div>
                <span class="text-xs text-gray-500">{{ agent.last_error_at }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Slowest agents -->
        <div v-if="healthSummary?.slowest_agents?.length > 0" class="mb-6">
          <h2 class="text-lg font-medium mb-3 flex items-center gap-2">
            <svg class="w-5 h-5 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Agents les plus lents
          </h2>
          <div class="grid gap-2">
            <div
              v-for="agent in healthSummary.slowest_agents"
              :key="agent.host_id"
              @click="selectAgent(agent.host_id)"
              class="bg-gray-800 rounded-lg p-3 border border-gray-700 cursor-pointer hover:bg-gray-700 flex items-center justify-between"
            >
              <div class="flex items-center gap-3">
                <div class="w-3 h-3 rounded-full" :class="getStatusBadge(agent.agent_health)"></div>
                <span>{{ agent.hostname }}</span>
              </div>
              <span class="text-yellow-400 font-mono text-sm">
                {{ formatDuration(agent.avg_report_duration_ms) }}
              </span>
            </div>
          </div>
        </div>

        <!-- All agents by status -->
        <div>
          <h2 class="text-lg font-medium mb-3">Tous les agents</h2>

          <!-- Empty state -->
          <div v-if="allAgents.length === 0 && !loading" class="text-center py-12 text-gray-500">
            <svg class="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
            </svg>
            <p>Aucun agent enregistre</p>
          </div>

          <!-- Agent cards -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div
              v-for="agent in allAgents"
              :key="agent.host_id"
              @click="selectAgent(agent.host_id)"
              :class="[
                'rounded-lg p-4 border cursor-pointer transition-colors',
                getStatusBgColor(agent.agent_health),
                selectedAgent === agent.host_id ? 'ring-2 ring-blue-500' : 'hover:brightness-110'
              ]"
            >
              <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full" :class="getStatusBadge(agent.agent_health)"></div>
                  <h3 class="font-medium">{{ agent.hostname }}</h3>
                </div>
                <span :class="['text-xs px-2 py-0.5 rounded', getStatusColor(agent.agent_health)]">
                  {{ getStatusLabel(agent.agent_health) }}
                </span>
              </div>

              <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <div>
                  <span class="text-gray-400">Version:</span>
                  <span class="ml-2">{{ agent.agent_version || '-' }}</span>
                </div>
                <div>
                  <span class="text-gray-400">Uptime:</span>
                  <span class="ml-2">{{ formatUptime(agent.uptime_seconds) }}</span>
                </div>
                <div>
                  <span class="text-gray-400">Dernier rapport:</span>
                  <span class="ml-2">{{ formatRelativeTime(agent.seconds_since_last_report) }}</span>
                </div>
                <div>
                  <span class="text-gray-400">Intervalle:</span>
                  <span class="ml-2">{{ agent.report_interval }}s</span>
                </div>
              </div>

              <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
                <span>{{ agent.reports_count }} rapports</span>
                <span v-if="agent.errors_count > 0" class="text-red-400">
                  {{ agent.errors_count }} erreurs
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Detail panel -->
      <div
        v-if="selectedAgent && agentDetail"
        class="w-96 border-l border-gray-700 bg-gray-800 overflow-auto"
      >
        <div class="p-4">
          <!-- Header -->
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold">Details</h2>
            <button
              @click="closeDetail"
              class="p-1 hover:bg-gray-700 rounded"
            >
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Agent info -->
          <div class="space-y-4">
            <!-- Status -->
            <div class="flex items-center gap-3">
              <div class="w-4 h-4 rounded-full" :class="getStatusBadge(agentDetail.agent_health)"></div>
              <div>
                <h3 class="font-medium">{{ agentDetail.hostname }}</h3>
                <p :class="['text-sm', getStatusColor(agentDetail.agent_health)]">
                  {{ getStatusLabel(agentDetail.agent_health) }}
                </p>
              </div>
            </div>

            <!-- Info grid -->
            <div class="bg-gray-900 rounded-lg p-3 space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-400">Host ID</span>
                <span class="font-mono text-xs">{{ agentDetail.host_id.slice(0, 12) }}...</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Version</span>
                <span>{{ agentDetail.agent_version || '-' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">OS</span>
                <span>{{ agentDetail.os_info || '-' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Docker</span>
                <span>{{ agentDetail.docker_version || '-' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Tailscale IP</span>
                <span>{{ agentDetail.tailscale_ip || '-' }}</span>
              </div>
            </div>

            <!-- Timing -->
            <div class="bg-gray-900 rounded-lg p-3 space-y-2 text-sm">
              <h4 class="font-medium text-gray-300 mb-2">Timing</h4>
              <div class="flex justify-between">
                <span class="text-gray-400">Uptime</span>
                <span>{{ formatUptime(agentDetail.uptime_seconds) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Intervalle rapport</span>
                <span>{{ agentDetail.report_interval }}s</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Dernier rapport</span>
                <span>{{ formatRelativeTime(agentDetail.seconds_since_last_report) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Duree dernier rapport</span>
                <span>{{ formatDuration(agentDetail.last_report_duration_ms) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Duree moyenne</span>
                <span>{{ formatDuration(agentDetail.avg_report_duration_ms) }}</span>
              </div>
            </div>

            <!-- Stats -->
            <div class="bg-gray-900 rounded-lg p-3 space-y-2 text-sm">
              <h4 class="font-medium text-gray-300 mb-2">Statistiques</h4>
              <div class="flex justify-between">
                <span class="text-gray-400">Rapports recus</span>
                <span class="text-green-400">{{ agentDetail.reports_count }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Erreurs totales</span>
                <span class="text-red-400">{{ agentDetail.errors_count }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Echecs consecutifs</span>
                <span :class="agentDetail.consecutive_failures > 0 ? 'text-yellow-400' : ''">
                  {{ agentDetail.consecutive_failures }}
                </span>
              </div>
            </div>

            <!-- Last error -->
            <div v-if="agentDetail.last_error" class="bg-red-900/30 rounded-lg p-3 border border-red-700">
              <h4 class="font-medium text-red-400 mb-2">Derniere erreur</h4>
              <p class="text-sm text-gray-300 break-words">{{ agentDetail.last_error }}</p>
              <p class="text-xs text-gray-500 mt-2">{{ agentDetail.last_error_at }}</p>
            </div>

            <!-- Timestamps -->
            <div class="bg-gray-900 rounded-lg p-3 space-y-2 text-sm">
              <h4 class="font-medium text-gray-300 mb-2">Dates</h4>
              <div class="flex justify-between">
                <span class="text-gray-400">Premier contact</span>
                <span class="text-xs">{{ agentDetail.first_seen }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-400">Dernier contact</span>
                <span class="text-xs">{{ agentDetail.last_seen }}</span>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex gap-2 pt-2">
              <button
                @click="resetAgentStats(agentDetail.host_id)"
                class="flex-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
              >
                Reinitialiser stats
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
