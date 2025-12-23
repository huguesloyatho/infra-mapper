<script setup>
import { ref, computed, onMounted, watch } from 'vue'

// State
const containers = ref([])
const hosts = ref([])
const logs = ref([])
const loading = ref(false)
const loadingContainers = ref(false)
const stats = ref(null)

// Filters
const selectedHost = ref('')
const selectedContainer = ref('')
const searchQuery = ref('')
const streamFilter = ref('')
const limit = ref(100)

// Pagination
const offset = ref(0)
const total = ref(0)
const hasMore = computed(() => offset.value + logs.value.length < total.value)

// Fetch hosts
async function fetchHosts() {
  try {
    const response = await fetch('/api/v1/hosts')
    if (!response.ok) throw new Error('Erreur chargement hosts')
    hosts.value = await response.json()
  } catch (error) {
    console.error('Erreur chargement hosts:', error)
  }
}

// Fetch containers for selected host
async function fetchContainers() {
  if (!selectedHost.value) {
    containers.value = []
    return
  }

  loadingContainers.value = true
  try {
    const url = new URL('/api/v1/containers', window.location.origin)
    url.searchParams.set('host_id', selectedHost.value)
    const response = await fetch(url)
    if (!response.ok) throw new Error('Erreur chargement containers')
    containers.value = await response.json()
  } catch (error) {
    console.error('Erreur chargement containers:', error)
  } finally {
    loadingContainers.value = false
  }
}

// Fetch all containers
async function fetchAllContainers() {
  loadingContainers.value = true
  try {
    const response = await fetch('/api/v1/containers')
    if (!response.ok) throw new Error('Erreur chargement containers')
    containers.value = await response.json()
  } catch (error) {
    console.error('Erreur chargement containers:', error)
  } finally {
    loadingContainers.value = false
  }
}

// Fetch logs
async function fetchLogs(append = false) {
  if (!selectedContainer.value) {
    logs.value = []
    total.value = 0
    return
  }

  loading.value = true
  try {
    const url = new URL(`/api/v1/containers/${selectedContainer.value}/logs`, window.location.origin)
    url.searchParams.set('limit', limit.value.toString())
    url.searchParams.set('offset', (append ? offset.value : 0).toString())

    if (searchQuery.value) {
      url.searchParams.set('search', searchQuery.value)
    }
    if (streamFilter.value) {
      url.searchParams.set('stream', streamFilter.value)
    }

    const response = await fetch(url)
    if (!response.ok) throw new Error('Erreur chargement logs')
    const data = await response.json()

    if (append) {
      logs.value = [...logs.value, ...data.logs]
    } else {
      logs.value = data.logs
      offset.value = 0
    }
    total.value = data.total
  } catch (error) {
    console.error('Erreur chargement logs:', error)
  } finally {
    loading.value = false
  }
}

// Fetch log stats
async function fetchStats() {
  try {
    const response = await fetch('/api/v1/logs/stats')
    if (!response.ok) throw new Error('Erreur chargement stats')
    stats.value = await response.json()
  } catch (error) {
    console.error('Erreur chargement stats:', error)
  }
}

// Load more logs
function loadMore() {
  offset.value += limit.value
  fetchLogs(true)
}

// Reset and search
function search() {
  offset.value = 0
  fetchLogs()
}

// Format timestamp
function formatTimestamp(ts) {
  if (!ts) return ''
  const date = new Date(ts)
  return date.toLocaleString('fr-FR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// Get container name from ID
function getContainerName(containerId) {
  const container = containers.value.find(c => c.id === containerId)
  return container?.name || containerId
}

// Watch host change
watch(selectedHost, () => {
  selectedContainer.value = ''
  logs.value = []
  if (selectedHost.value) {
    fetchContainers()
  } else {
    fetchAllContainers()
  }
})

// Watch container change
watch(selectedContainer, () => {
  if (selectedContainer.value) {
    fetchLogs()
  } else {
    logs.value = []
  }
})

// Initial load
onMounted(() => {
  fetchHosts()
  fetchAllContainers()
  fetchStats()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white">
    <!-- Header -->
    <div class="p-4 border-b border-gray-700">
      <h1 class="text-xl font-semibold mb-4">Logs des Containers</h1>

      <!-- Filters -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <!-- Host filter -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Host</label>
          <select
            v-model="selectedHost"
            class="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">Tous les hosts</option>
            <option v-for="host in hosts" :key="host.id" :value="host.id">
              {{ host.hostname }}
            </option>
          </select>
        </div>

        <!-- Container filter -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Container</label>
          <select
            v-model="selectedContainer"
            :disabled="loadingContainers"
            class="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
          >
            <option value="">Selectionner un container</option>
            <option v-for="container in containers" :key="container.id" :value="container.id">
              {{ container.name }} ({{ container.host_name }})
            </option>
          </select>
        </div>

        <!-- Stream filter -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Stream</label>
          <select
            v-model="streamFilter"
            class="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            @change="search"
          >
            <option value="">Tous</option>
            <option value="stdout">stdout</option>
            <option value="stderr">stderr</option>
          </select>
        </div>

        <!-- Search -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Recherche</label>
          <div class="flex gap-2">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Rechercher..."
              class="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              @keyup.enter="search"
            />
            <button
              @click="search"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium"
            >
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Limit -->
        <div>
          <label class="block text-sm text-gray-400 mb-1">Lignes</label>
          <select
            v-model="limit"
            class="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            @change="search"
          >
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="200">200</option>
            <option :value="500">500</option>
          </select>
        </div>
      </div>

      <!-- Stats -->
      <div v-if="stats" class="mt-4 flex gap-6 text-sm text-gray-400">
        <span>Total: <span class="text-white font-medium">{{ stats.total?.toLocaleString() }}</span> logs</span>
        <span>stdout: <span class="text-green-400">{{ stats.stdout?.toLocaleString() }}</span></span>
        <span>stderr: <span class="text-red-400">{{ stats.stderr?.toLocaleString() }}</span></span>
      </div>
    </div>

    <!-- Logs display -->
    <div class="flex-1 overflow-hidden flex flex-col">
      <!-- Info bar -->
      <div v-if="selectedContainer" class="px-4 py-2 bg-gray-800 border-b border-gray-700 text-sm">
        <span class="text-gray-400">Container:</span>
        <span class="ml-2 text-white font-medium">{{ getContainerName(selectedContainer) }}</span>
        <span class="ml-4 text-gray-400">|</span>
        <span class="ml-4 text-gray-400">{{ total }} logs trouves</span>
      </div>

      <!-- Loading -->
      <div v-if="loading && logs.length === 0" class="flex-1 flex items-center justify-center">
        <div class="flex items-center gap-3 text-gray-400">
          <svg class="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Chargement des logs...
        </div>
      </div>

      <!-- Empty state -->
      <div v-else-if="!selectedContainer" class="flex-1 flex items-center justify-center text-gray-500">
        <div class="text-center">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p>Selectionnez un container pour voir ses logs</p>
        </div>
      </div>

      <!-- No results -->
      <div v-else-if="logs.length === 0 && !loading" class="flex-1 flex items-center justify-center text-gray-500">
        <div class="text-center">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          <p>Aucun log trouve</p>
        </div>
      </div>

      <!-- Logs list -->
      <div v-else class="flex-1 overflow-auto font-mono text-sm">
        <div
          v-for="(log, index) in logs"
          :key="index"
          class="flex border-b border-gray-800 hover:bg-gray-800/50"
        >
          <!-- Timestamp -->
          <div class="flex-shrink-0 w-48 px-3 py-1 text-gray-500 border-r border-gray-800">
            {{ formatTimestamp(log.timestamp) }}
          </div>

          <!-- Stream badge -->
          <div class="flex-shrink-0 w-16 px-2 py-1 border-r border-gray-800">
            <span
              :class="log.stream === 'stderr' ? 'text-red-400' : 'text-green-400'"
              class="text-xs"
            >
              {{ log.stream }}
            </span>
          </div>

          <!-- Message -->
          <div class="flex-1 px-3 py-1 whitespace-pre-wrap break-all" :class="log.stream === 'stderr' ? 'text-red-300' : 'text-gray-200'">
            {{ log.message }}
          </div>
        </div>

        <!-- Load more -->
        <div v-if="hasMore" class="p-4 text-center">
          <button
            @click="loadMore"
            :disabled="loading"
            class="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm disabled:opacity-50"
          >
            {{ loading ? 'Chargement...' : 'Charger plus' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
