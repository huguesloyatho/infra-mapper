<script setup>
import { ref, computed, onMounted } from 'vue'

// State
const backups = ref([])
const loading = ref(false)
const creating = ref(false)
const restoring = ref(null) // backup_id en cours de restauration
const error = ref(null)
const successMessage = ref(null)

// Options
const includeLogsOnCreate = ref(false)
const retentionDays = ref(30)

// Modals
const showRestoreModal = ref(false)
const selectedBackup = ref(null)
const restoreOptions = ref({
  tables: null, // null = toutes
  clear_existing: true
})

// Computed
const totalSize = computed(() => {
  return backups.value.reduce((sum, b) => sum + b.size_bytes, 0)
})

const totalSizeHuman = computed(() => {
  return formatSize(totalSize.value)
})

// Methods
function formatSize(bytes) {
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  for (const unit of units) {
    if (size < 1024) return `${size.toFixed(1)} ${unit}`
    size /= 1024
  }
  return `${size.toFixed(1)} TB`
}

function formatDate(isoString) {
  if (!isoString) return 'N/A'
  const date = new Date(isoString)
  return date.toLocaleString('fr-FR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

async function fetchBackups() {
  loading.value = true
  error.value = null
  try {
    const response = await fetch('/api/v1/backups')
    if (!response.ok) throw new Error('Erreur chargement backups')
    backups.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function createBackup() {
  creating.value = true
  error.value = null
  successMessage.value = null
  try {
    const response = await fetch('/api/v1/backups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include_logs: includeLogsOnCreate.value })
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur creation backup')
    }
    const backup = await response.json()
    successMessage.value = `Backup ${backup.id} cree avec succes`
    await fetchBackups()
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

function downloadBackup(backup) {
  window.open(`/api/v1/backups/${backup.id}/download`, '_blank')
}

function openRestoreModal(backup) {
  selectedBackup.value = backup
  restoreOptions.value = {
    tables: null,
    clear_existing: true
  }
  showRestoreModal.value = true
}

async function restoreBackup() {
  if (!selectedBackup.value) return

  restoring.value = selectedBackup.value.id
  error.value = null
  successMessage.value = null
  showRestoreModal.value = false

  try {
    const response = await fetch(`/api/v1/backups/${selectedBackup.value.id}/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(restoreOptions.value)
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail || 'Erreur restauration')
    }

    const restoredTables = Object.entries(data.restored)
      .map(([table, count]) => `${table}: ${count}`)
      .join(', ')

    successMessage.value = `Restauration terminee - ${restoredTables}`

    if (data.errors && data.errors.length > 0) {
      error.value = `Erreurs: ${data.errors.join(', ')}`
    }
  } catch (e) {
    error.value = e.message
  } finally {
    restoring.value = null
    selectedBackup.value = null
  }
}

async function deleteBackup(backup) {
  if (!confirm(`Supprimer le backup ${backup.id} ?`)) return

  error.value = null
  try {
    const response = await fetch(`/api/v1/backups/${backup.id}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error('Erreur suppression')
    await fetchBackups()
    successMessage.value = `Backup ${backup.id} supprime`
  } catch (e) {
    error.value = e.message
  }
}

async function cleanupOldBackups() {
  if (!confirm(`Supprimer les backups de plus de ${retentionDays.value} jours ?`)) return

  error.value = null
  successMessage.value = null
  try {
    const response = await fetch('/api/v1/backups/cleanup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ retention_days: retentionDays.value })
    })
    if (!response.ok) throw new Error('Erreur nettoyage')
    const data = await response.json()
    successMessage.value = `${data.deleted_count} backup(s) supprime(s)`
    await fetchBackups()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(() => {
  fetchBackups()
})
</script>

<template>
  <div class="h-full overflow-auto p-6">
    <div class="max-w-6xl mx-auto">
      <!-- Header -->
      <div class="flex justify-between items-center mb-6">
        <div>
          <h1 class="text-2xl font-bold text-white">Sauvegardes</h1>
          <p class="text-gray-400 text-sm mt-1">
            Gestion des backups de la base de donnees
          </p>
        </div>
        <div class="flex gap-3">
          <button
            @click="fetchBackups"
            :disabled="loading"
            class="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 disabled:opacity-50"
          >
            Actualiser
          </button>
          <button
            @click="createBackup"
            :disabled="creating"
            class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-500 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="creating" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>{{ creating ? 'Creation...' : 'Nouveau backup' }}</span>
          </button>
        </div>
      </div>

      <!-- Messages -->
      <div v-if="error" class="mb-4 p-4 bg-red-900/50 border border-red-700 rounded text-red-200">
        {{ error }}
      </div>
      <div v-if="successMessage" class="mb-4 p-4 bg-green-900/50 border border-green-700 rounded text-green-200">
        {{ successMessage }}
      </div>

      <!-- Stats -->
      <div class="grid grid-cols-3 gap-4 mb-6">
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-gray-400 text-sm">Total backups</div>
          <div class="text-2xl font-bold text-white">{{ backups.length }}</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-gray-400 text-sm">Espace utilise</div>
          <div class="text-2xl font-bold text-white">{{ totalSizeHuman }}</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-gray-400 text-sm">Dernier backup</div>
          <div class="text-lg font-bold text-white">
            {{ backups.length > 0 ? formatDate(backups[0].created_at) : 'Aucun' }}
          </div>
        </div>
      </div>

      <!-- Options -->
      <div class="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 class="text-white font-medium mb-3">Options</h3>
        <div class="flex flex-wrap gap-6">
          <label class="flex items-center gap-2 text-gray-300">
            <input
              type="checkbox"
              v-model="includeLogsOnCreate"
              class="w-4 h-4 rounded"
            />
            <span>Inclure les logs des containers</span>
            <span class="text-gray-500 text-sm">(peut etre volumineux)</span>
          </label>

          <div class="flex items-center gap-2">
            <label class="text-gray-300">Retention:</label>
            <input
              type="number"
              v-model.number="retentionDays"
              min="1"
              max="365"
              class="w-20 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white"
            />
            <span class="text-gray-400">jours</span>
            <button
              @click="cleanupOldBackups"
              class="ml-2 px-3 py-1 bg-orange-600 text-white text-sm rounded hover:bg-orange-500"
            >
              Nettoyer
            </button>
          </div>
        </div>
      </div>

      <!-- Liste des backups -->
      <div class="bg-gray-800 rounded-lg overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-sm font-medium text-gray-300">ID</th>
              <th class="px-4 py-3 text-left text-sm font-medium text-gray-300">Date</th>
              <th class="px-4 py-3 text-left text-sm font-medium text-gray-300">Taille</th>
              <th class="px-4 py-3 text-left text-sm font-medium text-gray-300">Tables</th>
              <th class="px-4 py-3 text-right text-sm font-medium text-gray-300">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-700">
            <tr v-if="loading" class="text-center">
              <td colspan="5" class="px-4 py-8 text-gray-400">
                Chargement...
              </td>
            </tr>
            <tr v-else-if="backups.length === 0" class="text-center">
              <td colspan="5" class="px-4 py-8 text-gray-400">
                Aucun backup disponible
              </td>
            </tr>
            <tr
              v-for="backup in backups"
              :key="backup.id"
              class="hover:bg-gray-700/50"
            >
              <td class="px-4 py-3">
                <span class="font-mono text-sm text-white">{{ backup.id }}</span>
              </td>
              <td class="px-4 py-3 text-gray-300">
                {{ formatDate(backup.created_at) }}
              </td>
              <td class="px-4 py-3 text-gray-300">
                {{ backup.size_human }}
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="(count, table) in backup.tables"
                    :key="table"
                    class="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300"
                    :title="`${table}: ${count} lignes`"
                  >
                    {{ table }}: {{ count }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-right">
                <div class="flex justify-end gap-2">
                  <button
                    @click="downloadBackup(backup)"
                    class="p-1.5 text-gray-400 hover:text-blue-400"
                    title="Telecharger"
                  >
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </button>
                  <button
                    @click="openRestoreModal(backup)"
                    :disabled="restoring === backup.id"
                    class="p-1.5 text-gray-400 hover:text-green-400 disabled:opacity-50"
                    title="Restaurer"
                  >
                    <svg v-if="restoring === backup.id" class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <svg v-else class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                  <button
                    @click="deleteBackup(backup)"
                    class="p-1.5 text-gray-400 hover:text-red-400"
                    title="Supprimer"
                  >
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Modal de restauration -->
      <div
        v-if="showRestoreModal"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showRestoreModal = false"
      >
        <div class="bg-gray-800 rounded-lg p-6 w-full max-w-md">
          <h3 class="text-xl font-bold text-white mb-4">Restaurer le backup</h3>

          <div class="mb-4">
            <p class="text-gray-300">
              Backup: <span class="font-mono text-white">{{ selectedBackup?.id }}</span>
            </p>
            <p class="text-gray-400 text-sm mt-1">
              {{ formatDate(selectedBackup?.created_at) }} - {{ selectedBackup?.size_human }}
            </p>
          </div>

          <div class="mb-4">
            <label class="flex items-center gap-2 text-gray-300">
              <input
                type="checkbox"
                v-model="restoreOptions.clear_existing"
                class="w-4 h-4 rounded"
              />
              <span>Supprimer les donnees existantes</span>
            </label>
            <p class="text-gray-500 text-sm mt-1 ml-6">
              Recommande pour eviter les conflits
            </p>
          </div>

          <div class="bg-yellow-900/30 border border-yellow-700 rounded p-3 mb-4">
            <p class="text-yellow-200 text-sm">
              <strong>Attention:</strong> La restauration va remplacer les donnees actuelles.
              Cette operation est irreversible.
            </p>
          </div>

          <div class="flex justify-end gap-3">
            <button
              @click="showRestoreModal = false"
              class="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
            >
              Annuler
            </button>
            <button
              @click="restoreBackup"
              class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-500"
            >
              Restaurer
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
