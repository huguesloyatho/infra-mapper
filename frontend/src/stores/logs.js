import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useLogsStore = defineStore('logs', () => {
  // State
  const logs = ref([])
  const loading = ref(false)
  const error = ref(null)
  const total = ref(0)
  const currentContainer = ref(null)
  const currentContainerInfo = ref(null)
  const stats = ref(null)

  // Filters
  const filters = ref({
    search: '',
    stream: null,  // null = tous, 'stdout', 'stderr'
    since: null,   // datetime
    until: null,
  })

  // Pagination
  const pagination = ref({
    limit: 100,
    offset: 0,
  })

  // Computed
  const hasMore = computed(() =>
    logs.value.length < total.value
  )

  const filteredLogs = computed(() => {
    let result = logs.value

    // Filtre local par stream si déjà chargé
    if (filters.value.stream) {
      result = result.filter(log => log.stream === filters.value.stream)
    }

    return result
  })

  const stdoutCount = computed(() =>
    logs.value.filter(log => log.stream === 'stdout').length
  )

  const stderrCount = computed(() =>
    logs.value.filter(log => log.stream === 'stderr').length
  )

  // Actions
  async function fetchContainerLogs(containerId, options = {}) {
    loading.value = true
    error.value = null
    currentContainer.value = containerId

    try {
      const params = new URLSearchParams()
      params.append('limit', options.limit || pagination.value.limit)
      params.append('offset', options.offset || 0)

      if (options.search || filters.value.search) {
        params.append('search', options.search || filters.value.search)
      }
      if (options.since || filters.value.since) {
        params.append('since', (options.since || filters.value.since).toISOString())
      }
      if (options.until || filters.value.until) {
        params.append('until', (options.until || filters.value.until).toISOString())
      }
      if (options.stream || filters.value.stream) {
        params.append('stream', options.stream || filters.value.stream)
      }

      const response = await fetch(`/api/v1/containers/${encodeURIComponent(containerId)}/logs?${params}`)

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur chargement logs')
      }

      const data = await response.json()

      // Si c'est un append (pagination), ajouter aux logs existants
      if (options.append && options.offset > 0) {
        logs.value = [...logs.value, ...data.logs]
      } else {
        logs.value = data.logs
      }

      total.value = data.total
      currentContainerInfo.value = {
        container_id: data.container_id,
        container_name: data.container_name,
        host_name: data.host_name,
      }

      pagination.value.offset = options.offset || 0
    } catch (e) {
      error.value = e.message
      console.error('Erreur fetch container logs:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchHostLogs(hostId, limit = 500) {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      params.append('limit', limit)

      const response = await fetch(`/api/v1/hosts/${hostId}/logs?${params}`)

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur chargement logs hôte')
      }

      const data = await response.json()
      logs.value = data
      total.value = data.length
    } catch (e) {
      error.value = e.message
      console.error('Erreur fetch host logs:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchLogsStats() {
    try {
      const response = await fetch('/api/v1/logs/stats')

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur chargement stats')
      }

      stats.value = await response.json()
    } catch (e) {
      console.error('Erreur fetch logs stats:', e)
    }
  }

  async function cleanupOldLogs(days = 7) {
    try {
      const response = await fetch('/api/v1/logs/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur cleanup logs')
      }

      const result = await response.json()

      // Rafraîchir les stats
      await fetchLogsStats()

      return result
    } catch (e) {
      console.error('Erreur cleanup logs:', e)
      throw e
    }
  }

  function loadMoreLogs() {
    if (!hasMore.value || loading.value || !currentContainer.value) return

    fetchContainerLogs(currentContainer.value, {
      offset: pagination.value.offset + pagination.value.limit,
      append: true,
    })
  }

  function setFilters(newFilters) {
    filters.value = { ...filters.value, ...newFilters }
    // Reset pagination et recharger
    if (currentContainer.value) {
      fetchContainerLogs(currentContainer.value, { offset: 0 })
    }
  }

  function setStream(stream) {
    filters.value.stream = stream
    if (currentContainer.value) {
      fetchContainerLogs(currentContainer.value, { offset: 0 })
    }
  }

  function setSearch(search) {
    filters.value.search = search
    if (currentContainer.value) {
      fetchContainerLogs(currentContainer.value, { offset: 0 })
    }
  }

  function clearLogs() {
    logs.value = []
    currentContainer.value = null
    currentContainerInfo.value = null
    total.value = 0
    pagination.value.offset = 0
    filters.value = {
      search: '',
      stream: null,
      since: null,
      until: null,
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    logs,
    loading,
    error,
    total,
    currentContainer,
    currentContainerInfo,
    stats,
    filters,
    pagination,
    // Computed
    hasMore,
    filteredLogs,
    stdoutCount,
    stderrCount,
    // Actions
    fetchContainerLogs,
    fetchHostLogs,
    fetchLogsStats,
    cleanupOldLogs,
    loadMoreLogs,
    setFilters,
    setStream,
    setSearch,
    clearLogs,
    clearError,
  }
})
