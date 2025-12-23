<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const users = ref([])
const loading = ref(false)
const error = ref(null)
const showModal = ref(false)
const editingUser = ref(null)
const searchQuery = ref('')

const formData = ref({
  username: '',
  email: '',
  password: '',
  role: 'viewer',
  display_name: ''
})

const roles = [
  { value: 'super_admin', label: 'Super Admin', color: 'bg-purple-900 text-purple-300' },
  { value: 'admin', label: 'Administrateur', color: 'bg-red-900 text-red-300' },
  { value: 'operator', label: 'Opérateur', color: 'bg-blue-900 text-blue-300' },
  { value: 'viewer', label: 'Lecteur', color: 'bg-gray-600 text-gray-300' }
]

// Rôles que l'utilisateur actuel peut assigner
const assignableRoles = computed(() => {
  if (authStore.isSuperAdmin) {
    return roles // Super admin peut tout assigner
  }
  // Admin ne peut pas créer de super_admin
  return roles.filter(r => r.value !== 'super_admin')
})

const filteredUsers = computed(() => {
  if (!searchQuery.value) return users.value
  const query = searchQuery.value.toLowerCase()
  return users.value.filter(u =>
    u.username.toLowerCase().includes(query) ||
    u.email.toLowerCase().includes(query) ||
    (u.display_name && u.display_name.toLowerCase().includes(query))
  )
})

async function fetchUsers() {
  loading.value = true
  error.value = null
  try {
    const response = await authStore.authFetch('/api/v1/users')
    if (!response.ok) throw new Error('Erreur chargement utilisateurs')
    users.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  editingUser.value = null
  formData.value = {
    username: '',
    email: '',
    password: '',
    role: 'viewer',
    display_name: ''
  }
  showModal.value = true
}

function openEditModal(user) {
  editingUser.value = user
  formData.value = {
    username: user.username,
    email: user.email,
    password: '',
    role: user.role,
    display_name: user.display_name || ''
  }
  showModal.value = true
}

async function saveUser() {
  loading.value = true
  error.value = null

  try {
    const url = editingUser.value
      ? `/api/v1/users/${editingUser.value.id}`
      : '/api/v1/users'
    const method = editingUser.value ? 'PUT' : 'POST'

    const body = { ...formData.value }
    if (editingUser.value && !body.password) {
      delete body.password
    }

    const response = await authStore.authFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur sauvegarde')
    }

    showModal.value = false
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function deleteUser(user) {
  if (!confirm(`Supprimer l'utilisateur ${user.username} ?`)) return

  loading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/users/${user.id}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error('Erreur suppression')
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function toggleUserStatus(user) {
  loading.value = true
  try {
    const action = user.is_active ? 'deactivate' : 'activate'
    const response = await authStore.authFetch(`/api/v1/users/${user.id}/${action}`, {
      method: 'POST'
    })
    if (!response.ok) throw new Error('Erreur changement statut')
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function reset2FA(user) {
  if (!confirm(`Désactiver le 2FA pour ${user.username} ? L'utilisateur devra le reconfigurer.`)) return

  loading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/users/${user.id}/reset-2fa`, {
      method: 'POST'
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur reset 2FA')
    }
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function getRoleInfo(role) {
  return roles.find(r => r.value === role) || roles[2]
}

onMounted(fetchUsers)
</script>

<template>
  <div class="h-full overflow-auto p-6">
    <div class="max-w-6xl mx-auto">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-white">Gestion des Utilisateurs</h1>
        <button
          @click="openCreateModal"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center"
        >
          <svg class="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Nouvel utilisateur
        </button>
      </div>

      <!-- Error -->
      <div v-if="error" class="mb-4 bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded">
        {{ error }}
      </div>

      <!-- Search -->
      <div class="mb-4">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Rechercher..."
          class="w-full md:w-64 px-3 py-2 bg-gray-800 border border-gray-600 rounded-md text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <!-- Table -->
      <div class="bg-gray-800 rounded-lg overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Utilisateur</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Email</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Rôle</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Statut</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">2FA</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Provider</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-700">
            <tr v-if="loading && users.length === 0">
              <td colspan="7" class="px-4 py-8 text-center text-gray-400">
                Chargement...
              </td>
            </tr>
            <tr v-else-if="filteredUsers.length === 0">
              <td colspan="7" class="px-4 py-8 text-center text-gray-400">
                Aucun utilisateur trouvé
              </td>
            </tr>
            <tr v-for="user in filteredUsers" :key="user.id" class="hover:bg-gray-750">
              <td class="px-4 py-3">
                <div class="flex items-center">
                  <div class="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center mr-3">
                    <span class="text-sm font-medium text-white">
                      {{ (user.display_name || user.username).charAt(0).toUpperCase() }}
                    </span>
                  </div>
                  <div>
                    <div class="text-white font-medium">{{ user.display_name || user.username }}</div>
                    <div class="text-gray-400 text-sm">{{ user.username }}</div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-gray-300">{{ user.email }}</td>
              <td class="px-4 py-3">
                <span class="px-2 py-1 text-xs rounded-full" :class="getRoleInfo(user.role).color">
                  {{ getRoleInfo(user.role).label }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="user.is_active" class="text-green-400 flex items-center">
                  <span class="w-2 h-2 bg-green-400 rounded-full mr-2"></span>
                  Actif
                </span>
                <span v-else class="text-red-400 flex items-center">
                  <span class="w-2 h-2 bg-red-400 rounded-full mr-2"></span>
                  Inactif
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="user.totp_enabled" class="text-green-400 flex items-center">
                  <svg class="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  Actif
                </span>
                <span v-else class="text-gray-500">
                  -
                </span>
              </td>
              <td class="px-4 py-3 text-gray-400 text-sm">
                {{ user.idp_id ? 'SSO' : 'Local' }}
              </td>
              <td class="px-4 py-3 text-right space-x-2">
                <button
                  @click="openEditModal(user)"
                  class="text-blue-400 hover:text-blue-300"
                  title="Modifier"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  v-if="user.totp_enabled"
                  @click="reset2FA(user)"
                  class="text-orange-400 hover:text-orange-300"
                  title="Désactiver le 2FA"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </button>
                <button
                  @click="toggleUserStatus(user)"
                  class="text-yellow-400 hover:text-yellow-300"
                  :title="user.is_active ? 'Désactiver' : 'Activer'"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                  </svg>
                </button>
                <button
                  @click="deleteUser(user)"
                  class="text-red-400 hover:text-red-300"
                  title="Supprimer"
                  :disabled="user.id === authStore.user?.id"
                  :class="{ 'opacity-50 cursor-not-allowed': user.id === authStore.user?.id }"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-md p-6">
        <h2 class="text-xl font-bold text-white mb-4">
          {{ editingUser ? 'Modifier l\'utilisateur' : 'Nouvel utilisateur' }}
        </h2>

        <form @submit.prevent="saveUser" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Nom d'utilisateur</label>
            <input
              v-model="formData.username"
              type="text"
              required
              :disabled="!!editingUser"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white disabled:opacity-50"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Email</label>
            <input
              v-model="formData.email"
              type="email"
              required
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Nom affiché</label>
            <input
              v-model="formData.display_name"
              type="text"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">
              Mot de passe {{ editingUser ? '(laisser vide pour ne pas changer)' : '' }}
            </label>
            <input
              v-model="formData.password"
              type="password"
              :required="!editingUser"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Rôle</label>
            <select
              v-model="formData.role"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            >
              <option v-for="role in assignableRoles" :key="role.value" :value="role.value">
                {{ role.label }}
              </option>
            </select>
          </div>

          <div class="flex justify-end space-x-3 pt-4">
            <button
              type="button"
              @click="showModal = false"
              class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700"
            >
              Annuler
            </button>
            <button
              type="submit"
              :disabled="loading"
              class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {{ loading ? 'Enregistrement...' : 'Enregistrer' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
