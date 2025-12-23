<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useLogsStore } from '../stores/logs'

const props = defineProps({
  containerId: {
    type: String,
    required: true,
  },
})

const logsStore = useLogsStore()
const { logs, loading, error, total, currentContainerInfo, filters } = storeToRefs(logsStore)

const logsContainer = ref(null)
const autoScroll = ref(true)
const searchInput = ref('')
const streamFilter = ref(null)

// Watch for container changes
watch(() => props.containerId, (newId) => {
  if (newId) {
    logsStore.clearLogs()
    logsStore.fetchContainerLogs(newId)
  }
}, { immediate: true })

function handleScroll() {
  if (!logsContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = logsContainer.value
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 50

  // Load more when scrolling near bottom
  if (scrollHeight - scrollTop - clientHeight < 100) {
    logsStore.loadMoreLogs()
  }
}

function handleSearch() {
  logsStore.setSearch(searchInput.value)
}

function setStream(stream) {
  streamFilter.value = stream
  logsStore.setStream(stream)
}

function refresh() {
  logsStore.fetchContainerLogs(props.containerId)
}

function formatTimestamp(ts) {
  try {
    return new Date(ts).toLocaleString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts
  }
}

onUnmounted(() => {
  logsStore.clearLogs()
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between p-2 border-b border-gray-700">
      <h3 class="text-sm font-medium">Logs</h3>

      <div class="flex items-center gap-2">
        <!-- Stream filter -->
        <div class="flex text-xs">
          <button
            @click="setStream(null)"
            class="px-2 py-1 rounded-l"
            :class="streamFilter === null ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'"
          >
            Tous
          </button>
          <button
            @click="setStream('stdout')"
            class="px-2 py-1"
            :class="streamFilter === 'stdout' ? 'bg-green-600' : 'bg-gray-700 hover:bg-gray-600'"
          >
            stdout
          </button>
          <button
            @click="setStream('stderr')"
            class="px-2 py-1 rounded-r"
            :class="streamFilter === 'stderr' ? 'bg-red-600' : 'bg-gray-700 hover:bg-gray-600'"
          >
            stderr
          </button>
        </div>

        <!-- Refresh -->
        <button
          @click="refresh"
          :disabled="loading"
          class="p-1 hover:bg-gray-700 rounded disabled:opacity-50"
          title="Rafraichir"
        >
          🔄
        </button>
      </div>
    </div>

    <!-- Search -->
    <div class="p-2 border-b border-gray-700">
      <input
        v-model="searchInput"
        type="text"
        placeholder="Rechercher dans les logs..."
        class="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
        @keydown.enter="handleSearch"
      />
    </div>

    <!-- Logs content -->
    <div
      ref="logsContainer"
      @scroll="handleScroll"
      class="flex-1 overflow-auto p-2 bg-gray-900 font-mono text-xs"
    >
      <!-- Loading -->
      <div v-if="loading && logs.length === 0" class="text-gray-400 text-center py-4">
        Chargement...
      </div>

      <!-- Error -->
      <div v-else-if="error" class="text-red-400 text-center py-4">
        {{ error }}
      </div>

      <!-- Empty -->
      <div v-else-if="logs.length === 0" class="text-gray-400 text-center py-4">
        Aucun log disponible.
      </div>

      <!-- Logs list -->
      <div v-else class="space-y-0.5">
        <div
          v-for="(log, idx) in logs"
          :key="idx"
          class="flex gap-2 hover:bg-gray-800 px-1 rounded"
        >
          <span class="text-gray-500 shrink-0">
            {{ formatTimestamp(log.timestamp) }}
          </span>
          <span
            class="shrink-0 w-12"
            :class="log.stream === 'stderr' ? 'text-red-400' : 'text-green-400'"
          >
            {{ log.stream }}
          </span>
          <span class="text-gray-300 break-all">{{ log.message }}</span>
        </div>
      </div>

      <!-- Load more indicator -->
      <div v-if="loading && logs.length > 0" class="text-center py-2 text-gray-400">
        Chargement...
      </div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between p-2 border-t border-gray-700 text-xs text-gray-400">
      <span>{{ logs.length }} / {{ total }} logs</span>
      <label class="flex items-center gap-1 cursor-pointer">
        <input
          type="checkbox"
          v-model="autoScroll"
          class="rounded bg-gray-700 border-gray-600"
        />
        <span>Auto-scroll</span>
      </label>
    </div>
  </div>
</template>
