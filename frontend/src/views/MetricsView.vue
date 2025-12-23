<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

// State
const hosts = ref([])
const selectedHost = ref('')
const metrics = ref([])
const currentMetrics = ref(null)
const summary = ref(null)
const loading = ref(false)
const autoRefresh = ref(true)
const refreshInterval = ref(30)

// Time range
const timeRange = ref('1h')
const timeRanges = [
  { value: '15m', label: '15 min' },
  { value: '1h', label: '1 heure' },
  { value: '6h', label: '6 heures' },
  { value: '24h', label: '24 heures' },
  { value: '7d', label: '7 jours' }
]

let refreshTimer = null

// Compute time range in hours
function getHoursFromRange(range) {
  const map = { '15m': 0.25, '1h': 1, '6h': 6, '24h': 24, '7d': 168 }
  return map[range] || 1
}

// Fetch all hosts with current metrics
async function fetchHosts() {
  try {
    const response = await authStore.authFetch('/api/v1/metrics/hosts')
    if (!response.ok) throw new Error('Erreur chargement hosts')
    const data = await response.json()
    hosts.value = data.hosts || []
  } catch (error) {
    console.error('Erreur chargement hosts:', error)
  }
}

// Fetch metrics for selected host
async function fetchMetrics() {
  if (!selectedHost.value) {
    metrics.value = []
    currentMetrics.value = null
    summary.value = null
    return
  }

  loading.value = true
  try {
    const hours = getHoursFromRange(timeRange.value)

    // Fetch time-series, latest, and summary in parallel
    const [metricsRes, latestRes, summaryRes] = await Promise.all([
      authStore.authFetch(`/api/v1/metrics/hosts/${selectedHost.value}?hours=${hours}`),
      authStore.authFetch(`/api/v1/metrics/hosts/${selectedHost.value}/latest`),
      authStore.authFetch(`/api/v1/metrics/hosts/${selectedHost.value}/summary?hours=${hours}`)
    ])

    if (metricsRes.ok) {
      const data = await metricsRes.json()
      metrics.value = data.metrics || []
    }
    if (latestRes.ok) {
      currentMetrics.value = await latestRes.json()
    }
    if (summaryRes.ok) {
      summary.value = await summaryRes.json()
    }
  } catch (error) {
    console.error('Erreur chargement metrics:', error)
  } finally {
    loading.value = false
  }
}

// Format bytes to human readable
function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unitIndex = 0
  let value = bytes
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex++
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

// Format percentage
function formatPercent(value) {
  if (value === null || value === undefined) return '-'
  return `${value.toFixed(1)}%`
}

// Get color class based on percentage
function getPercentColor(value) {
  if (value === null || value === undefined) return 'text-gray-400'
  if (value >= 90) return 'text-red-400'
  if (value >= 70) return 'text-yellow-400'
  return 'text-green-400'
}

// Get progress bar color
function getProgressColor(value) {
  if (value === null || value === undefined) return 'bg-gray-600'
  if (value >= 90) return 'bg-red-500'
  if (value >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}

// Format timestamp
function formatTimestamp(ts) {
  if (!ts) return ''
  const date = new Date(ts)
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

// Get host name from ID
function getHostName(hostId) {
  const host = hosts.value.find(h => h.host_id === hostId)
  return host?.hostname || hostId
}

// Start auto-refresh
function startAutoRefresh() {
  stopAutoRefresh()
  if (autoRefresh.value) {
    refreshTimer = setInterval(() => {
      fetchHosts()
      if (selectedHost.value) {
        fetchMetrics()
      }
    }, refreshInterval.value * 1000)
  }
}

// Stop auto-refresh
function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// Watch for changes
watch(selectedHost, fetchMetrics)
watch(timeRange, fetchMetrics)
watch(autoRefresh, startAutoRefresh)

// Initial load
onMounted(() => {
  fetchHosts()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white">
    <!-- Header -->
    <div class="p-4 border-b border-gray-700">
      <h1 class="text-xl font-semibold mb-4">Metriques Infrastructure</h1>

      <!-- Filters -->
      <div class="flex flex-wrap gap-4 items-end">
        <!-- Host selector -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Host</label>
          <select
            v-model="selectedHost"
            class="bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none min-w-[200px]"
          >
            <option value="">Selectionner un host</option>
            <option v-for="host in hosts" :key="host.host_id" :value="host.host_id">
              {{ host.hostname }}
            </option>
          </select>
        </div>

        <!-- Time range -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Periode</label>
          <select
            v-model="timeRange"
            class="bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option v-for="range in timeRanges" :key="range.value" :value="range.value">
              {{ range.label }}
            </option>
          </select>
        </div>

        <!-- Auto-refresh -->
        <div class="flex items-center gap-2">
          <input
            type="checkbox"
            id="autoRefresh"
            v-model="autoRefresh"
            class="w-4 h-4"
          />
          <label for="autoRefresh" class="text-sm text-gray-400">
            Rafraichissement auto ({{ refreshInterval }}s)
          </label>
        </div>

        <!-- Refresh button -->
        <button
          @click="fetchHosts(); fetchMetrics()"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium disabled:opacity-50"
        >
          Rafraichir
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-auto p-4">
      <!-- Overview cards (when no host selected) -->
      <div v-if="!selectedHost" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <div
          v-for="host in hosts"
          :key="host.host_id"
          @click="selectedHost = host.host_id"
          class="bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-700 transition-colors border border-gray-700"
        >
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-medium text-lg">{{ host.hostname }}</h3>
            <span class="text-xs text-gray-500">{{ host.host_id.slice(0, 8) }}...</span>
          </div>

          <!-- CPU -->
          <div class="mb-3">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-400">CPU</span>
              <span :class="getPercentColor(host.cpu_percent)">
                {{ formatPercent(host.cpu_percent) }}
              </span>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                :class="getProgressColor(host.cpu_percent)"
                :style="{ width: `${host.cpu_percent || 0}%` }"
                class="h-full transition-all duration-300"
              ></div>
            </div>
          </div>

          <!-- Memory -->
          <div class="mb-3">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-400">RAM</span>
              <span :class="getPercentColor(host.memory_percent)">
                {{ formatPercent(host.memory_percent) }}
              </span>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                :class="getProgressColor(host.memory_percent)"
                :style="{ width: `${host.memory_percent || 0}%` }"
                class="h-full transition-all duration-300"
              ></div>
            </div>
          </div>

          <!-- Disk -->
          <div>
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-400">Disque</span>
              <span :class="getPercentColor(host.disk_percent)">
                {{ formatPercent(host.disk_percent) }}
              </span>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                :class="getProgressColor(host.disk_percent)"
                :style="{ width: `${host.disk_percent || 0}%` }"
                class="h-full transition-all duration-300"
              ></div>
            </div>
          </div>

          <div v-if="host.timestamp" class="mt-3 text-xs text-gray-500">
            Derniere maj: {{ formatTimestamp(host.timestamp) }}
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="hosts.length === 0" class="col-span-full text-center py-12 text-gray-500">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p>Aucun host avec metriques disponible</p>
          <p class="text-sm mt-2">Les agents doivent envoyer des rapports avec metriques</p>
        </div>
      </div>

      <!-- Host detail view -->
      <div v-else>
        <!-- Back button -->
        <button
          @click="selectedHost = ''"
          class="mb-4 flex items-center gap-2 text-gray-400 hover:text-white"
        >
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
          Retour
        </button>

        <!-- Host title -->
        <h2 class="text-2xl font-bold mb-6">{{ getHostName(selectedHost) }}</h2>

        <!-- Loading -->
        <div v-if="loading && !currentMetrics" class="flex items-center justify-center py-12">
          <div class="flex items-center gap-3 text-gray-400">
            <svg class="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Chargement des metriques...
          </div>
        </div>

        <!-- Current metrics cards -->
        <div v-if="currentMetrics" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <!-- CPU -->
          <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div class="flex items-center gap-3 mb-3">
              <div class="p-2 bg-blue-900/50 rounded-lg">
                <svg class="w-6 h-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
              </div>
              <div>
                <h3 class="text-sm text-gray-400">CPU</h3>
                <p :class="getPercentColor(currentMetrics.cpu_percent)" class="text-2xl font-bold">
                  {{ formatPercent(currentMetrics.cpu_percent) }}
                </p>
              </div>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                :class="getProgressColor(currentMetrics.cpu_percent)"
                :style="{ width: `${currentMetrics.cpu_percent || 0}%` }"
                class="h-full transition-all duration-300"
              ></div>
            </div>
            <div class="mt-2 text-xs text-gray-500">
              {{ currentMetrics.cpu_count }} cores | Load: {{ currentMetrics.load_1m ? (currentMetrics.load_1m / 100).toFixed(2) : '-' }}
            </div>
          </div>

          <!-- Memory -->
          <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div class="flex items-center gap-3 mb-3">
              <div class="p-2 bg-purple-900/50 rounded-lg">
                <svg class="w-6 h-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
              </div>
              <div>
                <h3 class="text-sm text-gray-400">Memoire</h3>
                <p :class="getPercentColor(currentMetrics.memory_percent)" class="text-2xl font-bold">
                  {{ formatPercent(currentMetrics.memory_percent) }}
                </p>
              </div>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                :class="getProgressColor(currentMetrics.memory_percent)"
                :style="{ width: `${currentMetrics.memory_percent || 0}%` }"
                class="h-full transition-all duration-300"
              ></div>
            </div>
            <div class="mt-2 text-xs text-gray-500">
              {{ formatBytes(currentMetrics.memory_used * 1024 * 1024) }} / {{ formatBytes(currentMetrics.memory_total * 1024 * 1024) }}
            </div>
          </div>

          <!-- Disk -->
          <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div class="flex items-center gap-3 mb-3">
              <div class="p-2 bg-green-900/50 rounded-lg">
                <svg class="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                </svg>
              </div>
              <div>
                <h3 class="text-sm text-gray-400">Disque</h3>
                <p :class="getPercentColor(currentMetrics.disk_percent)" class="text-2xl font-bold">
                  {{ formatPercent(currentMetrics.disk_percent) }}
                </p>
              </div>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                :class="getProgressColor(currentMetrics.disk_percent)"
                :style="{ width: `${currentMetrics.disk_percent || 0}%` }"
                class="h-full transition-all duration-300"
              ></div>
            </div>
            <div class="mt-2 text-xs text-gray-500">
              {{ formatBytes(currentMetrics.disk_used * 1024 * 1024) }} / {{ formatBytes(currentMetrics.disk_total * 1024 * 1024) }}
            </div>
          </div>

          <!-- Network -->
          <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div class="flex items-center gap-3 mb-3">
              <div class="p-2 bg-orange-900/50 rounded-lg">
                <svg class="w-6 h-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16l2.879-2.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h3 class="text-sm text-gray-400">Reseau</h3>
                <p class="text-lg font-bold text-orange-400">
                  {{ formatBytes(currentMetrics.network_rx_bytes) }}
                </p>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-xs text-gray-500">
              <div>
                <span class="text-green-400">RX:</span> {{ formatBytes(currentMetrics.network_rx_bytes) }}
              </div>
              <div>
                <span class="text-blue-400">TX:</span> {{ formatBytes(currentMetrics.network_tx_bytes) }}
              </div>
            </div>
          </div>
        </div>

        <!-- Summary stats -->
        <div v-if="summary" class="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
          <h3 class="text-lg font-medium mb-4">Statistiques ({{ timeRanges.find(r => r.value === timeRange)?.label }})</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p class="text-sm text-gray-400">CPU Moyenne</p>
              <p :class="getPercentColor(summary.cpu_avg)" class="text-xl font-bold">{{ formatPercent(summary.cpu_avg) }}</p>
            </div>
            <div>
              <p class="text-sm text-gray-400">CPU Max</p>
              <p :class="getPercentColor(summary.cpu_max)" class="text-xl font-bold">{{ formatPercent(summary.cpu_max) }}</p>
            </div>
            <div>
              <p class="text-sm text-gray-400">RAM Moyenne</p>
              <p :class="getPercentColor(summary.memory_avg)" class="text-xl font-bold">{{ formatPercent(summary.memory_avg) }}</p>
            </div>
            <div>
              <p class="text-sm text-gray-400">RAM Max</p>
              <p :class="getPercentColor(summary.memory_max)" class="text-xl font-bold">{{ formatPercent(summary.memory_max) }}</p>
            </div>
          </div>
          <p class="text-xs text-gray-500 mt-3">
            {{ summary.data_points }} points de donnees
          </p>
        </div>

        <!-- Time series table -->
        <div v-if="metrics.length > 0" class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-700">
            <h3 class="font-medium">Historique</h3>
          </div>
          <div class="overflow-x-auto max-h-96 overflow-y-auto">
            <table class="w-full text-sm">
              <thead class="bg-gray-700 sticky top-0">
                <tr>
                  <th class="px-4 py-2 text-left text-gray-400">Timestamp</th>
                  <th class="px-4 py-2 text-right text-gray-400">CPU</th>
                  <th class="px-4 py-2 text-right text-gray-400">RAM</th>
                  <th class="px-4 py-2 text-right text-gray-400">Disque</th>
                  <th class="px-4 py-2 text-right text-gray-400">Load</th>
                  <th class="px-4 py-2 text-right text-gray-400">RX</th>
                  <th class="px-4 py-2 text-right text-gray-400">TX</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(m, i) in metrics" :key="i" class="border-b border-gray-700 hover:bg-gray-700/50">
                  <td class="px-4 py-2 text-gray-300">{{ new Date(m.timestamp).toLocaleString('fr-FR') }}</td>
                  <td class="px-4 py-2 text-right" :class="getPercentColor(m.cpu_percent)">{{ formatPercent(m.cpu_percent) }}</td>
                  <td class="px-4 py-2 text-right" :class="getPercentColor(m.memory_percent)">{{ formatPercent(m.memory_percent) }}</td>
                  <td class="px-4 py-2 text-right" :class="getPercentColor(m.disk_percent)">{{ formatPercent(m.disk_percent) }}</td>
                  <td class="px-4 py-2 text-right text-gray-300">{{ m.load_1m ? (m.load_1m / 100).toFixed(2) : '-' }}</td>
                  <td class="px-4 py-2 text-right text-green-400">{{ formatBytes(m.network_rx_bytes) }}</td>
                  <td class="px-4 py-2 text-right text-blue-400">{{ formatBytes(m.network_tx_bytes) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- No data -->
        <div v-else-if="!loading" class="text-center py-12 text-gray-500">
          <p>Aucune donnee historique disponible pour cette periode</p>
        </div>
      </div>
    </div>
  </div>
</template>
