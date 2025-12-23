<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const organizations = ref([])
const loading = ref(false)
const error = ref(null)
const showModal = ref(false)
const editingOrg = ref(null)
const searchQuery = ref('')

// Pour les details d'une organisation
const selectedOrg = ref(null)
const showTeamsModal = ref(false)
const showMembersModal = ref(false)
const showHostsModal = ref(false)

// Données des sous-modals
const teams = ref([])
const members = ref([])
const orgHosts = ref([])
const availableHosts = ref([])
const availableUsers = ref([])
const teamsLoading = ref(false)
const membersLoading = ref(false)
const hostsLoading = ref(false)

// Modal ajout membre
const showAddMemberModal = ref(false)
const selectedUserId = ref('')
const selectedMemberRole = ref('member')

// Modal ajout host
const showAddHostModal = ref(false)
const selectedHostId = ref('')

// Modal ajout team
const showAddTeamModal = ref(false)
const newTeam = ref({ name: '', slug: '', description: '', color: '#3B82F6' })

const formData = ref({
  name: '',
  slug: '',
  description: '',
  max_hosts: null,
  max_users: null,
  max_teams: null
})

const filteredOrgs = computed(() => {
  if (!searchQuery.value) return organizations.value
  const query = searchQuery.value.toLowerCase()
  return organizations.value.filter(o =>
    o.name.toLowerCase().includes(query) ||
    o.slug.toLowerCase().includes(query)
  )
})

async function fetchOrganizations() {
  loading.value = true
  error.value = null
  try {
    const response = await authStore.authFetch('/api/v1/organizations')
    if (!response.ok) throw new Error('Erreur chargement organisations')
    organizations.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  editingOrg.value = null
  formData.value = {
    name: '',
    slug: '',
    description: '',
    max_hosts: null,
    max_users: null,
    max_teams: null
  }
  showModal.value = true
}

function openEditModal(org) {
  editingOrg.value = org
  formData.value = {
    name: org.name,
    slug: org.slug,
    description: org.description || '',
    max_hosts: org.max_hosts,
    max_users: org.max_users,
    max_teams: org.max_teams
  }
  showModal.value = true
}

function generateSlug() {
  if (!editingOrg.value) {
    formData.value.slug = formData.value.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
  }
}

function generateTeamSlug() {
  newTeam.value.slug = newTeam.value.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

async function saveOrganization() {
  loading.value = true
  error.value = null

  try {
    const url = editingOrg.value
      ? `/api/v1/organizations/${editingOrg.value.id}`
      : '/api/v1/organizations'
    const method = editingOrg.value ? 'PUT' : 'POST'

    const response = await authStore.authFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData.value)
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Erreur sauvegarde')
    }

    showModal.value = false
    await fetchOrganizations()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function deleteOrganization(org) {
  if (!confirm(`Supprimer l'organisation "${org.name}" ? Cette action supprimera aussi toutes les equipes associees.`)) return

  loading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${org.id}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error('Erreur suppression')
    await fetchOrganizations()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// === Teams Management ===
async function viewTeams(org) {
  selectedOrg.value = org
  showTeamsModal.value = true
  await fetchTeams(org.id)
}

async function fetchTeams(orgId) {
  teamsLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${orgId}/teams`)
    if (response.ok) {
      teams.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur chargement teams:', e)
  } finally {
    teamsLoading.value = false
  }
}

function openAddTeamModal() {
  newTeam.value = { name: '', slug: '', description: '', color: '#3B82F6' }
  showAddTeamModal.value = true
}

async function addTeam() {
  if (!newTeam.value.name || !newTeam.value.slug) return

  teamsLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${selectedOrg.value.id}/teams`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newTeam.value)
    })
    if (response.ok) {
      showAddTeamModal.value = false
      await fetchTeams(selectedOrg.value.id)
      await fetchOrganizations()
    } else {
      const data = await response.json().catch(() => ({}))
      alert(data.detail || 'Erreur creation equipe')
    }
  } catch (e) {
    console.error('Erreur ajout team:', e)
  } finally {
    teamsLoading.value = false
  }
}

async function deleteTeam(team) {
  if (!confirm(`Supprimer l'equipe "${team.name}" ?`)) return

  teamsLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${selectedOrg.value.id}/teams/${team.id}`, {
      method: 'DELETE'
    })
    if (response.ok) {
      await fetchTeams(selectedOrg.value.id)
      await fetchOrganizations()
    }
  } catch (e) {
    console.error('Erreur suppression team:', e)
  } finally {
    teamsLoading.value = false
  }
}

// === Members Management ===
async function viewMembers(org) {
  selectedOrg.value = org
  showMembersModal.value = true
  await fetchMembers(org.id)
  await fetchAvailableUsers()
}

async function fetchMembers(orgId) {
  membersLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${orgId}/members`)
    if (response.ok) {
      members.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur chargement membres:', e)
  } finally {
    membersLoading.value = false
  }
}

async function fetchAvailableUsers() {
  try {
    const response = await authStore.authFetch('/api/v1/users')
    if (response.ok) {
      availableUsers.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur chargement utilisateurs:', e)
  }
}

function openAddMemberModal() {
  selectedUserId.value = ''
  selectedMemberRole.value = 'member'
  showAddMemberModal.value = true
}

async function addMember() {
  if (!selectedUserId.value) return

  membersLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${selectedOrg.value.id}/members`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: selectedUserId.value,
        role: selectedMemberRole.value
      })
    })
    if (response.ok) {
      showAddMemberModal.value = false
      await fetchMembers(selectedOrg.value.id)
      await fetchOrganizations()
    } else {
      const data = await response.json().catch(() => ({}))
      alert(data.detail || 'Erreur ajout membre')
    }
  } catch (e) {
    console.error('Erreur ajout membre:', e)
  } finally {
    membersLoading.value = false
  }
}

async function removeMember(member) {
  if (!confirm(`Retirer "${member.username}" de l'organisation ?`)) return

  membersLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${selectedOrg.value.id}/members/${member.user_id}`, {
      method: 'DELETE'
    })
    if (response.ok) {
      await fetchMembers(selectedOrg.value.id)
      await fetchOrganizations()
    }
  } catch (e) {
    console.error('Erreur suppression membre:', e)
  } finally {
    membersLoading.value = false
  }
}

// === Hosts Management ===
async function viewHosts(org) {
  selectedOrg.value = org
  showHostsModal.value = true
  await fetchOrgHosts(org.id)
  await fetchAvailableHosts()
}

async function fetchOrgHosts(orgId) {
  hostsLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${orgId}/hosts`)
    if (response.ok) {
      orgHosts.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur chargement hosts:', e)
  } finally {
    hostsLoading.value = false
  }
}

async function fetchAvailableHosts() {
  try {
    const response = await authStore.authFetch('/api/v1/hosts')
    if (response.ok) {
      availableHosts.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur chargement hosts disponibles:', e)
  }
}

function openAddHostModal() {
  selectedHostId.value = ''
  showAddHostModal.value = true
}

// Hosts non assignés à cette org
const unassignedHosts = computed(() => {
  const assignedIds = orgHosts.value.map(h => h.host_id)
  return availableHosts.value.filter(h => !assignedIds.includes(h.id))
})

// Users non membres de cette org
const nonMemberUsers = computed(() => {
  const memberIds = members.value.map(m => m.user_id)
  return availableUsers.value.filter(u => !memberIds.includes(u.id))
})

async function addHost() {
  if (!selectedHostId.value) return

  hostsLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${selectedOrg.value.id}/hosts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host_id: selectedHostId.value })
    })
    if (response.ok) {
      showAddHostModal.value = false
      await fetchOrgHosts(selectedOrg.value.id)
      await fetchAvailableHosts()
      await fetchOrganizations()
    } else {
      const data = await response.json().catch(() => ({}))
      alert(data.detail || 'Erreur assignation host')
    }
  } catch (e) {
    console.error('Erreur ajout host:', e)
  } finally {
    hostsLoading.value = false
  }
}

async function removeHost(host) {
  if (!confirm(`Retirer le host "${host.hostname}" de l'organisation ?`)) return

  hostsLoading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/organizations/${selectedOrg.value.id}/hosts/${host.host_id}`, {
      method: 'DELETE'
    })
    if (response.ok) {
      await fetchOrgHosts(selectedOrg.value.id)
      await fetchAvailableHosts()
      await fetchOrganizations()
    }
  } catch (e) {
    console.error('Erreur suppression host:', e)
  } finally {
    hostsLoading.value = false
  }
}

const memberRoles = [
  { value: 'owner', label: 'Proprietaire' },
  { value: 'admin', label: 'Administrateur' },
  { value: 'member', label: 'Membre' }
]

onMounted(fetchOrganizations)
</script>

<template>
  <div class="h-full overflow-auto p-6">
    <div class="max-w-6xl mx-auto">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-white">Gestion des Organisations</h1>
          <p class="text-gray-400 text-sm mt-1">Gerez les organisations et leurs equipes pour le multi-tenancy</p>
        </div>
        <button
          @click="openCreateModal"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center"
        >
          <svg class="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Nouvelle organisation
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
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Organisation</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Stats</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Quotas</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Statut</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-700">
            <tr v-if="loading && organizations.length === 0">
              <td colspan="5" class="px-4 py-8 text-center text-gray-400">
                Chargement...
              </td>
            </tr>
            <tr v-else-if="filteredOrgs.length === 0">
              <td colspan="5" class="px-4 py-8 text-center text-gray-400">
                Aucune organisation trouvee
              </td>
            </tr>
            <tr v-for="org in filteredOrgs" :key="org.id" class="hover:bg-gray-750">
              <td class="px-4 py-3">
                <div>
                  <div class="text-white font-medium">{{ org.name }}</div>
                  <div class="text-gray-500 text-xs font-mono">{{ org.slug }}</div>
                  <div class="text-gray-400 text-sm" v-if="org.description">{{ org.description }}</div>
                </div>
              </td>
              <td class="px-4 py-3 text-sm">
                <div class="flex space-x-4">
                  <span class="text-cyan-400">{{ org.members_count }} membres</span>
                  <span class="text-purple-400">{{ org.teams_count }} equipes</span>
                  <span class="text-green-400">{{ org.hosts_count }} hosts</span>
                </div>
              </td>
              <td class="px-4 py-3 text-gray-400 text-sm">
                <div v-if="org.max_hosts || org.max_users || org.max_teams">
                  <span v-if="org.max_hosts">{{ org.hosts_count }}/{{ org.max_hosts }} hosts</span>
                  <span v-if="org.max_users">, {{ org.members_count }}/{{ org.max_users }} users</span>
                  <span v-if="org.max_teams">, {{ org.teams_count }}/{{ org.max_teams }} teams</span>
                </div>
                <span v-else class="text-gray-500">Illimite</span>
              </td>
              <td class="px-4 py-3">
                <span v-if="org.is_active" class="text-green-400 flex items-center">
                  <span class="w-2 h-2 bg-green-400 rounded-full mr-2"></span>
                  Active
                </span>
                <span v-else class="text-red-400 flex items-center">
                  <span class="w-2 h-2 bg-red-400 rounded-full mr-2"></span>
                  Inactive
                </span>
              </td>
              <td class="px-4 py-3 text-right space-x-2">
                <button
                  @click="viewHosts(org)"
                  class="text-green-400 hover:text-green-300"
                  title="Gerer les hosts"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                  </svg>
                </button>
                <button
                  @click="viewTeams(org)"
                  class="text-purple-400 hover:text-purple-300"
                  title="Gerer les equipes"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                  </svg>
                </button>
                <button
                  @click="viewMembers(org)"
                  class="text-cyan-400 hover:text-cyan-300"
                  title="Gerer les membres"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                </button>
                <button
                  @click="openEditModal(org)"
                  class="text-blue-400 hover:text-blue-300"
                  title="Modifier"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  @click="deleteOrganization(org)"
                  class="text-red-400 hover:text-red-300"
                  title="Supprimer"
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

      <!-- Info -->
      <div class="mt-6 bg-gray-800 rounded-lg p-4">
        <h3 class="text-white font-medium mb-2">A propos des organisations</h3>
        <p class="text-gray-400 text-sm">
          Les organisations permettent d'isoler les donnees entre differents clients ou departements.
          Chaque organisation peut avoir ses propres equipes, membres et hosts assignes.
          Les utilisateurs ne voient que les ressources de leur organisation.
        </p>
      </div>
    </div>

    <!-- Modal Create/Edit Organization -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-md p-6">
        <h2 class="text-xl font-bold text-white mb-4">
          {{ editingOrg ? 'Modifier l\'organisation' : 'Nouvelle organisation' }}
        </h2>

        <form @submit.prevent="saveOrganization" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Nom</label>
            <input
              v-model="formData.name"
              @input="generateSlug"
              type="text"
              required
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
              placeholder="Mon Organisation"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Slug (URL)</label>
            <input
              v-model="formData.slug"
              type="text"
              required
              :disabled="!!editingOrg"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white font-mono disabled:opacity-50"
              placeholder="mon-organisation"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <textarea
              v-model="formData.description"
              rows="2"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
              placeholder="Description optionnelle..."
            ></textarea>
          </div>

          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Max Hosts</label>
              <input
                v-model.number="formData.max_hosts"
                type="number"
                min="0"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                placeholder="∞"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Max Users</label>
              <input
                v-model.number="formData.max_users"
                type="number"
                min="0"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                placeholder="∞"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Max Teams</label>
              <input
                v-model.number="formData.max_teams"
                type="number"
                min="0"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                placeholder="∞"
              />
            </div>
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

    <!-- Modal Teams -->
    <div v-if="showTeamsModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showTeamsModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-2xl p-6 max-h-[80vh] overflow-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold text-white">
            Equipes de {{ selectedOrg?.name }}
          </h2>
          <button
            @click="openAddTeamModal"
            class="px-3 py-1 bg-purple-600 text-white text-sm rounded-md hover:bg-purple-700"
          >
            + Ajouter
          </button>
        </div>

        <div v-if="teamsLoading" class="text-center py-8 text-gray-400">Chargement...</div>
        <div v-else-if="teams.length === 0" class="text-center py-8 text-gray-400">
          Aucune equipe dans cette organisation
        </div>
        <div v-else class="space-y-2">
          <div v-for="team in teams" :key="team.id" class="flex items-center justify-between bg-gray-700 rounded-lg p-3">
            <div class="flex items-center">
              <div class="w-3 h-3 rounded-full mr-3" :style="{ backgroundColor: team.color || '#6B7280' }"></div>
              <div>
                <div class="text-white font-medium">{{ team.name }}</div>
                <div class="text-gray-400 text-sm">{{ team.members_count }} membres, {{ team.hosts_count }} hosts</div>
              </div>
            </div>
            <button @click="deleteTeam(team)" class="text-red-400 hover:text-red-300">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>

        <div class="flex justify-end mt-4">
          <button
            @click="showTeamsModal = false"
            class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>

    <!-- Modal Add Team -->
    <div v-if="showAddTeamModal" class="fixed inset-0 z-[60] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showAddTeamModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-md p-6">
        <h2 class="text-lg font-bold text-white mb-4">Nouvelle equipe</h2>
        <form @submit.prevent="addTeam" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Nom</label>
            <input
              v-model="newTeam.name"
              @input="generateTeamSlug"
              type="text"
              required
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
              placeholder="Nom de l'equipe"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Slug</label>
            <input
              v-model="newTeam.slug"
              type="text"
              required
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white font-mono"
              placeholder="slug-equipe"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Couleur</label>
            <input
              v-model="newTeam.color"
              type="color"
              class="w-full h-10 bg-gray-700 border border-gray-600 rounded-md cursor-pointer"
            />
          </div>
          <div class="flex justify-end space-x-3 pt-4">
            <button type="button" @click="showAddTeamModal = false" class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700">
              Annuler
            </button>
            <button type="submit" :disabled="teamsLoading" class="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50">
              Creer
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal Members -->
    <div v-if="showMembersModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showMembersModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-2xl p-6 max-h-[80vh] overflow-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold text-white">
            Membres de {{ selectedOrg?.name }}
          </h2>
          <button
            @click="openAddMemberModal"
            class="px-3 py-1 bg-cyan-600 text-white text-sm rounded-md hover:bg-cyan-700"
          >
            + Ajouter
          </button>
        </div>

        <div v-if="membersLoading" class="text-center py-8 text-gray-400">Chargement...</div>
        <div v-else-if="members.length === 0" class="text-center py-8 text-gray-400">
          Aucun membre dans cette organisation
        </div>
        <div v-else class="space-y-2">
          <div v-for="member in members" :key="member.id" class="flex items-center justify-between bg-gray-700 rounded-lg p-3">
            <div>
              <div class="text-white font-medium">{{ member.display_name || member.username }}</div>
              <div class="text-gray-400 text-sm">{{ member.email }}</div>
            </div>
            <div class="flex items-center space-x-3">
              <span class="px-2 py-1 rounded text-xs"
                    :class="{
                      'bg-yellow-900 text-yellow-300': member.role === 'owner',
                      'bg-red-900 text-red-300': member.role === 'admin',
                      'bg-gray-600 text-gray-300': member.role === 'member'
                    }">
                {{ member.role }}
              </span>
              <button @click="removeMember(member)" class="text-red-400 hover:text-red-300">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div class="flex justify-end mt-4">
          <button
            @click="showMembersModal = false"
            class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>

    <!-- Modal Add Member -->
    <div v-if="showAddMemberModal" class="fixed inset-0 z-[60] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showAddMemberModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-md p-6">
        <h2 class="text-lg font-bold text-white mb-4">Ajouter un membre</h2>
        <form @submit.prevent="addMember" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Utilisateur</label>
            <select
              v-model="selectedUserId"
              required
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            >
              <option value="" disabled>Selectionner un utilisateur</option>
              <option v-for="user in nonMemberUsers" :key="user.id" :value="user.id">
                {{ user.display_name || user.username }} ({{ user.email }})
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Role</label>
            <select
              v-model="selectedMemberRole"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            >
              <option v-for="role in memberRoles" :key="role.value" :value="role.value">
                {{ role.label }}
              </option>
            </select>
          </div>
          <div class="flex justify-end space-x-3 pt-4">
            <button type="button" @click="showAddMemberModal = false" class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700">
              Annuler
            </button>
            <button type="submit" :disabled="membersLoading || !selectedUserId" class="px-4 py-2 bg-cyan-600 text-white rounded-md hover:bg-cyan-700 disabled:opacity-50">
              Ajouter
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal Hosts -->
    <div v-if="showHostsModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showHostsModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-2xl p-6 max-h-[80vh] overflow-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold text-white">
            Hosts de {{ selectedOrg?.name }}
          </h2>
          <button
            @click="openAddHostModal"
            class="px-3 py-1 bg-green-600 text-white text-sm rounded-md hover:bg-green-700"
          >
            + Assigner
          </button>
        </div>

        <div v-if="hostsLoading" class="text-center py-8 text-gray-400">Chargement...</div>
        <div v-else-if="orgHosts.length === 0" class="text-center py-8 text-gray-400">
          Aucun host assigne a cette organisation
        </div>
        <div v-else class="space-y-2">
          <div v-for="host in orgHosts" :key="host.host_id" class="flex items-center justify-between bg-gray-700 rounded-lg p-3">
            <div>
              <div class="text-white font-medium">{{ host.hostname }}</div>
              <div class="text-gray-400 text-sm">
                {{ host.ip_addresses?.join(', ') || 'Pas d\'IP' }}
              </div>
            </div>
            <div class="flex items-center space-x-3">
              <span v-if="host.is_online" class="text-green-400 flex items-center">
                <span class="w-2 h-2 bg-green-400 rounded-full mr-1"></span>
                Online
              </span>
              <span v-else class="text-red-400 flex items-center">
                <span class="w-2 h-2 bg-red-400 rounded-full mr-1"></span>
                Offline
              </span>
              <button @click="removeHost(host)" class="text-red-400 hover:text-red-300">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div class="flex justify-end mt-4">
          <button
            @click="showHostsModal = false"
            class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>

    <!-- Modal Add Host -->
    <div v-if="showAddHostModal" class="fixed inset-0 z-[60] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showAddHostModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-md p-6">
        <h2 class="text-lg font-bold text-white mb-4">Assigner un host</h2>
        <form @submit.prevent="addHost" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">Host disponible</label>
            <select
              v-model="selectedHostId"
              required
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
            >
              <option value="" disabled>Selectionner un host</option>
              <option v-for="host in unassignedHosts" :key="host.id" :value="host.id">
                {{ host.hostname }} ({{ host.tailscale_ip || host.ip_addresses?.[0] || 'N/A' }})
              </option>
            </select>
            <p v-if="unassignedHosts.length === 0" class="text-yellow-400 text-sm mt-2">
              Tous les hosts sont deja assignes a une organisation
            </p>
          </div>
          <div class="flex justify-end space-x-3 pt-4">
            <button type="button" @click="showAddHostModal = false" class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700">
              Annuler
            </button>
            <button type="submit" :disabled="hostsLoading || !selectedHostId" class="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50">
              Assigner
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
