import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useVmsStore = defineStore('vms', () => {
  // State
  const vms = ref([])
  const loading = ref(false)
  const error = ref(null)
  const actionInProgress = ref(null)  // vm_id en cours d'action
  const deploymentProgress = ref({})  // { vm_id: { step, progress, message } }

  // Computed
  const onlineVms = computed(() =>
    vms.value.filter(vm => vm.status === 'online')
  )

  const offlineVms = computed(() =>
    vms.value.filter(vm => vm.status === 'offline')
  )

  const pendingVms = computed(() =>
    vms.value.filter(vm => vm.status === 'pending')
  )

  const deployingVms = computed(() =>
    vms.value.filter(vm => vm.status === 'deploying')
  )

  const autoDiscoveredVms = computed(() =>
    vms.value.filter(vm => vm.is_auto_discovered)
  )

  const manualVms = computed(() =>
    vms.value.filter(vm => !vm.is_auto_discovered)
  )

  // Actions
  async function fetchVms(includeAutoDiscovered = true) {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      params.append('include_auto_discovered', includeAutoDiscovered.toString())

      const response = await fetch(`/api/v1/vms?${params}`)
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur chargement VMs')
      }

      vms.value = await response.json()
    } catch (e) {
      error.value = e.message
      console.error('Erreur fetch VMs:', e)
    } finally {
      loading.value = false
    }
  }

  async function createVm(data) {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/v1/vms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur création VM')
      }

      const vm = await response.json()
      vms.value.push(vm)
      return vm
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateVm(vmId, data) {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`/api/v1/vms/${vmId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur mise à jour VM')
      }

      const updated = await response.json()
      const index = vms.value.findIndex(v => v.id === vmId)
      if (index !== -1) {
        vms.value[index] = updated
      }
      return updated
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteVm(vmId, options = {}) {
    const { deleteAgent = false, deleteHostData = true } = options
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      params.append('delete_agent', deleteAgent.toString())
      params.append('delete_host_data', deleteHostData.toString())

      const response = await fetch(`/api/v1/vms/${vmId}?${params}`, {
        method: 'DELETE'
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur suppression VM')
      }

      vms.value = vms.value.filter(v => v.id !== vmId)
      return await response.json()
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function testSshConnection(ipAddress, sshPort = 22, sshUser = 'root') {
    try {
      const response = await fetch('/api/v1/ssh/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip_address: ipAddress,
          ssh_port: sshPort,
          ssh_user: sshUser
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur test SSH')
      }

      return await response.json()
    } catch (e) {
      console.error('Erreur test SSH:', e)
      throw e
    }
  }

  async function deployAgent(vmIds) {
    if (vmIds.length === 0) return []

    actionInProgress.value = vmIds[0]
    error.value = null

    // Mettre les VMs en statut deploying
    vmIds.forEach(id => {
      const vm = vms.value.find(v => v.id === id)
      if (vm) vm.status = 'deploying'
    })

    try {
      const response = await fetch('/api/v1/agents/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vm_ids: vmIds })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur déploiement')
      }

      const results = await response.json()

      // Rafraîchir les VMs pour avoir les statuts à jour
      await fetchVms()

      return results
    } catch (e) {
      error.value = e.message
      // Rafraîchir pour restaurer les statuts corrects
      await fetchVms()
      throw e
    } finally {
      actionInProgress.value = null
    }
  }

  async function agentAction(vmIds, action) {
    if (vmIds.length === 0) return []

    actionInProgress.value = vmIds[0]
    error.value = null

    try {
      const response = await fetch('/api/v1/agents/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vm_ids: vmIds, action })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Erreur action ${action}`)
      }

      const results = await response.json()

      // Rafraîchir les VMs
      await fetchVms()

      return results
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      actionInProgress.value = null
    }
  }

  async function getAgentLogs(vmId, lines = 100) {
    try {
      const response = await fetch(`/api/v1/agents/${vmId}/logs?lines=${lines}`)

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Erreur récupération logs')
      }

      return await response.json()
    } catch (e) {
      console.error('Erreur get agent logs:', e)
      throw e
    }
  }

  function getVmById(vmId) {
    return vms.value.find(v => v.id === vmId)
  }

  function clearError() {
    error.value = null
  }

  // Deployment progress handlers
  function handleDeploymentProgress(data) {
    deploymentProgress.value[data.vm_id] = {
      step: data.step,
      progress: data.progress,
      message: data.message
    }

    // Si c'est une erreur ou terminé, mettre à jour le statut de la VM
    if (data.step === 'error') {
      const vm = vms.value.find(v => v.id === data.vm_id)
      if (vm) {
        vm.status = 'error'
      }
    }
  }

  function clearDeploymentProgress(vmId) {
    if (vmId) {
      delete deploymentProgress.value[vmId]
    } else {
      deploymentProgress.value = {}
    }
  }

  function getDeploymentProgress(vmId) {
    return deploymentProgress.value[vmId] || null
  }

  return {
    // State
    vms,
    loading,
    error,
    actionInProgress,
    deploymentProgress,
    // Computed
    onlineVms,
    offlineVms,
    pendingVms,
    deployingVms,
    autoDiscoveredVms,
    manualVms,
    // Actions
    fetchVms,
    createVm,
    updateVm,
    deleteVm,
    testSshConnection,
    deployAgent,
    agentAction,
    getAgentLogs,
    getVmById,
    clearError,
    // Deployment progress
    handleDeploymentProgress,
    clearDeploymentProgress,
    getDeploymentProgress,
  }
})
