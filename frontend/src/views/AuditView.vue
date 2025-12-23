<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const logs = ref([])
const loading = ref(false)
const error = ref(null)
const pagination = ref({
  skip: 0,
  limit: 50,
  total: 0
})

const filters = ref({
  action: '',
  user_id: '',
  success: '',
  from_date: '',
  to_date: ''
})

const actions = [
  { value: '', label: 'Toutes les actions' },
  { value: 'login', label: 'Connexion' },
  { value: 'logout', label: 'Déconnexion' },
  { value: 'login_failed', label: 'Connexion échouée' },
  { value: 'password_change', label: 'Changement mot de passe' },
  { value: 'user_create', label: 'Création utilisateur' },
  { value: 'user_update', label: 'Modification utilisateur' },
  { value: 'user_delete', label: 'Suppression utilisateur' },
  { value: 'role_change', label: 'Changement de rôle' },
  { value: 'idp_config', label: 'Configuration IdP' },
  { value: 'token_refresh', label: 'Rafraîchissement token' },
  { value: 'session_revoke', label: 'Révocation session' }
]

async function fetchLogs() {
  loading.value = true
  error.value = null

  try {
    const params = new URLSearchParams()
    params.append('skip', pagination.value.skip.toString())
    params.append('limit', pagination.value.limit.toString())

    if (filters.value.action) params.append('action', filters.value.action)
    if (filters.value.user_id) params.append('user_id', filters.value.user_id)
    if (filters.value.success !== '') params.append('success', filters.value.success)
    if (filters.value.from_date) params.append('from_date', filters.value.from_date)
    if (filters.value.to_date) params.append('to_date', filters.value.to_date)

    const response = await authStore.authFetch(`/api/v1/audit/logs?${params}`)
    if (!response.ok) throw new Error('Erreur chargement logs')

    const data = await response.json()
    logs.value = data.logs || data
    pagination.value.total = data.total || logs.value.length
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  pagination.value.skip = 0
  fetchLogs()
}

function resetFilters() {
  filters.value = {
    action: '',
    user_id: '',
    success: '',
    from_date: '',
    to_date: ''
  }
  applyFilters()
}

function nextPage() {
  if (pagination.value.skip + pagination.value.limit < pagination.value.total) {
    pagination.value.skip += pagination.value.limit
    fetchLogs()
  }
}

function prevPage() {
  if (pagination.value.skip > 0) {
    pagination.value.skip = Math.max(0, pagination.value.skip - pagination.value.limit)
    fetchLogs()
  }
}

function formatDate(dateString) {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function getActionLabel(action) {
  const found = actions.find(a => a.value === action)
  return found ? found.label : action
}

function getActionColor(action) {
  const colors = {
    login: 'text-green-400',
    logout: 'text-gray-400',
    login_failed: 'text-red-400',
    password_change: 'text-yellow-400',
    user_create: 'text-blue-400',
    user_update: 'text-blue-400',
    user_delete: 'text-red-400',
    role_change: 'text-purple-400',
    idp_config: 'text-orange-400',
    token_refresh: 'text-gray-400',
    session_revoke: 'text-yellow-400'
  }
  return colors[action] || 'text-gray-400'
}

const currentPage = computed(() => Math.floor(pagination.value.skip / pagination.value.limit) + 1)
const totalPages = computed(() => Math.ceil(pagination.value.total / pagination.value.limit))

onMounted(fetchLogs)
</script>

<template>
  <div class="h-full overflow-auto p-6">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-white">Logs d'Audit</h1>
      </div>

      <!-- Error -->
      <div v-if="error" class="mb-4 bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded">
        {{ error }}
      </div>

      <!-- Filters -->
      <div class="bg-gray-800 rounded-lg p-4 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Action</label>
            <select v-model="filters.action"
                    class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white">
              <option v-for="action in actions" :key="action.value" :value="action.value">
                {{ action.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Résultat</label>
            <select v-model="filters.success"
                    class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white">
              <option value="">Tous</option>
              <option value="true">Succès</option>
              <option value="false">Échec</option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Date début</label>
            <input v-model="filters.from_date" type="date"
                   class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Date fin</label>
            <input v-model="filters.to_date" type="date"
                   class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
          </div>

          <div class="flex items-end space-x-2">
            <button @click="applyFilters"
                    class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
              Filtrer
            </button>
            <button @click="resetFilters"
                    class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700">
              Reset
            </button>
          </div>
        </div>
      </div>

      <!-- Table -->
      <div class="bg-gray-800 rounded-lg overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Date</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Utilisateur</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Action</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Ressource</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">IP</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Résultat</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-700">
            <tr v-if="loading && logs.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                Chargement...
              </td>
            </tr>
            <tr v-else-if="logs.length === 0">
              <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                Aucun log trouvé
              </td>
            </tr>
            <tr v-for="log in logs" :key="log.id" class="hover:bg-gray-750">
              <td class="px-4 py-3 text-gray-300 text-sm whitespace-nowrap">
                {{ formatDate(log.timestamp) }}
              </td>
              <td class="px-4 py-3">
                <span class="text-white">{{ log.username || '-' }}</span>
              </td>
              <td class="px-4 py-3">
                <span :class="getActionColor(log.action)" class="font-medium">
                  {{ getActionLabel(log.action) }}
                </span>
              </td>
              <td class="px-4 py-3 text-gray-400 text-sm">
                <span v-if="log.resource_type">
                  {{ log.resource_type }}
                  <span v-if="log.resource_id" class="text-gray-500">
                    #{{ log.resource_id.substring(0, 8) }}
                  </span>
                </span>
                <span v-else>-</span>
              </td>
              <td class="px-4 py-3 text-gray-400 text-sm font-mono">
                {{ log.ip_address || '-' }}
              </td>
              <td class="px-4 py-3">
                <span v-if="log.success" class="text-green-400 flex items-center">
                  <svg class="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  Succès
                </span>
                <span v-else class="text-red-400 flex items-center">
                  <svg class="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Échec
                </span>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
        <div class="bg-gray-700 px-4 py-3 flex items-center justify-between">
          <div class="text-sm text-gray-400">
            {{ pagination.skip + 1 }} - {{ Math.min(pagination.skip + pagination.limit, pagination.total) }}
            sur {{ pagination.total }} entrées
          </div>
          <div class="flex space-x-2">
            <button @click="prevPage" :disabled="pagination.skip === 0"
                    class="px-3 py-1 border border-gray-600 text-gray-300 rounded hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed">
              Précédent
            </button>
            <span class="px-3 py-1 text-gray-300">
              Page {{ currentPage }} / {{ totalPages }}
            </span>
            <button @click="nextPage" :disabled="pagination.skip + pagination.limit >= pagination.total"
                    class="px-3 py-1 border border-gray-600 text-gray-300 rounded hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed">
              Suivant
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
