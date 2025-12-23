<script setup>
import { ref, computed, watch } from 'vue'
import ContainerLogsPanel from './ContainerLogsPanel.vue'

const API_BASE = import.meta.env.VITE_API_URL || ''

const props = defineProps({
  node: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['close'])

const activeTab = ref('details')  // 'details', 'logs', or 'actions'

// Reset tab when node changes
watch(() => props.node?.id, () => {
  activeTab.value = 'details'
})

// Computed properties
const isHost = computed(() => props.node.type === 'host')
const isContainer = computed(() => props.node.type === 'container')
const isExternal = computed(() => props.node.type === 'external')

// Get the container ID for API calls (format: host_id:container_id, without 'container:' prefix)
const containerIdForApi = computed(() => {
  if (!isContainer.value || !props.node.id) return null
  // The graph node ID is "container:host_id:docker_id", we need "host_id:docker_id"
  const id = props.node.id
  if (id.startsWith('container:')) {
    return id.substring('container:'.length)
  }
  return id
})

// Get the container ID for logs (same format as API)
const containerIdForLogs = computed(() => containerIdForApi.value)

// Container actions state
const actionLoading = ref(false)
const actionResult = ref(null)
const execCommand = ref('')
const execResult = ref(null)
const execLoading = ref(false)

// Container actions - use containerIdForApi which strips the 'container:' prefix
async function containerAction(action) {
  const containerId = containerIdForApi.value
  if (!containerId) return

  actionLoading.value = true
  actionResult.value = null

  try {
    const response = await fetch(`${API_BASE}/api/v1/containers/${containerId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    const data = await response.json()
    actionResult.value = data
  } catch (error) {
    actionResult.value = { success: false, error: error.message }
  } finally {
    actionLoading.value = false
  }
}

async function execInContainer() {
  const containerId = containerIdForApi.value
  if (!containerId || !execCommand.value.trim()) return

  execLoading.value = true
  execResult.value = null

  try {
    const response = await fetch(`${API_BASE}/api/v1/containers/${containerId}/exec`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: execCommand.value,
        timeout: 30
      })
    })
    execResult.value = await response.json()
  } catch (error) {
    execResult.value = { success: false, error: error.message }
  } finally {
    execLoading.value = false
  }
}

const statusClass = computed(() => {
  const status = props.node.status
  if (status === 'running') return 'bg-green-500/20 text-green-400'
  if (status === 'exited' || status === 'stopped') return 'bg-red-500/20 text-red-400'
  if (status === 'paused') return 'bg-yellow-500/20 text-yellow-400'
  return 'bg-gray-500/20 text-gray-400'
})

const healthClass = computed(() => {
  const health = props.node.health
  if (health === 'healthy') return 'bg-green-500/20 text-green-400'
  if (health === 'unhealthy') return 'bg-red-500/20 text-red-400'
  if (health === 'starting') return 'bg-yellow-500/20 text-yellow-400'
  return 'bg-gray-500/20 text-gray-400'
})

// Ports exposes sur 0.0.0.0 (IPv4 uniquement)
const exposedPorts = computed(() => {
  const ports = props.node.ports || []
  return ports
    .filter(p => p.host_ip === '0.0.0.0' && p.host_port)
    .map(p => p.host_port)
})
</script>

<template>
  <aside class="w-96 bg-gray-800 border-l border-gray-700 flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between p-4 border-b border-gray-700 shrink-0">
      <h2 class="font-semibold truncate">{{ node.label }}</h2>
      <button
        @click="emit('close')"
        class="w-8 h-8 flex items-center justify-center hover:bg-gray-700 rounded"
      >
        x
      </button>
    </div>

    <!-- Tabs for containers -->
    <div v-if="isContainer" class="flex border-b border-gray-700 shrink-0">
      <button
        @click="activeTab = 'details'"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'details'
          ? 'text-white border-b-2 border-blue-500 bg-gray-900'
          : 'text-gray-400 hover:text-white hover:bg-gray-700'"
      >
        Details
      </button>
      <button
        @click="activeTab = 'logs'"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'logs'
          ? 'text-white border-b-2 border-blue-500 bg-gray-900'
          : 'text-gray-400 hover:text-white hover:bg-gray-700'"
      >
        Logs
      </button>
      <button
        @click="activeTab = 'actions'"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'actions'
          ? 'text-white border-b-2 border-blue-500 bg-gray-900'
          : 'text-gray-400 hover:text-white hover:bg-gray-700'"
      >
        Actions
      </button>
    </div>

    <!-- Details tab -->
    <div v-if="activeTab === 'details'" class="flex-1 overflow-y-auto p-4 space-y-4">
      <!-- Type badge -->
      <div>
        <span
          class="px-2 py-1 rounded text-xs font-medium"
          :class="{
            'bg-blue-500/20 text-blue-400': isHost,
            'bg-green-500/20 text-green-400': isContainer,
            'bg-purple-500/20 text-purple-400': isExternal,
          }"
        >
          {{ isHost ? 'Hote' : isContainer ? 'Conteneur' : 'Externe' }}
        </span>
      </div>

      <!-- Details Host -->
      <template v-if="isHost">
        <div>
          <div class="text-xs text-gray-400 mb-1">Hostname</div>
          <div class="text-sm">{{ node.hostname }}</div>
        </div>

        <div v-if="node.ip_addresses?.length">
          <div class="text-xs text-gray-400 mb-1">IPs</div>
          <div class="space-y-1">
            <div v-for="ip in node.ip_addresses" :key="ip" class="text-sm font-mono">
              {{ ip }}
            </div>
          </div>
        </div>

        <div v-if="node.tailscale_ip">
          <div class="text-xs text-gray-400 mb-1">IP Tailscale</div>
          <div class="text-sm font-mono text-cyan-400">{{ node.tailscale_ip }}</div>
        </div>

        <div v-if="node.docker_version">
          <div class="text-xs text-gray-400 mb-1">Docker</div>
          <div class="text-sm">{{ node.docker_version }}</div>
        </div>

        <div>
          <div class="text-xs text-gray-400 mb-1">Conteneurs</div>
          <div class="text-sm">{{ node.container_count }} conteneur(s)</div>
        </div>

        <div>
          <div class="text-xs text-gray-400 mb-1">Statut</div>
          <span
            class="px-2 py-0.5 rounded text-xs"
            :class="node.is_online ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'"
          >
            {{ node.is_online ? 'En ligne' : 'Hors ligne' }}
          </span>
        </div>
      </template>

      <!-- Details Container -->
      <template v-if="isContainer">
        <div>
          <div class="text-xs text-gray-400 mb-1">ID</div>
          <div class="text-sm font-mono">{{ node.container_id }}</div>
        </div>

        <div v-if="node.hostname">
          <div class="text-xs text-gray-400 mb-1">VM</div>
          <div class="text-sm">{{ node.hostname }}</div>
        </div>

        <div v-if="exposedPorts.length">
          <div class="text-xs text-gray-400 mb-1">Ports exposes</div>
          <div class="text-sm font-mono text-cyan-400">{{ exposedPorts.join(', ') }}</div>
        </div>

        <div>
          <div class="text-xs text-gray-400 mb-1">Image</div>
          <div class="text-sm font-mono truncate" :title="node.image">
            {{ node.image }}
          </div>
        </div>

        <div class="flex gap-2">
          <div>
            <div class="text-xs text-gray-400 mb-1">Statut</div>
            <span class="px-2 py-0.5 rounded text-xs" :class="statusClass">
              {{ node.status }}
            </span>
          </div>
          <div v-if="node.health && node.health !== 'none'">
            <div class="text-xs text-gray-400 mb-1">Sante</div>
            <span class="px-2 py-0.5 rounded text-xs" :class="healthClass">
              {{ node.health }}
            </span>
          </div>
        </div>

        <div v-if="node.compose_project">
          <div class="text-xs text-gray-400 mb-1">Projet Compose</div>
          <div class="text-sm">
            {{ node.compose_project }}
            <span v-if="node.compose_service" class="text-gray-400">
              / {{ node.compose_service }}
            </span>
          </div>
        </div>

        <div v-if="node.ports?.length">
          <div class="text-xs text-gray-400 mb-1">Ports</div>
          <div class="space-y-1">
            <div
              v-for="(port, idx) in node.ports"
              :key="idx"
              class="text-sm font-mono"
            >
              <span v-if="port.host_port">{{ port.host_port }} -> </span>
              {{ port.container_port }}/{{ port.protocol }}
            </div>
          </div>
        </div>

        <div v-if="node.networks?.length">
          <div class="text-xs text-gray-400 mb-1">Reseaux</div>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="net in node.networks"
              :key="net"
              class="px-2 py-0.5 bg-gray-700 rounded text-xs"
            >
              {{ net }}
            </span>
          </div>
        </div>
      </template>

      <!-- Details External -->
      <template v-if="isExternal">
        <div>
          <div class="text-xs text-gray-400 mb-1">IP</div>
          <div class="text-sm font-mono">{{ node.ip }}</div>
        </div>
      </template>

      <!-- Derniere vue -->
      <div v-if="node.last_seen" class="pt-4 border-t border-gray-700">
        <div class="text-xs text-gray-400 mb-1">Derniere activite</div>
        <div class="text-sm text-gray-300">
          {{ new Date(node.last_seen).toLocaleString('fr-FR') }}
        </div>
      </div>
    </div>

    <!-- Logs tab (containers only) -->
    <div v-if="activeTab === 'logs' && isContainer" class="flex-1 overflow-hidden">
      <ContainerLogsPanel
        v-if="containerIdForLogs"
        :container-id="containerIdForLogs"
      />
    </div>

    <!-- Actions tab (containers only) -->
    <div v-if="activeTab === 'actions' && isContainer" class="flex-1 overflow-y-auto p-4 space-y-6">
      <!-- Container controls -->
      <div>
        <h3 class="text-sm font-medium text-gray-300 mb-3">Controle du container</h3>
        <div class="flex gap-2">
          <button
            @click="containerAction('start')"
            :disabled="actionLoading || node.status === 'running'"
            class="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors"
          >
            Start
          </button>
          <button
            @click="containerAction('stop')"
            :disabled="actionLoading || node.status !== 'running'"
            class="flex-1 px-3 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors"
          >
            Stop
          </button>
          <button
            @click="containerAction('restart')"
            :disabled="actionLoading"
            class="flex-1 px-3 py-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors"
          >
            Restart
          </button>
        </div>

        <!-- Action result -->
        <div v-if="actionResult" class="mt-3 p-3 rounded text-sm" :class="actionResult.success ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'">
          <span v-if="actionResult.success">{{ actionResult.message }}</span>
          <span v-else>Erreur: {{ actionResult.error }}</span>
        </div>

        <div v-if="actionLoading" class="mt-3 text-sm text-gray-400">
          Execution en cours...
        </div>
      </div>

      <!-- Exec command -->
      <div>
        <h3 class="text-sm font-medium text-gray-300 mb-3">Executer une commande</h3>
        <div class="space-y-2">
          <input
            v-model="execCommand"
            @keyup.enter="execInContainer"
            type="text"
            placeholder="Ex: ls -la, cat /etc/hostname"
            class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
            :disabled="execLoading || node.status !== 'running'"
          />
          <button
            @click="execInContainer"
            :disabled="execLoading || !execCommand.trim() || node.status !== 'running'"
            class="w-full px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors"
          >
            {{ execLoading ? 'Execution...' : 'Executer' }}
          </button>
        </div>

        <!-- Exec result -->
        <div v-if="execResult" class="mt-3 space-y-2">
          <div v-if="execResult.success" class="space-y-2">
            <div class="text-xs text-gray-400">
              Code de sortie: <span :class="execResult.exit_code === 0 ? 'text-green-400' : 'text-red-400'">{{ execResult.exit_code }}</span>
            </div>
            <div v-if="execResult.stdout" class="bg-gray-900 p-3 rounded max-h-48 overflow-auto">
              <pre class="text-xs text-gray-300 whitespace-pre-wrap break-all">{{ execResult.stdout }}</pre>
            </div>
            <div v-if="execResult.stderr" class="bg-red-900/30 p-3 rounded max-h-48 overflow-auto">
              <pre class="text-xs text-red-300 whitespace-pre-wrap break-all">{{ execResult.stderr }}</pre>
            </div>
          </div>
          <div v-else class="p-3 bg-red-500/20 rounded text-sm text-red-400">
            Erreur: {{ execResult.error }}
          </div>
        </div>

        <p v-if="node.status !== 'running'" class="mt-2 text-xs text-gray-500">
          Le container doit etre en cours d'execution pour executer des commandes.
        </p>
      </div>
    </div>
  </aside>
</template>
