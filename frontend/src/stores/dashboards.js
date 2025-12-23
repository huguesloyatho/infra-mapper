import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useDashboardsStore = defineStore('dashboards', () => {
  // State
  const dashboards = ref([])
  const currentDashboard = ref(null)
  const positions = ref({}) // node_id -> {x, y}
  const loading = ref(false)
  const error = ref(null)
  const hasUnsavedChanges = ref(false)

  // Computed
  const dashboardList = computed(() => dashboards.value)
  const isCustomDashboard = computed(() => currentDashboard.value !== null)

  // Actions
  async function fetchDashboards() {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/v1/dashboards')
      if (!response.ok) throw new Error('Erreur lors du chargement des dashboards')
      dashboards.value = await response.json()
    } catch (e) {
      error.value = e.message
      console.error('Erreur fetch dashboards:', e)
    } finally {
      loading.value = false
    }
  }

  async function createDashboard(data) {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/v1/dashboards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!response.ok) throw new Error('Erreur lors de la création du dashboard')

      const newDashboard = await response.json()
      dashboards.value.push(newDashboard)
      return newDashboard
    } catch (e) {
      error.value = e.message
      console.error('Erreur création dashboard:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateDashboard(id, data) {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`/api/v1/dashboards/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })

      if (!response.ok) throw new Error('Erreur lors de la mise à jour du dashboard')

      const updated = await response.json()
      const index = dashboards.value.findIndex(d => d.id === id)
      if (index !== -1) {
        dashboards.value[index] = updated
      }

      if (currentDashboard.value?.id === id) {
        currentDashboard.value = updated
      }

      return updated
    } catch (e) {
      error.value = e.message
      console.error('Erreur mise à jour dashboard:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteDashboard(id) {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`/api/v1/dashboards/${id}`, {
        method: 'DELETE',
      })

      if (!response.ok) throw new Error('Erreur lors de la suppression du dashboard')

      dashboards.value = dashboards.value.filter(d => d.id !== id)

      if (currentDashboard.value?.id === id) {
        currentDashboard.value = null
        positions.value = {}
      }

      return true
    } catch (e) {
      error.value = e.message
      console.error('Erreur suppression dashboard:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadDashboard(id) {
    if (!id) {
      // Mode "live" sans dashboard personnalisé
      currentDashboard.value = null
      positions.value = {}
      hasUnsavedChanges.value = false
      return null
    }

    loading.value = true
    error.value = null

    try {
      const response = await fetch(`/api/v1/dashboards/${id}/graph`)
      if (!response.ok) throw new Error('Erreur lors du chargement du dashboard')

      const data = await response.json()

      // Trouver le dashboard dans la liste
      const dashboard = dashboards.value.find(d => d.id === id)
      currentDashboard.value = dashboard || null

      // Charger les positions sauvegardées
      positions.value = {}
      for (const [nodeId, pos] of Object.entries(data.positions || {})) {
        positions.value[nodeId] = { x: pos.x, y: pos.y }
      }

      hasUnsavedChanges.value = false

      return {
        graph: data.graph,
        positions: positions.value,
      }
    } catch (e) {
      error.value = e.message
      console.error('Erreur chargement dashboard:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  function updatePosition(nodeId, x, y) {
    positions.value[nodeId] = { x, y }
    hasUnsavedChanges.value = true
  }

  function updateAllPositions(newPositions) {
    // newPositions est un objet { nodeId: { x, y } }
    for (const [nodeId, pos] of Object.entries(newPositions)) {
      positions.value[nodeId] = { x: pos.x, y: pos.y }
    }
    hasUnsavedChanges.value = true
  }

  async function savePositions() {
    if (!currentDashboard.value) {
      console.warn('Pas de dashboard actif pour sauvegarder les positions')
      return false
    }

    loading.value = true
    error.value = null

    try {
      const positionsList = Object.entries(positions.value).map(([nodeId, pos]) => ({
        node_id: nodeId,
        x: pos.x,
        y: pos.y,
      }))

      const response = await fetch(`/api/v1/dashboards/${currentDashboard.value.id}/positions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions: positionsList }),
      })

      if (!response.ok) throw new Error('Erreur lors de la sauvegarde des positions')

      hasUnsavedChanges.value = false
      return true
    } catch (e) {
      error.value = e.message
      console.error('Erreur sauvegarde positions:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  function getPosition(nodeId) {
    return positions.value[nodeId] || null
  }

  function clearCurrentDashboard() {
    currentDashboard.value = null
    positions.value = {}
    hasUnsavedChanges.value = false
  }

  return {
    // State
    dashboards,
    currentDashboard,
    positions,
    loading,
    error,
    hasUnsavedChanges,
    // Computed
    dashboardList,
    isCustomDashboard,
    // Actions
    fetchDashboards,
    createDashboard,
    updateDashboard,
    deleteDashboard,
    loadDashboard,
    updatePosition,
    updateAllPositions,
    savePositions,
    getPosition,
    clearCurrentDashboard,
  }
})
