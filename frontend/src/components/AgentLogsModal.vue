<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useVmsStore } from '../stores/vms'

const props = defineProps({
  vmId: {
    type: String,
    required: true,
  },
  isAutoDiscovered: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

const vmsStore = useVmsStore()

const logs = ref('')
const loading = ref(false)
const error = ref(null)
const lines = ref(100)
const autoScroll = ref(true)
const logsContainer = ref(null)

let refreshInterval = null

async function fetchLogs() {
  loading.value = true
  error.value = null

  try {
    const result = await vmsStore.getAgentLogs(props.vmId, lines.value)
    logs.value = result.logs || ''

    // Auto-scroll to bottom
    if (autoScroll.value) {
      await nextTick()
      if (logsContainer.value) {
        logsContainer.value.scrollTop = logsContainer.value.scrollHeight
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function handleScroll() {
  if (!logsContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = logsContainer.value
  // Auto-scroll is enabled if we're near the bottom
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 50
}

function startAutoRefresh() {
  refreshInterval = setInterval(fetchLogs, 5000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

function handleClose() {
  emit('close')
}

onMounted(() => {
  fetchLogs()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="handleClose">
    <div class="bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl h-[80vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-gray-700">
        <h2 class="text-lg font-semibold">Logs de l'agent</h2>

        <div class="flex items-center gap-4">
          <!-- Lines selector -->
          <select
            v-model.number="lines"
            @change="fetchLogs"
            class="px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
          >
            <option :value="50">50 lignes</option>
            <option :value="100">100 lignes</option>
            <option :value="200">200 lignes</option>
            <option :value="500">500 lignes</option>
          </select>

          <!-- Refresh button -->
          <button
            @click="fetchLogs"
            :disabled="loading"
            class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-sm flex items-center gap-2"
          >
            <span v-if="loading">...</span>
            <span v-else>Rafraichir</span>
          </button>

          <!-- Close button -->
          <button
            @click="handleClose"
            class="w-8 h-8 flex items-center justify-center hover:bg-gray-700 rounded"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- Logs content -->
      <div
        ref="logsContainer"
        @scroll="handleScroll"
        class="flex-1 overflow-auto p-4 bg-gray-900 font-mono text-sm"
      >
        <!-- Loading -->
        <div v-if="loading && !logs" class="text-gray-400">
          Chargement des logs...
        </div>

        <!-- Error -->
        <div v-else-if="error" class="text-center py-8">
          <div class="text-red-400 mb-4">
            Erreur: {{ error }}
          </div>
          <div v-if="props.isAutoDiscovered || error.includes('Permission denied') || error.includes('SSH')" class="text-gray-400 text-sm space-y-2">
            <p>Cette VM a été auto-découverte et l'accès SSH n'est pas configuré.</p>
            <p>Pour voir les logs de l'agent :</p>
            <ol class="text-left max-w-md mx-auto list-decimal list-inside space-y-1 mt-2">
              <li>Configurez l'accès SSH sur le backend</li>
              <li>Ou connectez-vous directement à la VM :</li>
            </ol>
            <code class="block mt-2 px-4 py-2 bg-gray-800 rounded text-xs text-green-400">
              ssh user@vm-ip "cd /opt/infra-mapper-agent && docker compose logs --tail=100"
            </code>
            <p class="mt-4 text-xs">Les logs des containers sont disponibles dans l'onglet "Graphe" → cliquez sur un container → onglet "Logs"</p>
          </div>
        </div>

        <!-- Empty -->
        <div v-else-if="!logs" class="text-gray-400">
          Aucun log disponible.
        </div>

        <!-- Logs -->
        <pre v-else class="whitespace-pre-wrap text-gray-300">{{ logs }}</pre>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between p-3 border-t border-gray-700 text-sm text-gray-400">
        <div class="flex items-center gap-2">
          <span
            class="w-2 h-2 rounded-full"
            :class="refreshInterval ? 'bg-green-500' : 'bg-gray-500'"
          ></span>
          <span>Auto-refresh: {{ refreshInterval ? 'ON' : 'OFF' }}</span>
        </div>

        <div class="flex items-center gap-2">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              v-model="autoScroll"
              class="rounded bg-gray-700 border-gray-600"
            />
            <span>Auto-scroll</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>
