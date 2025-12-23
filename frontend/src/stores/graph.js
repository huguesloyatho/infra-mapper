import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useVmsStore } from './vms'

export const useGraphStore = defineStore('graph', () => {
  // State
  const nodes = ref([])
  const edges = ref([])
  const lastUpdated = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const stats = ref({ hosts: 0, containers: 0, connections: 0 })

  // Filtres
  const filters = ref({
    includeOffline: true,  // Inclure tous les hôtes/conteneurs par défaut
    hostFilter: '',
    projectFilter: '',
    showExternal: true,
  })

  // Filtres de visibilité des edges (côté client)
  const edgeFilters = ref({
    // Par type de réseau
    showInternal: true,      // inter-conteneurs même VM
    showCrossHost: true,     // inter-VM (Tailscale)
    showExternal: true,      // vers internet

    // Par source de détection
    showProcNet: true,       // /proc/net
    showTcpdump: true,       // tcpdump

    // Par type de lien
    showConnections: true,   // connexions réseau
    showDependencies: true,  // depends_on déclarées
  })

  // Filtres de visibilité par VM/hostname
  const hostFilters = ref({})  // { hostname: boolean } - true/undefined = visible, false = masqué

  // Option de rafraîchissement auto
  const autoRefresh = ref(false)

  // WebSocket
  const wsConnected = ref(false)
  let ws = null

  // Computed
  const hostNodes = computed(() =>
    nodes.value.filter(n => n.type === 'host')
  )

  const containerNodes = computed(() =>
    nodes.value.filter(n => n.type === 'container')
  )

  const externalNodes = computed(() =>
    nodes.value.filter(n => n.type === 'external')
  )

  // Liste unique des VMs (hostnames)
  const uniqueHosts = computed(() => {
    const hosts = new Set()
    nodes.value.forEach(n => {
      const hostname = n.data?.hostname
      if (hostname) hosts.add(hostname)
    })
    return Array.from(hosts).sort()
  })

  // Actions
  async function fetchGraph() {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      if (filters.value.includeOffline) params.append('include_offline', 'true')
      if (filters.value.hostFilter) params.append('host_filter', filters.value.hostFilter)
      if (filters.value.projectFilter) params.append('project_filter', filters.value.projectFilter)

      const response = await fetch(`/api/v1/graph?${params}`)
      if (!response.ok) throw new Error('Erreur lors du chargement du graphe')

      const data = await response.json()
      nodes.value = data.nodes
      edges.value = data.edges
      lastUpdated.value = new Date(data.last_updated)
    } catch (e) {
      error.value = e.message
      console.error('Erreur fetch graph:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    try {
      const response = await fetch('/api/v1/stats')
      if (response.ok) {
        stats.value = await response.json()
      }
    } catch (e) {
      console.error('Erreur fetch stats:', e)
    }
  }

  function connectWebSocket() {
    if (ws) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      wsConnected.value = true
      console.log('WebSocket connecté')
    }

    ws.onclose = () => {
      wsConnected.value = false
      ws = null
      // Reconnecter après 5 secondes
      setTimeout(connectWebSocket, 5000)
    }

    ws.onerror = (e) => {
      console.error('Erreur WebSocket:', e)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        handleWsMessage(message)
      } catch (e) {
        console.error('Erreur parsing message WS:', e)
      }
    }

    // Heartbeat
    setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 30000)
  }

  function handleWsMessage(message) {
    // Handler pour deployment_progress - toujours actif
    if (message.type === 'deployment_progress') {
      const vmsStore = useVmsStore()
      vmsStore.handleDeploymentProgress(message.data)
      return
    }

    // Ne rafraîchir que si autoRefresh est activé
    if (!autoRefresh.value) {
      // Juste mettre à jour les stats
      if (message.type === 'graph_refresh' || message.type === 'host_update') {
        fetchStats()
      }
      return
    }

    switch (message.type) {
      case 'graph_refresh':
        fetchGraph()
        fetchStats()
        break
      case 'host_update':
        console.log('Host mis à jour:', message.data)
        fetchGraph()
        break
      case 'container_change':
        console.log('Conteneur modifié:', message.data)
        fetchGraph()
        break
    }
  }

  function toggleAutoRefresh() {
    autoRefresh.value = !autoRefresh.value
  }

  function disconnectWebSocket() {
    if (ws) {
      ws.close()
      ws = null
    }
  }

  function updateFilters(newFilters) {
    filters.value = { ...filters.value, ...newFilters }
    fetchGraph()
  }

  function toggleEdgeFilter(filterKey) {
    edgeFilters.value[filterKey] = !edgeFilters.value[filterKey]
  }

  function toggleHostFilter(hostname) {
    // Si undefined (jamais cliqué), mettre à false (masquer)
    // Sinon toggle la valeur
    if (hostFilters.value[hostname] === undefined) {
      hostFilters.value[hostname] = false
    } else {
      hostFilters.value[hostname] = !hostFilters.value[hostname]
    }
  }

  function setGraphData(newNodes, newEdges) {
    nodes.value = newNodes || []
    edges.value = newEdges || []
    lastUpdated.value = new Date()
  }

  return {
    // State
    nodes,
    edges,
    lastUpdated,
    loading,
    error,
    stats,
    filters,
    edgeFilters,
    hostFilters,
    wsConnected,
    autoRefresh,
    // Computed
    hostNodes,
    containerNodes,
    externalNodes,
    uniqueHosts,
    // Actions
    fetchGraph,
    fetchStats,
    connectWebSocket,
    disconnectWebSocket,
    updateFilters,
    toggleAutoRefresh,
    toggleEdgeFilter,
    toggleHostFilter,
    setGraphData,
  }
})
