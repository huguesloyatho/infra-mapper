<script setup>
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useVmsStore } from '../stores/vms'
import VmModal from './VmModal.vue'
import AgentLogsModal from './AgentLogsModal.vue'
import SshKeyModal from './SshKeyModal.vue'

const vmsStore = useVmsStore()
const { vms, loading, error, actionInProgress, deploymentProgress } = storeToRefs(vmsStore)

// Selection
const selectedVmIds = ref(new Set())
const selectAll = ref(false)

// Modals
const showVmModal = ref(false)
const editingVm = ref(null)
const showAgentLogsModal = ref(false)
const logsVmId = ref(null)
const showSshKeyModal = ref(false)
const showDeleteModal = ref(false)
const vmToDelete = ref(null)
const deleteOptions = ref({ deleteAgent: false, deleteHostData: true })

// Filter
const filterStatus = ref('all')
const searchQuery = ref('')

// Computed
const filteredVms = computed(() => {
  let result = vms.value

  // Filter by status
  if (filterStatus.value !== 'all') {
    result = result.filter(vm => vm.status === filterStatus.value)
  }

  // Filter by search
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(vm =>
      vm.name.toLowerCase().includes(query) ||
      vm.hostname.toLowerCase().includes(query) ||
      vm.ip_address.toLowerCase().includes(query)
    )
  }

  return result
})

const selectedVms = computed(() =>
  vms.value.filter(vm => selectedVmIds.value.has(vm.id))
)

const canDeploy = computed(() =>
  selectedVms.value.some(vm => vm.status === 'pending' || vm.status === 'offline')
)

const canStart = computed(() =>
  selectedVms.value.some(vm => vm.status === 'offline')
)

const canStop = computed(() =>
  selectedVms.value.some(vm => vm.status === 'online')
)

// Methods
function toggleSelectAll() {
  if (selectAll.value) {
    selectedVmIds.value = new Set()
    selectAll.value = false
  } else {
    selectedVmIds.value = new Set(filteredVms.value.map(vm => vm.id))
    selectAll.value = true
  }
}

function toggleSelect(vmId) {
  if (selectedVmIds.value.has(vmId)) {
    selectedVmIds.value.delete(vmId)
  } else {
    selectedVmIds.value.add(vmId)
  }
  // Force reactivity
  selectedVmIds.value = new Set(selectedVmIds.value)
  selectAll.value = selectedVmIds.value.size === filteredVms.value.length
}

function openAddModal() {
  editingVm.value = null
  showVmModal.value = true
}

function openEditModal(vm) {
  editingVm.value = { ...vm }
  showVmModal.value = true
}

async function handleVmSave(vmData) {
  try {
    if (editingVm.value) {
      await vmsStore.updateVm(editingVm.value.id, vmData)
    } else {
      await vmsStore.createVm(vmData)
    }
    showVmModal.value = false
    editingVm.value = null
  } catch (e) {
    console.error('Erreur sauvegarde VM:', e)
  }
}

function openDeleteModal(vm) {
  vmToDelete.value = vm
  deleteOptions.value = { deleteAgent: false, deleteHostData: true }
  showDeleteModal.value = true
}

async function confirmDeleteVm() {
  if (!vmToDelete.value) return

  try {
    await vmsStore.deleteVm(vmToDelete.value.id, deleteOptions.value)
    selectedVmIds.value.delete(vmToDelete.value.id)
    showDeleteModal.value = false
    vmToDelete.value = null
  } catch (e) {
    console.error('Erreur suppression VM:', e)
  }
}

async function handleDeploy() {
  const ids = Array.from(selectedVmIds.value)
  if (ids.length === 0) return

  try {
    await vmsStore.deployAgent(ids)
    selectedVmIds.value = new Set()
  } catch (e) {
    console.error('Erreur deploiement:', e)
  }
}

async function deploySingleVm(vm) {
  try {
    await vmsStore.deployAgent([vm.id])
  } catch (e) {
    console.error('Erreur deploiement:', e)
  }
}

async function handleAgentAction(action) {
  const ids = Array.from(selectedVmIds.value)
  if (ids.length === 0) return

  const actionLabels = {
    start: 'Demarrer',
    stop: 'Arreter',
    restart: 'Redemarrer',
    update: 'Mettre a jour',
    delete: 'Supprimer',
  }

  if (action === 'delete' && !confirm('Supprimer les agents selectionnees ?')) {
    return
  }

  try {
    await vmsStore.agentAction(ids, action)
    if (action === 'delete') {
      selectedVmIds.value = new Set()
    }
  } catch (e) {
    console.error(`Erreur action ${action}:`, e)
  }
}

const logsVmIsAutoDiscovered = ref(false)

function openAgentLogs(vm) {
  logsVmId.value = vm.id
  logsVmIsAutoDiscovered.value = vm.is_auto_discovered || false
  showAgentLogsModal.value = true
}

function getStatusClass(status) {
  switch (status) {
    case 'online':
      return 'bg-green-500/20 text-green-400'
    case 'offline':
      return 'bg-red-500/20 text-red-400'
    case 'pending':
      return 'bg-yellow-500/20 text-yellow-400'
    case 'deploying':
      return 'bg-blue-500/20 text-blue-400'
    case 'error':
      return 'bg-red-500/20 text-red-400'
    default:
      return 'bg-gray-500/20 text-gray-400'
  }
}

function getOsIcon(osType) {
  switch (osType) {
    case 'debian':
    case 'ubuntu':
      return '🐧'
    case 'centos':
      return '🎩'
    case 'macos':
      return '🍎'
    case 'windows':
      return '🪟'
    default:
      return '💻'
  }
}

// Deployment progress helpers
function getDeployProgress(vmId) {
  return deploymentProgress.value[vmId]?.progress || 0
}

function getDeployStep(vmId) {
  const steps = {
    preparing: 'Preparation...',
    detecting_os: 'Detection OS...',
    checking_docker: 'Verification Docker...',
    uploading: 'Upload fichiers...',
    creating_config: 'Configuration...',
    building: 'Build Docker...',
    starting: 'Demarrage...',
    verifying: 'Verification...',
    error: 'Erreur'
  }
  const step = deploymentProgress.value[vmId]?.step
  return steps[step] || 'Deploiement...'
}

function getDeployMessage(vmId) {
  return deploymentProgress.value[vmId]?.message || ''
}

onMounted(() => {
  vmsStore.fetchVms()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white">
    <!-- Header -->
    <header class="flex items-center justify-between p-4 border-b border-gray-700">
      <h1 class="text-xl font-bold">Gestion des VMs / Agents</h1>

      <div class="flex items-center gap-4">
        <!-- Search -->
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Rechercher..."
          class="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
        />

        <!-- Filter by status -->
        <select
          v-model="filterStatus"
          class="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
        >
          <option value="all">Tous les statuts</option>
          <option value="online">En ligne</option>
          <option value="offline">Hors ligne</option>
          <option value="pending">En attente</option>
          <option value="deploying">Deploiement</option>
          <option value="error">Erreur</option>
        </select>

        <!-- SSH Key button -->
        <button
          @click="showSshKeyModal = true"
          class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium flex items-center gap-2"
          title="Gestion des cles SSH"
        >
          <span>🔑</span>
          SSH
        </button>

        <!-- Add VM button -->
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium flex items-center gap-2"
        >
          <span>+</span>
          Ajouter VM
        </button>
      </div>
    </header>

    <!-- Action bar -->
    <div
      v-if="selectedVmIds.size > 0"
      class="flex items-center gap-4 p-4 bg-gray-800 border-b border-gray-700"
    >
      <span class="text-sm text-gray-400">
        {{ selectedVmIds.size }} VM(s) selectionnee(s)
      </span>

      <div class="flex gap-2">
        <button
          v-if="canDeploy"
          @click="handleDeploy"
          :disabled="actionInProgress"
          class="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm"
        >
          Deployer Agent
        </button>

        <button
          v-if="canStart"
          @click="handleAgentAction('start')"
          :disabled="actionInProgress"
          class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm"
        >
          Demarrer
        </button>

        <button
          v-if="canStop"
          @click="handleAgentAction('stop')"
          :disabled="actionInProgress"
          class="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm"
        >
          Arreter
        </button>

        <button
          @click="handleAgentAction('update')"
          :disabled="actionInProgress"
          class="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm"
        >
          Mettre a jour
        </button>

        <button
          @click="handleAgentAction('delete')"
          :disabled="actionInProgress"
          class="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm"
        >
          Supprimer Agent
        </button>
      </div>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading && vms.length === 0" class="flex-1 flex items-center justify-center">
      <div class="text-gray-400">Chargement...</div>
    </div>

    <div v-else-if="error" class="flex-1 flex items-center justify-center">
      <div class="text-red-400">{{ error }}</div>
    </div>

    <!-- Table -->
    <div v-else class="flex-1 overflow-auto">
      <table class="w-full">
        <thead class="bg-gray-800 sticky top-0">
          <tr>
            <th class="w-12 p-3 text-left">
              <input
                type="checkbox"
                :checked="selectAll"
                @change="toggleSelectAll"
                class="rounded bg-gray-700 border-gray-600"
              />
            </th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">Nom</th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">Hostname</th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">IP</th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">OS</th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">Statut</th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">Agent</th>
            <th class="p-3 text-left text-sm font-medium text-gray-400">Tags</th>
            <th class="w-32 p-3 text-left text-sm font-medium text-gray-400">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="vm in filteredVms"
            :key="vm.id"
            class="border-b border-gray-800 hover:bg-gray-800/50"
            :class="{ 'bg-blue-900/20': selectedVmIds.has(vm.id) }"
          >
            <td class="p-3">
              <input
                type="checkbox"
                :checked="selectedVmIds.has(vm.id)"
                @change="toggleSelect(vm.id)"
                class="rounded bg-gray-700 border-gray-600"
              />
            </td>
            <td class="p-3">
              <div class="flex items-center gap-2">
                <span>{{ vm.name }}</span>
                <span
                  v-if="vm.is_auto_discovered"
                  class="px-1.5 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded"
                  title="Decouverte automatique"
                >
                  Auto
                </span>
              </div>
            </td>
            <td class="p-3 font-mono text-sm">{{ vm.hostname }}</td>
            <td class="p-3 font-mono text-sm">{{ vm.ip_address }}:{{ vm.ssh_port }}</td>
            <td class="p-3">
              <span :title="vm.os_type">{{ getOsIcon(vm.os_type) }}</span>
            </td>
            <td class="p-3">
              <span
                class="px-2 py-1 rounded text-xs font-medium"
                :class="getStatusClass(vm.status)"
              >
                {{ vm.status }}
              </span>
            </td>
            <td class="p-3 text-sm text-gray-400">
              <!-- Deployment progress -->
              <template v-if="vm.status === 'deploying'">
                <div class="flex flex-col gap-1">
                  <div class="flex items-center gap-2">
                    <div class="w-24 h-2 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-blue-500 transition-all duration-300"
                        :style="{ width: getDeployProgress(vm.id) + '%' }"
                      ></div>
                    </div>
                    <span class="text-xs text-gray-400">{{ getDeployProgress(vm.id) }}%</span>
                  </div>
                  <span class="text-xs text-gray-500">{{ getDeployStep(vm.id) }}</span>
                </div>
              </template>
              <!-- Error with message -->
              <template v-else-if="vm.status === 'error' && getDeployMessage(vm.id)">
                <div class="flex flex-col gap-1">
                  <span class="text-xs text-red-400">Echec</span>
                  <span class="text-xs text-gray-500 truncate max-w-[150px]" :title="getDeployMessage(vm.id)">
                    {{ getDeployMessage(vm.id) }}
                  </span>
                </div>
              </template>
              <!-- Normal display -->
              <template v-else-if="vm.agent_version">
                v{{ vm.agent_version }}
              </template>
              <template v-else>
                -
              </template>
            </td>
            <td class="p-3">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in vm.tags"
                  :key="tag"
                  class="px-1.5 py-0.5 bg-gray-700 text-xs rounded"
                >
                  {{ tag }}
                </span>
              </div>
            </td>
            <td class="p-3">
              <div class="flex items-center gap-1">
                <button
                  v-if="vm.status === 'pending' || vm.status === 'offline'"
                  @click="deploySingleVm(vm)"
                  :disabled="actionInProgress"
                  class="p-1.5 hover:bg-green-700 bg-green-600 rounded disabled:opacity-50"
                  title="Deployer l'agent"
                >
                  🚀
                </button>
                <button
                  @click="openEditModal(vm)"
                  class="p-1.5 hover:bg-gray-700 rounded"
                  title="Modifier"
                >
                  ✏️
                </button>
                <button
                  v-if="vm.status === 'online'"
                  @click="openAgentLogs(vm)"
                  class="p-1.5 hover:bg-gray-700 rounded"
                  :class="{ 'opacity-50': vm.is_auto_discovered }"
                  :title="vm.is_auto_discovered ? 'Logs agent (SSH non configure)' : 'Voir les logs'"
                >
                  📋
                </button>
                <button
                  @click="openDeleteModal(vm)"
                  class="p-1.5 hover:bg-gray-700 rounded text-red-400"
                  title="Supprimer"
                >
                  🗑️
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Empty state -->
      <div
        v-if="filteredVms.length === 0"
        class="p-8 text-center text-gray-400"
      >
        <template v-if="vms.length === 0">
          Aucune VM enregistree. Cliquez sur "Ajouter VM" pour commencer.
        </template>
        <template v-else>
          Aucune VM ne correspond aux filtres.
        </template>
      </div>
    </div>

    <!-- Status bar -->
    <footer class="flex items-center justify-between p-3 bg-gray-800 border-t border-gray-700 text-sm text-gray-400">
      <div>
        {{ vms.length }} VM(s) au total
        <span v-if="vms.filter(v => v.status === 'online').length > 0">
          · {{ vms.filter(v => v.status === 'online').length }} en ligne
        </span>
      </div>
      <button
        @click="vmsStore.fetchVms()"
        :disabled="loading"
        class="px-3 py-1 hover:bg-gray-700 rounded disabled:opacity-50"
      >
        Rafraichir
      </button>
    </footer>

    <!-- Modals -->
    <VmModal
      v-if="showVmModal"
      :vm="editingVm"
      @save="handleVmSave"
      @close="showVmModal = false"
    />

    <AgentLogsModal
      v-if="showAgentLogsModal"
      :vm-id="logsVmId"
      :is-auto-discovered="logsVmIsAutoDiscovered"
      @close="showAgentLogsModal = false"
    />

    <SshKeyModal
      v-if="showSshKeyModal"
      @close="showSshKeyModal = false"
      @keyDeployed="vmsStore.fetchVms()"
    />

    <!-- Delete confirmation modal -->
    <div v-if="showDeleteModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold text-white mb-4">Supprimer la VM</h3>

        <p class="text-gray-300 mb-4">
          Voulez-vous vraiment supprimer la VM <span class="font-semibold text-white">{{ vmToDelete?.name }}</span> ?
        </p>

        <div class="space-y-3 mb-6">
          <label class="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              v-model="deleteOptions.deleteHostData"
              class="mt-1"
            />
            <div>
              <span class="text-white">Supprimer les donnees associees</span>
              <p class="text-sm text-gray-400">Containers, connexions et reseaux collectes</p>
            </div>
          </label>

          <label v-if="vmToDelete?.host_id" class="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              v-model="deleteOptions.deleteAgent"
              class="mt-1"
            />
            <div>
              <span class="text-white">Supprimer l'agent sur la VM</span>
              <p class="text-sm text-gray-400">Arrete et supprime le conteneur agent distant</p>
            </div>
          </label>
        </div>

        <div class="flex justify-end gap-3">
          <button
            @click="showDeleteModal = false; vmToDelete = null"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
          >
            Annuler
          </button>
          <button
            @click="confirmDeleteVm"
            class="px-4 py-2 bg-red-600 hover:bg-red-500 rounded text-white"
            :disabled="loading"
          >
            {{ loading ? 'Suppression...' : 'Supprimer' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
