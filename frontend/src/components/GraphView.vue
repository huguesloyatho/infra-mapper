<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useGraphStore } from '../stores/graph'
import { useDashboardsStore } from '../stores/dashboards'
import { useCytoscape, getHostColor } from '../composables/useCytoscape'
import NodeDetails from './NodeDetails.vue'

const graphStore = useGraphStore()
const dashboardsStore = useDashboardsStore()

const { nodes, edges, loading, error, wsConnected, stats, lastUpdated, autoRefresh, edgeFilters, hostFilters, uniqueHosts } = storeToRefs(graphStore)
const { dashboards, currentDashboard, hasUnsavedChanges, loading: dashboardLoading } = storeToRefs(dashboardsStore)

const containerRef = ref(null)
const showDashboardModal = ref(false)
const showExportMenu = ref(false)
const newDashboardName = ref('')
const searchQuery = ref('')
const searchResults = ref([])

// Local state for selected node (synced from composable)
const currentSelectedNode = ref(null)

// Context menu state
const contextMenu = ref({
  show: false,
  x: 0,
  y: 0,
  node: null
})

const API_BASE = import.meta.env.VITE_API_URL || ''

// Context menu actions
const contextMenuActionLoading = ref(false)
const contextMenuActionResult = ref(null)

// Clé localStorage pour persister le dashboard sélectionné
const DASHBOARD_STORAGE_KEY = 'infra-mapper-selected-dashboard'

// Callback pour les changements de position
const handlePositionChange = (nodeId, x, y) => {
  if (currentDashboard.value) {
    dashboardsStore.updatePosition(nodeId, x, y)
  }
}

// Callback for right-click context menu
const handleContextMenu = (event, nodeData) => {
  contextMenu.value = {
    show: true,
    x: event.originalEvent.clientX,
    y: event.originalEvent.clientY,
    node: nodeData
  }
}

// Configuration du composable avec callback
const { selectedNode: composableSelectedNode, runLayout, fitGraph, zoomIn, zoomOut, exportPng, setSavedPositions, getAllPositions, searchNodes, clearSearch } = useCytoscape(
  containerRef,
  nodes,
  edges,
  edgeFilters,
  hostFilters,
  { onPositionChange: handlePositionChange, onContextMenu: handleContextMenu }
)

// Sync selectedNode from composable to local state
watch(composableSelectedNode, (newVal) => {
  console.log('[WATCH] composableSelectedNode changed:', newVal?.label)
  currentSelectedNode.value = newVal
}, { immediate: true })

// Function to clear selection
function clearSelection() {
  composableSelectedNode.value = null
  currentSelectedNode.value = null
}

function hideContextMenu() {
  contextMenu.value.show = false
  contextMenuActionResult.value = null
}

// Get container ID for API calls (format: host_id:container_id)
function getContainerIdForApi(node) {
  if (!node || node.type !== 'container') return null
  const id = node.id
  if (id.startsWith('container:')) {
    return id.substring('container:'.length)
  }
  return id
}

async function contextMenuAction(action) {
  const containerId = getContainerIdForApi(contextMenu.value.node)
  if (!containerId) return

  contextMenuActionLoading.value = true
  contextMenuActionResult.value = null

  try {
    const response = await fetch(`${API_BASE}/api/v1/containers/${containerId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    const data = await response.json()
    contextMenuActionResult.value = data

    // Auto-hide after success
    if (data.success) {
      setTimeout(() => {
        hideContextMenu()
        // Refresh graph to see new status
        graphStore.fetchGraph()
      }, 1500)
    }
  } catch (err) {
    contextMenuActionResult.value = { success: false, error: err.message }
  } finally {
    contextMenuActionLoading.value = false
  }
}

// Recherche de containers
function handleSearch() {
  searchResults.value = searchNodes(searchQuery.value)
}

function handleClearSearch() {
  searchQuery.value = ''
  searchResults.value = []
  clearSearch()
}

// Export functions
async function downloadFile(url, filename) {
  try {
    const response = await fetch(`${API_BASE}${url}`)
    if (!response.ok) throw new Error('Export failed')

    const contentType = response.headers.get('content-type')
    const blob = await response.blob()
    const downloadUrl = URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(downloadUrl)
  } catch (err) {
    console.error('Export error:', err)
    alert('Erreur lors de l\'export: ' + err.message)
  }
}

async function exportInventoryJson() {
  const filename = `infra-mapper-inventory-${new Date().toISOString().split('T')[0]}.json`
  const response = await fetch(`${API_BASE}/api/v1/export/inventory/json`)
  const data = await response.json()
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function exportInventoryCsv() {
  const filename = `infra-mapper-inventory-${new Date().toISOString().split('T')[0]}.csv`
  downloadFile('/api/v1/export/inventory/csv', filename)
}

async function exportConnectionsJson() {
  const filename = `infra-mapper-connections-${new Date().toISOString().split('T')[0]}.json`
  const response = await fetch(`${API_BASE}/api/v1/export/connections/json`)
  const data = await response.json()
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function exportConnectionsCsv() {
  const filename = `infra-mapper-connections-${new Date().toISOString().split('T')[0]}.csv`
  downloadFile('/api/v1/export/connections/csv', filename)
}

async function exportSummary() {
  const filename = `infra-mapper-summary-${new Date().toISOString().split('T')[0]}.json`
  const response = await fetch(`${API_BASE}/api/v1/export/report/summary`)
  const data = await response.json()
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

// Format de la date
const lastUpdatedFormatted = computed(() => {
  if (!lastUpdated.value) return '-'
  return new Intl.DateTimeFormat('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(lastUpdated.value)
})

// Charger un dashboard
async function selectDashboard(dashboardId, saveToStorage = true) {
  if (!dashboardId) {
    // Mode live
    dashboardsStore.clearCurrentDashboard()
    setSavedPositions({})
    if (saveToStorage) {
      localStorage.removeItem(DASHBOARD_STORAGE_KEY)
    }
    graphStore.fetchGraph()
    return
  }

  try {
    const data = await dashboardsStore.loadDashboard(dashboardId)
    if (data) {
      // D'abord les positions, puis les données du graphe
      setSavedPositions(data.positions)
      // Utiliser l'action du store pour mettre à jour les données
      graphStore.setGraphData(data.graph.nodes, data.graph.edges)

      // Persister le choix du dashboard
      if (saveToStorage) {
        localStorage.setItem(DASHBOARD_STORAGE_KEY, dashboardId)
      }
    }
  } catch (e) {
    console.error('Erreur chargement dashboard:', e)
    // En cas d'erreur (dashboard supprimé ?), nettoyer localStorage
    localStorage.removeItem(DASHBOARD_STORAGE_KEY)
  }
}

// Créer un nouveau dashboard
async function createDashboard() {
  if (!newDashboardName.value.trim()) return

  try {
    const dashboard = await dashboardsStore.createDashboard({
      name: newDashboardName.value.trim(),
    })
    newDashboardName.value = ''
    showDashboardModal.value = false

    // Charger le nouveau dashboard et sauvegarder les positions actuelles
    await selectDashboard(dashboard.id)

    // Sauvegarder les positions actuelles
    const positions = getAllPositions()
    dashboardsStore.updateAllPositions(positions)
    await dashboardsStore.savePositions()
  } catch (e) {
    console.error('Erreur création dashboard:', e)
  }
}

// Sauvegarder les positions
async function saveCurrentPositions() {
  if (!currentDashboard.value) return

  try {
    const positions = getAllPositions()
    dashboardsStore.updateAllPositions(positions)
    await dashboardsStore.savePositions()
  } catch (e) {
    console.error('Erreur sauvegarde positions:', e)
  }
}

// Supprimer le dashboard actuel
async function deleteCurrentDashboard() {
  if (!currentDashboard.value) return
  if (!confirm(`Supprimer le dashboard "${currentDashboard.value.name}" ?`)) return

  try {
    await dashboardsStore.deleteDashboard(currentDashboard.value.id)
    localStorage.removeItem(DASHBOARD_STORAGE_KEY)
    graphStore.fetchGraph()
  } catch (e) {
    console.error('Erreur suppression dashboard:', e)
  }
}

// Close context menu and export menu on click outside
function handleGlobalClick(event) {
  // Close context menu
  if (contextMenu.value.show) {
    const menuEl = document.getElementById('context-menu')
    if (menuEl && !menuEl.contains(event.target)) {
      hideContextMenu()
    }
  }
  // Close export menu
  if (showExportMenu.value) {
    const exportBtn = event.target.closest('.relative')
    if (!exportBtn || !exportBtn.querySelector('[class*="absolute"]')) {
      showExportMenu.value = false
    }
  }
}

onMounted(async () => {
  // Context menu handlers
  document.addEventListener('click', handleGlobalClick)
  document.addEventListener('contextmenu', (e) => {
    // Only prevent default if clicking on graph canvas
    if (containerRef.value?.contains(e.target)) {
      e.preventDefault()
    }
  })

  await dashboardsStore.fetchDashboards()
  graphStore.fetchStats()
  graphStore.connectWebSocket()

  // Restaurer le dashboard précédemment sélectionné
  const savedDashboardId = localStorage.getItem(DASHBOARD_STORAGE_KEY)
  if (savedDashboardId && dashboards.value.some(d => d.id === savedDashboardId)) {
    // Charger le dashboard sauvegardé sans re-sauvegarder dans localStorage
    await selectDashboard(savedDashboardId, false)
  } else {
    // Mode live par défaut
    graphStore.fetchGraph()
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleGlobalClick)
  graphStore.disconnectWebSocket()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white">
    <!-- Header -->
    <header class="flex items-center justify-between px-4 py-3 bg-gray-800 border-b border-gray-700">
      <div class="flex items-center gap-4">
        <!-- Sélecteur de dashboard -->
        <div class="flex items-center gap-2">
          <select
            :value="currentDashboard?.id || ''"
            @change="selectDashboard($event.target.value)"
            class="bg-gray-700 text-white text-sm px-3 py-1.5 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
          >
            <option value="">Live (temps réel)</option>
            <option v-for="d in dashboards" :key="d.id" :value="d.id">
              {{ d.name }}
            </option>
          </select>

          <button
            @click="showDashboardModal = true"
            class="px-2 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm"
            title="Nouveau dashboard"
          >
            +
          </button>

          <template v-if="currentDashboard">
            <button
              @click="saveCurrentPositions()"
              class="px-3 py-1.5 rounded text-sm"
              :class="hasUnsavedChanges ? 'bg-amber-600 hover:bg-amber-500' : 'bg-gray-700 hover:bg-gray-600'"
              :disabled="dashboardLoading"
            >
              {{ hasUnsavedChanges ? 'Sauver*' : 'Sauver' }}
            </button>

            <button
              @click="deleteCurrentDashboard()"
              class="px-2 py-1.5 bg-red-700 hover:bg-red-600 rounded text-sm"
              title="Supprimer"
            >
              X
            </button>
          </template>
        </div>

        <div class="flex items-center gap-2 text-sm text-gray-400">
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full" :class="wsConnected ? 'bg-green-500' : 'bg-red-500'"></span>
            {{ wsConnected ? 'Connecte' : 'Deconnecte' }}
          </span>
          <span class="text-gray-600">|</span>
          <span>MAJ: {{ lastUpdatedFormatted }}</span>
        </div>
      </div>

      <!-- Recherche -->
      <div class="flex items-center gap-2">
        <div class="relative">
          <input
            v-model="searchQuery"
            @input="handleSearch"
            @keyup.escape="handleClearSearch"
            type="text"
            placeholder="Rechercher un container..."
            class="bg-gray-700 text-white text-sm px-3 py-1.5 pl-8 rounded border border-gray-600 focus:border-blue-500 focus:outline-none w-64"
          />
          <svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <button
            v-if="searchQuery"
            @click="handleClearSearch"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
          >
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <span v-if="searchQuery && searchResults.length > 0" class="text-sm text-gray-400">
          {{ searchResults.length }} resultat{{ searchResults.length > 1 ? 's' : '' }}
        </span>
        <span v-else-if="searchQuery && searchResults.length === 0" class="text-sm text-amber-400">
          Aucun resultat
        </span>
      </div>

      <!-- Stats -->
      <div class="flex items-center gap-6 text-sm">
        <div class="flex items-center gap-2">
          <span class="w-3 h-3 bg-blue-500 rounded"></span>
          <span>{{ stats.hosts }} hotes</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-3 h-3 bg-green-500 rounded-full"></span>
          <span>{{ stats.containers }} conteneurs</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-3 h-3 bg-gray-500 rounded"></span>
          <span>{{ stats.connections }} connexions</span>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-2">
        <button
          @click="graphStore.toggleAutoRefresh()"
          class="px-3 py-1.5 rounded text-sm"
          :class="[
            currentDashboard !== null
              ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
              : autoRefresh
                ? 'bg-green-600 hover:bg-green-500'
                : 'bg-gray-700 hover:bg-gray-600'
          ]"
          :disabled="currentDashboard !== null"
          :title="currentDashboard ? 'Desactive en mode dashboard' : (autoRefresh ? 'Cliquer pour desactiver' : 'Cliquer pour activer le rafraichissement auto')"
        >
          {{ autoRefresh ? 'Pause Auto' : 'Play Auto' }}
        </button>
        <button
          @click="currentDashboard ? selectDashboard(currentDashboard.id) : (graphStore.fetchGraph(), runLayout())"
          class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm"
          :disabled="loading"
        >
          Rafraichir
        </button>
        <div class="relative">
          <button
            @click="showExportMenu = !showExportMenu"
            class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm flex items-center gap-1"
          >
            Exporter
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <!-- Export dropdown menu -->
          <div
            v-if="showExportMenu"
            class="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-50 min-w-48"
          >
            <div class="py-1">
              <button
                @click="exportPng(); showExportMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                Export PNG (graphe)
              </button>
              <div class="border-t border-gray-700 my-1"></div>
              <button
                @click="exportInventoryJson(); showExportMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Inventaire JSON
              </button>
              <button
                @click="exportInventoryCsv(); showExportMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Inventaire CSV
              </button>
              <div class="border-t border-gray-700 my-1"></div>
              <button
                @click="exportConnectionsJson(); showExportMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Connexions JSON
              </button>
              <button
                @click="exportConnectionsCsv(); showExportMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Connexions CSV
              </button>
              <div class="border-t border-gray-700 my-1"></div>
              <button
                @click="exportSummary(); showExportMenu = false"
                class="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
              >
                <svg class="w-4 h-4 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Rapport resume
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>

    <!-- Main -->
    <main class="flex-1 flex overflow-hidden">
      <!-- Graphe -->
      <div class="flex-1 relative">
        <!-- Loading -->
        <div
          v-if="loading || dashboardLoading"
          class="absolute inset-0 flex items-center justify-center bg-gray-900/50 z-10"
        >
          <div class="loading text-lg">Chargement...</div>
        </div>

        <!-- Error -->
        <div
          v-if="error"
          class="absolute top-4 left-4 right-4 p-4 bg-red-500/20 border border-red-500 rounded-lg z-10"
        >
          {{ error }}
        </div>

        <!-- Indicateur dashboard -->
        <div
          v-if="currentDashboard"
          class="absolute top-4 left-4 px-3 py-2 bg-blue-600/80 rounded-lg text-sm z-10"
        >
          Dashboard: {{ currentDashboard.name }}
          <span v-if="hasUnsavedChanges" class="text-amber-300 ml-2">*</span>
        </div>

        <!-- Canvas Cytoscape -->
        <div ref="containerRef" class="w-full h-full"></div>

        <!-- Context Menu -->
        <div
          v-if="contextMenu.show"
          id="context-menu"
          class="fixed bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-50 min-w-48"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        >
          <!-- Header -->
          <div class="px-3 py-2 border-b border-gray-700">
            <div class="font-medium text-sm truncate">{{ contextMenu.node?.label }}</div>
            <div class="text-xs text-gray-400">{{ contextMenu.node?.type === 'container' ? 'Container' : contextMenu.node?.type }}</div>
          </div>

          <!-- Actions for containers -->
          <div v-if="contextMenu.node?.type === 'container'" class="py-1">
            <button
              @click="contextMenuAction('start')"
              :disabled="contextMenuActionLoading || contextMenu.node?.status === 'running'"
              class="w-full px-3 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span class="w-4 text-center text-green-400">&#9654;</span>
              Demarrer
            </button>
            <button
              @click="contextMenuAction('stop')"
              :disabled="contextMenuActionLoading || contextMenu.node?.status !== 'running'"
              class="w-full px-3 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span class="w-4 text-center text-red-400">&#9632;</span>
              Arreter
            </button>
            <button
              @click="contextMenuAction('restart')"
              :disabled="contextMenuActionLoading"
              class="w-full px-3 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span class="w-4 text-center text-yellow-400">&#8635;</span>
              Redemarrer
            </button>
          </div>

          <!-- Action result -->
          <div v-if="contextMenuActionResult" class="px-3 py-2 border-t border-gray-700">
            <div
              class="text-xs p-2 rounded"
              :class="contextMenuActionResult.success ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'"
            >
              {{ contextMenuActionResult.success ? contextMenuActionResult.message || 'OK' : contextMenuActionResult.error }}
            </div>
          </div>

          <!-- Loading indicator -->
          <div v-if="contextMenuActionLoading" class="px-3 py-2 border-t border-gray-700">
            <div class="text-xs text-gray-400">Execution...</div>
          </div>
        </div>

        <!-- Controles de zoom -->
        <div class="absolute bottom-4 left-4 flex flex-col gap-2">
          <button
            @click="zoomIn()"
            class="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-lg text-xl"
          >
            +
          </button>
          <button
            @click="zoomOut()"
            class="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-lg text-xl"
          >
            -
          </button>
          <button
            @click="fitGraph()"
            class="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
            title="Ajuster a l'ecran"
          >
            [ ]
          </button>
          <button
            @click="runLayout()"
            class="w-10 h-10 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
            title="Reorganiser"
          >
            ~
          </button>
        </div>

        <!-- Legende interactive / Filtres -->
        <div class="absolute bottom-4 right-4 p-3 bg-gray-800/90 rounded-lg text-xs max-h-[80vh] overflow-y-auto">
          <div class="font-semibold mb-2">Legende & Filtres</div>

          <!-- VMs (couleurs dynamiques + filtrable) -->
          <div class="mb-3">
            <div class="text-gray-400 mb-1 text-[10px] uppercase tracking-wide">VMs</div>
            <div class="space-y-0.5">
              <label
                v-for="hostname in uniqueHosts"
                :key="hostname"
                class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded"
              >
                <input
                  type="checkbox"
                  :checked="hostFilters[hostname] !== false"
                  @change="graphStore.toggleHostFilter(hostname)"
                  class="w-3 h-3"
                  :style="{ accentColor: getHostColor(hostname) }"
                />
                <span
                  class="w-4 h-3 rounded"
                  :style="{ backgroundColor: getHostColor(hostname) }"
                ></span>
                <span>{{ hostname }}</span>
              </label>
            </div>
          </div>

          <!-- Etat des conteneurs -->
          <div class="mb-3">
            <div class="text-gray-400 mb-1 text-[10px] uppercase tracking-wide">Etat</div>
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <span class="w-4 h-3 bg-gray-600 rounded border-2 border-green-500"></span>
                <span>Running</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-4 h-3 bg-gray-600 rounded border-2 border-red-500 opacity-60"></span>
                <span>Stopped</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 bg-purple-800 rotate-45 border border-purple-500"></span>
                <span>Service externe</span>
              </div>
            </div>
          </div>

          <!-- Type de reseau (filtrable) -->
          <div class="mb-3">
            <div class="text-gray-400 mb-1 text-[10px] uppercase tracking-wide">Type de reseau</div>
            <div class="space-y-0.5">
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showInternal" class="accent-green-500 w-3 h-3">
                <span class="w-5 h-0.5 bg-green-500"></span>
                <span>Inter-conteneurs</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showCrossHost" class="accent-cyan-500 w-3 h-3">
                <span class="w-5 h-0.5 bg-cyan-500"></span>
                <span>Inter-VM (Tailscale)</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showExternal" class="accent-amber-500 w-3 h-3">
                <span class="w-5 h-0.5 bg-amber-500"></span>
                <span>Externe (web)</span>
              </label>
            </div>
          </div>

          <!-- Source de detection (filtrable) -->
          <div class="mb-3">
            <div class="text-gray-400 mb-1 text-[10px] uppercase tracking-wide">Source</div>
            <div class="space-y-0.5">
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showProcNet" class="w-3 h-3">
                <span>/proc/net</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showTcpdump" class="w-3 h-3">
                <span>tcpdump</span>
              </label>
            </div>
          </div>

          <!-- Type de lien (filtrable) -->
          <div>
            <div class="text-gray-400 mb-1 text-[10px] uppercase tracking-wide">Type de lien</div>
            <div class="space-y-0.5">
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showConnections" class="w-3 h-3">
                <span class="w-5 h-0.5 bg-amber-500"></span>
                <span>Connexions</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 p-1 rounded">
                <input type="checkbox" v-model="edgeFilters.showDependencies" class="w-3 h-3">
                <span class="w-5 border-t border-dashed border-cyan-500"></span>
                <span>Dependances</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- Panneau de details -->
      <NodeDetails
        v-if="currentSelectedNode"
        :node="currentSelectedNode"
        @close="clearSelection()"
      />
    </main>

    <!-- Modal creation dashboard -->
    <div
      v-if="showDashboardModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="showDashboardModal = false"
    >
      <div class="bg-gray-800 rounded-lg p-6 w-96">
        <h2 class="text-lg font-semibold mb-4">Nouveau Dashboard</h2>

        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-1">Nom du dashboard</label>
          <input
            v-model="newDashboardName"
            type="text"
            class="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
            placeholder="Mon dashboard"
            @keyup.enter="createDashboard()"
          />
        </div>

        <p class="text-sm text-gray-400 mb-4">
          Les positions actuelles des noeuds seront sauvegardees dans ce dashboard.
        </p>

        <div class="flex justify-end gap-2">
          <button
            @click="showDashboardModal = false"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded"
          >
            Annuler
          </button>
          <button
            @click="createDashboard()"
            :disabled="!newDashboardName.trim()"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Creer
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
