<script setup>
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useGraphStore } from '../stores/graph'

const graphStore = useGraphStore()
const { nodes, loading, error } = storeToRefs(graphStore)

// Recherche globale
const globalSearch = ref('')

// Recherche par VM
const vmSearches = ref({})

// Filtre d'etat
const showRunning = ref(true)
const showStopped = ref(true)

// Tri
const sortBy = ref('name') // 'name', 'status', 'project'
const sortAsc = ref(true)

// Recuperer les VMs uniques
const uniqueHosts = computed(() => {
  const hosts = new Map()
  nodes.value.forEach(n => {
    if (n.type === 'container' && n.data?.hostname) {
      if (!hosts.has(n.data.hostname)) {
        hosts.set(n.data.hostname, {
          hostname: n.data.hostname,
          hostId: n.data.host_id
        })
      }
    }
  })
  return Array.from(hosts.values()).sort((a, b) => a.hostname.localeCompare(b.hostname))
})

// Containers groupes par VM
const containersByHost = computed(() => {
  const result = {}

  uniqueHosts.value.forEach(host => {
    result[host.hostname] = []
  })

  nodes.value.forEach(n => {
    if (n.type === 'container' && n.data?.hostname) {
      const container = {
        id: n.id,
        name: n.data.compose_service || n.label?.split('\n')[0] || 'unknown',
        fullName: n.label?.split('\n')[0] || 'unknown',
        image: n.data.image || '',
        status: n.data.status || 'unknown',
        health: n.data.health || 'none',
        ports: n.data.ports || [],
        project: n.data.compose_project || '-',
        networks: n.data.networks || [],
        hostname: n.data.hostname
      }

      if (result[n.data.hostname]) {
        result[n.data.hostname].push(container)
      }
    }
  })

  return result
})

// Filtrer et trier les containers pour une VM
function getFilteredContainers(hostname) {
  let containers = containersByHost.value[hostname] || []

  // Filtre global
  if (globalSearch.value) {
    const search = globalSearch.value.toLowerCase()
    containers = containers.filter(c =>
      c.name.toLowerCase().includes(search) ||
      c.project.toLowerCase().includes(search) ||
      c.image.toLowerCase().includes(search)
    )
  }

  // Filtre par VM
  const vmSearch = vmSearches.value[hostname]
  if (vmSearch) {
    const search = vmSearch.toLowerCase()
    containers = containers.filter(c =>
      c.name.toLowerCase().includes(search) ||
      c.project.toLowerCase().includes(search) ||
      c.image.toLowerCase().includes(search)
    )
  }

  // Filtre par etat
  containers = containers.filter(c => {
    if (c.status === 'running' && !showRunning.value) return false
    if (c.status !== 'running' && !showStopped.value) return false
    return true
  })

  // Tri
  containers.sort((a, b) => {
    let cmp = 0
    switch (sortBy.value) {
      case 'name':
        cmp = a.name.localeCompare(b.name)
        break
      case 'status':
        cmp = a.status.localeCompare(b.status)
        break
      case 'project':
        cmp = a.project.localeCompare(b.project)
        break
    }
    return sortAsc.value ? cmp : -cmp
  })

  return containers
}

// Stats par VM
function getVmStats(hostname) {
  const containers = containersByHost.value[hostname] || []
  const running = containers.filter(c => c.status === 'running').length
  const stopped = containers.filter(c => c.status !== 'running').length
  return { total: containers.length, running, stopped }
}

// Stats globales
const globalStats = computed(() => {
  let total = 0, running = 0, stopped = 0
  uniqueHosts.value.forEach(host => {
    const stats = getVmStats(host.hostname)
    total += stats.total
    running += stats.running
    stopped += stats.stopped
  })
  return { total, running, stopped, hosts: uniqueHosts.value.length }
})

// Formatage des ports
function formatPorts(ports) {
  if (!ports || ports.length === 0) return '-'
  return ports
    .filter(p => p.host_port)
    .map(p => `${p.host_port}:${p.container_port}`)
    .slice(0, 3)
    .join(', ') + (ports.length > 3 ? '...' : '')
}

// Couleurs par VM
const VM_COLORS = [
  '#3b82f6', '#8b5cf6', '#ec4899', '#f97316', '#14b8a6',
  '#eab308', '#06b6d4', '#84cc16', '#f43f5e', '#6366f1'
]

function getVmColor(index) {
  return VM_COLORS[index % VM_COLORS.length]
}

// Toggle tri
function toggleSort(field) {
  if (sortBy.value === field) {
    sortAsc.value = !sortAsc.value
  } else {
    sortBy.value = field
    sortAsc.value = true
  }
}

onMounted(() => {
  graphStore.fetchGraph()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white p-4 overflow-hidden">
    <!-- Header -->
    <header class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-2xl font-bold text-blue-400">Inventaire Infrastructure</h1>
        <p class="text-gray-400 text-sm">
          {{ globalStats.hosts }} VMs - {{ globalStats.total }} containers
          ({{ globalStats.running }} running, {{ globalStats.stopped }} stopped)
        </p>
      </div>

      <!-- Filtres globaux -->
      <div class="flex items-center gap-4">
        <!-- Recherche globale -->
        <div class="relative">
          <input
            v-model="globalSearch"
            type="text"
            placeholder="Recherche globale..."
            class="bg-gray-800 text-white text-sm px-4 py-2 pl-10 rounded-lg border border-gray-700 focus:border-blue-500 focus:outline-none w-64"
          />
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <!-- Filtres d'etat -->
        <div class="flex items-center gap-2">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" v-model="showRunning" class="accent-green-500 w-4 h-4" />
            <span class="text-sm text-green-400">Running</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" v-model="showStopped" class="accent-red-500 w-4 h-4" />
            <span class="text-sm text-red-400">Stopped</span>
          </label>
        </div>

        <!-- Tri -->
        <div class="flex items-center gap-2 text-sm">
          <span class="text-gray-400">Tri:</span>
          <button
            @click="toggleSort('name')"
            class="px-2 py-1 rounded"
            :class="sortBy === 'name' ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'"
          >
            Nom {{ sortBy === 'name' ? (sortAsc ? '↑' : '↓') : '' }}
          </button>
          <button
            @click="toggleSort('project')"
            class="px-2 py-1 rounded"
            :class="sortBy === 'project' ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'"
          >
            Projet {{ sortBy === 'project' ? (sortAsc ? '↑' : '↓') : '' }}
          </button>
          <button
            @click="toggleSort('status')"
            class="px-2 py-1 rounded"
            :class="sortBy === 'status' ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'"
          >
            Etat {{ sortBy === 'status' ? (sortAsc ? '↑' : '↓') : '' }}
          </button>
        </div>

        <!-- Refresh -->
        <button
          @click="graphStore.fetchGraph()"
          class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm flex items-center gap-2"
          :disabled="loading"
        >
          <svg class="w-4 h-4" :class="loading ? 'animate-spin' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Rafraichir
        </button>
      </div>
    </header>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-4 bg-red-500/20 border border-red-500 rounded-lg">
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading && nodes.length === 0" class="flex-1 flex items-center justify-center">
      <div class="text-xl text-gray-400">Chargement...</div>
    </div>

    <!-- Colonnes par VM -->
    <div v-else class="flex-1 overflow-x-auto">
      <div class="flex gap-4 h-full min-w-max">
        <div
          v-for="(host, index) in uniqueHosts"
          :key="host.hostname"
          class="flex flex-col w-80 min-w-80 bg-gray-800 rounded-lg overflow-hidden"
        >
          <!-- Header VM -->
          <div
            class="p-3 border-b-2"
            :style="{ borderColor: getVmColor(index), backgroundColor: getVmColor(index) + '20' }"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="w-3 h-3 rounded-full"
                  :style="{ backgroundColor: getVmColor(index) }"
                ></span>
                <span class="font-semibold">{{ host.hostname }}</span>
              </div>
              <div class="text-xs text-gray-400">
                {{ getVmStats(host.hostname).running }}/{{ getVmStats(host.hostname).total }}
              </div>
            </div>

            <!-- Recherche par VM -->
            <div class="mt-2 relative">
              <input
                v-model="vmSearches[host.hostname]"
                type="text"
                placeholder="Filtrer..."
                class="w-full bg-gray-700 text-white text-xs px-3 py-1.5 pl-8 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
              />
              <svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>

          <!-- Liste containers -->
          <div class="flex-1 overflow-y-auto p-2 space-y-2">
            <div
              v-for="container in getFilteredContainers(host.hostname)"
              :key="container.id"
              class="p-2 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors"
            >
              <!-- Nom + Status -->
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-sm truncate" :title="container.fullName">
                  {{ container.name }}
                </span>
                <span
                  class="w-2 h-2 rounded-full flex-shrink-0"
                  :class="container.status === 'running' ? 'bg-green-500' : 'bg-red-500'"
                  :title="container.status"
                ></span>
              </div>

              <!-- Projet -->
              <div class="text-xs text-gray-400 mb-1">
                <span class="text-blue-400">{{ container.project }}</span>
              </div>

              <!-- Image -->
              <div class="text-xs text-gray-500 truncate" :title="container.image">
                {{ container.image.split('/').pop()?.split(':')[0] || container.image }}
              </div>

              <!-- Ports -->
              <div v-if="container.ports?.length > 0" class="text-xs text-amber-400 mt-1">
                {{ formatPorts(container.ports) }}
              </div>

              <!-- Health -->
              <div v-if="container.health && container.health !== 'none'" class="mt-1">
                <span
                  class="text-xs px-1.5 py-0.5 rounded"
                  :class="{
                    'bg-green-900 text-green-300': container.health === 'healthy',
                    'bg-yellow-900 text-yellow-300': container.health === 'starting',
                    'bg-red-900 text-red-300': container.health === 'unhealthy'
                  }"
                >
                  {{ container.health }}
                </span>
              </div>
            </div>

            <!-- Empty state -->
            <div
              v-if="getFilteredContainers(host.hostname).length === 0"
              class="text-center text-gray-500 text-sm py-4"
            >
              Aucun container
            </div>
          </div>
        </div>

        <!-- Empty state global -->
        <div
          v-if="uniqueHosts.length === 0 && !loading"
          class="flex-1 flex items-center justify-center text-gray-500"
        >
          Aucune VM trouvee
        </div>
      </div>
    </div>
  </div>
</template>
