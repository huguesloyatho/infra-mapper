<script setup>
import { ref, computed, onMounted } from 'vue'

// State
const loading = ref(false)
const error = ref(null)
const successMessage = ref(null)

// Data
const sinks = ref([])
const sinkTypes = ref([])

// Modal
const showModal = ref(false)
const editingSink = ref(null)
const testing = ref(null)

// Form
const sinkForm = ref({
  name: '',
  type: 'graylog',
  url: '',
  port: null,
  auth_type: 'none',
  username: '',
  password: '',
  api_key: '',
  token: '',
  config: {},
  filter_hosts: [],
  filter_containers: [],
  filter_streams: [],
  tls_enabled: false,
  tls_verify: true,
  batch_size: 100,
  flush_interval: 5,
  enabled: true,
})

// Current sink type info
const currentSinkType = computed(() => {
  return sinkTypes.value.find(t => t.id === sinkForm.value.type)
})

// Available auth types for current sink type
const availableAuthTypes = computed(() => {
  const type = currentSinkType.value
  if (!type) return ['none']
  return type.auth_types || ['none']
})

// Config fields for current sink type
const configFields = computed(() => {
  const type = currentSinkType.value
  if (!type) return []
  return type.config_fields || []
})

// Fetch sink types
async function fetchSinkTypes() {
  try {
    const response = await fetch('/api/v1/log-sinks/types')
    if (response.ok) {
      const data = await response.json()
      sinkTypes.value = data.types
    }
  } catch (e) {
    console.error('Erreur chargement types:', e)
  }
}

// Fetch sinks
async function fetchSinks() {
  loading.value = true
  error.value = null
  try {
    const response = await fetch('/api/v1/log-sinks')
    if (response.ok) {
      sinks.value = await response.json()
    } else {
      throw new Error('Erreur chargement sinks')
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Open create modal
function openCreateModal() {
  editingSink.value = null
  sinkForm.value = {
    name: '',
    type: 'graylog',
    url: '',
    port: null,
    auth_type: 'none',
    username: '',
    password: '',
    api_key: '',
    token: '',
    config: {},
    filter_hosts: [],
    filter_containers: [],
    filter_streams: [],
    tls_enabled: false,
    tls_verify: true,
    batch_size: 100,
    flush_interval: 5,
    enabled: true,
  }
  showModal.value = true
}

// Open edit modal
function openEditModal(sink) {
  editingSink.value = sink
  sinkForm.value = {
    name: sink.name,
    type: sink.type,
    url: sink.url,
    port: sink.port,
    auth_type: sink.auth_type || 'none',
    username: sink.username || '',
    password: '',
    api_key: '',
    token: '',
    config: { ...sink.config },
    filter_hosts: [...(sink.filter_hosts || [])],
    filter_containers: [...(sink.filter_containers || [])],
    filter_streams: [...(sink.filter_streams || [])],
    tls_enabled: sink.tls_enabled,
    tls_verify: sink.tls_verify,
    batch_size: sink.batch_size,
    flush_interval: sink.flush_interval,
    enabled: sink.enabled,
  }
  showModal.value = true
}

// Close modal
function closeModal() {
  showModal.value = false
  editingSink.value = null
}

// Save sink
async function saveSink() {
  loading.value = true
  error.value = null
  successMessage.value = null

  try {
    const url = editingSink.value
      ? `/api/v1/log-sinks/${editingSink.value.id}`
      : '/api/v1/log-sinks'
    const method = editingSink.value ? 'PUT' : 'POST'

    // Build payload
    const payload = { ...sinkForm.value }

    // Set default port if not specified
    if (!payload.port && currentSinkType.value?.default_port) {
      payload.port = currentSinkType.value.default_port
    }

    // Clean up empty auth fields
    if (payload.auth_type === 'none') {
      delete payload.username
      delete payload.password
      delete payload.api_key
      delete payload.token
    } else if (payload.auth_type === 'basic') {
      delete payload.api_key
      delete payload.token
    } else if (payload.auth_type === 'token') {
      delete payload.username
      delete payload.password
      delete payload.api_key
    } else if (payload.auth_type === 'api_key') {
      delete payload.username
      delete payload.password
      delete payload.token
    }

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur sauvegarde')
    }

    successMessage.value = editingSink.value ? 'Puits mis a jour' : 'Puits cree'
    closeModal()
    await fetchSinks()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Delete sink
async function deleteSink(sink) {
  if (!confirm(`Supprimer le puits "${sink.name}" ?`)) return

  loading.value = true
  error.value = null
  try {
    const response = await fetch(`/api/v1/log-sinks/${sink.id}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('Erreur suppression')
    successMessage.value = 'Puits supprime'
    await fetchSinks()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Toggle sink
async function toggleSink(sink) {
  try {
    const response = await fetch(`/api/v1/log-sinks/${sink.id}/toggle`, { method: 'POST' })
    if (!response.ok) throw new Error('Erreur toggle')
    await fetchSinks()
  } catch (e) {
    error.value = e.message
  }
}

// Test sink
async function testSink(sink) {
  testing.value = sink.id
  error.value = null
  successMessage.value = null

  try {
    const response = await fetch(`/api/v1/log-sinks/${sink.id}/test`, { method: 'POST' })
    const result = await response.json()

    if (result.success) {
      successMessage.value = `Test reussi pour "${sink.name}"`
    } else {
      error.value = `Test echoue: ${result.error}`
    }
    await fetchSinks()
  } catch (e) {
    error.value = e.message
  } finally {
    testing.value = null
  }
}

// Reset stats
async function resetStats(sink) {
  try {
    await fetch(`/api/v1/log-sinks/${sink.id}/reset-stats`, { method: 'POST' })
    await fetchSinks()
    successMessage.value = 'Statistiques reinitialisees'
  } catch (e) {
    error.value = e.message
  }
}

// Format number
function formatNumber(n) {
  if (n === null || n === undefined) return '0'
  return n.toLocaleString()
}

// Format date
function formatDate(isoString) {
  if (!isoString) return 'Jamais'
  const date = new Date(isoString)
  return date.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Get sink type label
function getSinkTypeLabel(type) {
  const found = sinkTypes.value.find(t => t.id === type)
  return found?.name || type
}

// On type change
function onTypeChange() {
  // Reset config with defaults
  const type = currentSinkType.value
  if (type) {
    sinkForm.value.config = {}
    type.config_fields?.forEach(field => {
      if (field.default !== undefined) {
        sinkForm.value.config[field.name] = field.default
      }
    })
    // Set default port
    if (type.default_port) {
      sinkForm.value.port = type.default_port
    }
    // Set default auth type
    if (type.auth_types?.length > 0) {
      sinkForm.value.auth_type = type.auth_types[0]
    }
  }
}

// Initial load
onMounted(async () => {
  await fetchSinkTypes()
  await fetchSinks()
})
</script>

<template>
  <div class="h-full overflow-auto bg-gray-900 text-white p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-semibold">Puits de Logs</h1>
        <p class="text-sm text-gray-400 mt-1">
          Configurez l'envoi des logs vers des systemes externes (Graylog, Loki, OpenObserve...)
        </p>
      </div>
      <button
        @click="openCreateModal"
        class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Ajouter un puits
      </button>
    </div>

    <!-- Messages -->
    <div v-if="error" class="mb-4 p-3 bg-red-900/50 border border-red-700 rounded text-red-300 text-sm">
      {{ error }}
    </div>
    <div v-if="successMessage" class="mb-4 p-3 bg-green-900/50 border border-green-700 rounded text-green-300 text-sm">
      {{ successMessage }}
    </div>

    <!-- Loading -->
    <div v-if="loading && sinks.length === 0" class="text-center py-12 text-gray-400">
      Chargement...
    </div>

    <!-- Empty state -->
    <div v-else-if="sinks.length === 0" class="text-center py-12 text-gray-500">
      <svg class="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
      </svg>
      <p>Aucun puits de logs configure</p>
      <p class="text-sm mt-2">Cliquez sur "Ajouter un puits" pour commencer</p>
    </div>

    <!-- Sinks list -->
    <div v-else class="space-y-4">
      <div
        v-for="sink in sinks"
        :key="sink.id"
        class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden"
      >
        <!-- Header -->
        <div class="p-4 flex items-center justify-between">
          <div class="flex items-center gap-4">
            <!-- Status indicator -->
            <div
              :class="sink.enabled ? 'bg-green-500' : 'bg-gray-600'"
              class="w-3 h-3 rounded-full"
            ></div>

            <!-- Info -->
            <div>
              <h3 class="font-medium flex items-center gap-2">
                {{ sink.name }}
                <span class="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">
                  {{ getSinkTypeLabel(sink.type) }}
                </span>
              </h3>
              <p class="text-sm text-gray-400">{{ sink.url }}{{ sink.port ? ':' + sink.port : '' }}</p>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2">
            <button
              @click="testSink(sink)"
              :disabled="testing === sink.id"
              class="px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50"
            >
              {{ testing === sink.id ? 'Test...' : 'Tester' }}
            </button>
            <button
              @click="toggleSink(sink)"
              :class="sink.enabled ? 'bg-yellow-600 hover:bg-yellow-700' : 'bg-green-600 hover:bg-green-700'"
              class="px-3 py-1.5 text-sm rounded"
            >
              {{ sink.enabled ? 'Desactiver' : 'Activer' }}
            </button>
            <button
              @click="openEditModal(sink)"
              class="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 rounded"
            >
              Modifier
            </button>
            <button
              @click="deleteSink(sink)"
              class="px-3 py-1.5 text-sm bg-red-600 hover:bg-red-700 rounded"
            >
              Supprimer
            </button>
          </div>
        </div>

        <!-- Stats -->
        <div class="px-4 pb-4 grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <span class="text-gray-400">Logs envoyes:</span>
            <span class="ml-2 text-green-400 font-medium">{{ formatNumber(sink.logs_sent) }}</span>
          </div>
          <div>
            <span class="text-gray-400">Erreurs:</span>
            <span class="ml-2" :class="sink.errors_count > 0 ? 'text-red-400' : 'text-gray-300'">
              {{ formatNumber(sink.errors_count) }}
            </span>
          </div>
          <div>
            <span class="text-gray-400">Dernier succes:</span>
            <span class="ml-2 text-gray-300">{{ formatDate(sink.last_success) }}</span>
          </div>
          <div>
            <span class="text-gray-400">Derniere erreur:</span>
            <span class="ml-2" :class="sink.last_error ? 'text-red-400' : 'text-gray-300'">
              {{ formatDate(sink.last_error) }}
            </span>
          </div>
          <div class="flex justify-end">
            <button
              @click="resetStats(sink)"
              class="text-xs text-gray-500 hover:text-gray-300"
            >
              Reset stats
            </button>
          </div>
        </div>

        <!-- Error message -->
        <div v-if="sink.last_error_message" class="px-4 pb-4">
          <div class="text-xs text-red-400 bg-red-900/30 rounded p-2">
            {{ sink.last_error_message }}
          </div>
        </div>

        <!-- Filters info -->
        <div v-if="sink.filter_streams?.length || sink.filter_hosts?.length" class="px-4 pb-4 flex gap-4 text-xs">
          <div v-if="sink.filter_streams?.length" class="text-gray-400">
            Streams: <span class="text-gray-300">{{ sink.filter_streams.join(', ') }}</span>
          </div>
          <div v-if="sink.filter_hosts?.length" class="text-gray-400">
            Hosts: <span class="text-gray-300">{{ sink.filter_hosts.length }} selectionnes</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <div
      v-if="showModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="closeModal"
    >
      <div class="bg-gray-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-auto">
        <!-- Modal header -->
        <div class="p-4 border-b border-gray-700 flex items-center justify-between">
          <h2 class="text-lg font-medium">
            {{ editingSink ? 'Modifier le puits' : 'Nouveau puits de logs' }}
          </h2>
          <button @click="closeModal" class="text-gray-400 hover:text-white">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Modal body -->
        <form @submit.prevent="saveSink" class="p-4 space-y-4">
          <!-- Basic info -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Nom</label>
              <input
                v-model="sinkForm.name"
                type="text"
                required
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                placeholder="Mon serveur Graylog"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Type</label>
              <select
                v-model="sinkForm.type"
                @change="onTypeChange"
                :disabled="editingSink"
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm disabled:opacity-50"
              >
                <option v-for="type in sinkTypes" :key="type.id" :value="type.id">
                  {{ type.name }}
                </option>
              </select>
              <p v-if="currentSinkType" class="text-xs text-gray-500 mt-1">
                {{ currentSinkType.description }}
              </p>
            </div>
          </div>

          <!-- Connection -->
          <div class="grid grid-cols-3 gap-4">
            <div class="col-span-2">
              <label class="block text-sm text-gray-400 mb-1">URL / Host</label>
              <input
                v-model="sinkForm.url"
                type="text"
                required
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                placeholder="https://graylog.example.com"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Port</label>
              <input
                v-model.number="sinkForm.port"
                type="number"
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                :placeholder="currentSinkType?.default_port || ''"
              />
            </div>
          </div>

          <!-- Auth -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Authentification</label>
              <select
                v-model="sinkForm.auth_type"
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
              >
                <option v-for="auth in availableAuthTypes" :key="auth" :value="auth">
                  {{ auth === 'none' ? 'Aucune' : auth === 'basic' ? 'Basic Auth' : auth === 'token' ? 'Bearer Token' : 'API Key' }}
                </option>
              </select>
            </div>
            <div v-if="sinkForm.auth_type === 'basic'">
              <label class="block text-sm text-gray-400 mb-1">Utilisateur</label>
              <input
                v-model="sinkForm.username"
                type="text"
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div v-if="sinkForm.auth_type === 'basic'" class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Mot de passe</label>
              <input
                v-model="sinkForm.password"
                type="password"
                class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                :placeholder="editingSink ? '(inchange)' : ''"
              />
            </div>
          </div>

          <div v-if="sinkForm.auth_type === 'token'">
            <label class="block text-sm text-gray-400 mb-1">Token</label>
            <input
              v-model="sinkForm.token"
              type="password"
              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
              :placeholder="editingSink ? '(inchange)' : ''"
            />
          </div>

          <div v-if="sinkForm.auth_type === 'api_key'">
            <label class="block text-sm text-gray-400 mb-1">API Key</label>
            <input
              v-model="sinkForm.api_key"
              type="password"
              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
              :placeholder="editingSink ? '(inchange)' : ''"
            />
          </div>

          <!-- Config fields -->
          <div v-if="configFields.length > 0" class="border-t border-gray-700 pt-4">
            <h3 class="text-sm font-medium text-gray-300 mb-3">Configuration specifique</h3>
            <div class="grid grid-cols-2 gap-4">
              <div v-for="field in configFields" :key="field.name">
                <label class="block text-sm text-gray-400 mb-1">{{ field.name }}</label>
                <select
                  v-if="field.type === 'select'"
                  v-model="sinkForm.config[field.name]"
                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                >
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
                <input
                  v-else-if="field.type === 'number'"
                  v-model.number="sinkForm.config[field.name]"
                  type="number"
                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                />
                <input
                  v-else-if="field.type === 'boolean'"
                  v-model="sinkForm.config[field.name]"
                  type="checkbox"
                  class="w-4 h-4"
                />
                <input
                  v-else
                  v-model="sinkForm.config[field.name]"
                  type="text"
                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                  :placeholder="field.default"
                />
              </div>
            </div>
          </div>

          <!-- Filters -->
          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-sm font-medium text-gray-300 mb-3">Filtres</h3>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Streams a envoyer</label>
              <div class="flex gap-4">
                <label class="flex items-center gap-2">
                  <input
                    type="checkbox"
                    :checked="sinkForm.filter_streams.length === 0 || sinkForm.filter_streams.includes('stdout')"
                    @change="e => {
                      if (e.target.checked && !sinkForm.filter_streams.includes('stdout')) {
                        sinkForm.filter_streams.push('stdout')
                      } else if (!e.target.checked) {
                        sinkForm.filter_streams = sinkForm.filter_streams.filter(s => s !== 'stdout')
                      }
                    }"
                    class="w-4 h-4"
                  />
                  <span class="text-sm">stdout</span>
                </label>
                <label class="flex items-center gap-2">
                  <input
                    type="checkbox"
                    :checked="sinkForm.filter_streams.length === 0 || sinkForm.filter_streams.includes('stderr')"
                    @change="e => {
                      if (e.target.checked && !sinkForm.filter_streams.includes('stderr')) {
                        sinkForm.filter_streams.push('stderr')
                      } else if (!e.target.checked) {
                        sinkForm.filter_streams = sinkForm.filter_streams.filter(s => s !== 'stderr')
                      }
                    }"
                    class="w-4 h-4"
                  />
                  <span class="text-sm">stderr</span>
                </label>
              </div>
              <p class="text-xs text-gray-500 mt-1">Si aucun selectionne, tous les streams seront envoyes</p>
            </div>
          </div>

          <!-- TLS -->
          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-sm font-medium text-gray-300 mb-3">Securite</h3>
            <div class="flex gap-6">
              <label class="flex items-center gap-2">
                <input v-model="sinkForm.tls_enabled" type="checkbox" class="w-4 h-4" />
                <span class="text-sm">TLS/SSL</span>
              </label>
              <label class="flex items-center gap-2">
                <input v-model="sinkForm.tls_verify" type="checkbox" class="w-4 h-4" />
                <span class="text-sm">Verifier le certificat</span>
              </label>
            </div>
          </div>

          <!-- Batching -->
          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-sm font-medium text-gray-300 mb-3">Performance</h3>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm text-gray-400 mb-1">Taille du batch</label>
                <input
                  v-model.number="sinkForm.batch_size"
                  type="number"
                  min="1"
                  max="10000"
                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label class="block text-sm text-gray-400 mb-1">Intervalle (s)</label>
                <input
                  v-model.number="sinkForm.flush_interval"
                  type="number"
                  min="1"
                  max="300"
                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
                />
              </div>
            </div>
          </div>

          <!-- Enabled -->
          <div class="border-t border-gray-700 pt-4">
            <label class="flex items-center gap-2">
              <input v-model="sinkForm.enabled" type="checkbox" class="w-4 h-4" />
              <span class="text-sm">Activer ce puits</span>
            </label>
          </div>
        </form>

        <!-- Modal footer -->
        <div class="p-4 border-t border-gray-700 flex justify-end gap-3">
          <button
            @click="closeModal"
            type="button"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
          >
            Annuler
          </button>
          <button
            @click="saveSink"
            :disabled="loading"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm disabled:opacity-50"
          >
            {{ loading ? 'Enregistrement...' : (editingSink ? 'Mettre a jour' : 'Creer') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
