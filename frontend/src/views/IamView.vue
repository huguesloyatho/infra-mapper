<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const activeTab = ref('oidc') // 'oidc' or 'saml'
const providers = ref([])
const loading = ref(false)
const error = ref(null)
const showModal = ref(false)
const editingProvider = ref(null)

const oidcFormData = ref({
  name: '',
  display_name: '',
  provider_type: 'oidc',
  is_enabled: true,
  config: {
    client_id: '',
    client_secret: '',
    issuer_url: '',
    scopes: 'openid profile email',
    authorization_endpoint: '',
    token_endpoint: '',
    userinfo_endpoint: ''
  },
  attribute_mapping: {
    email: 'email',
    username: 'preferred_username',
    display_name: 'name'
  },
  role_mapping: {},
  auto_create_users: true,
  default_role: 'viewer'
})

const samlFormData = ref({
  name: '',
  display_name: '',
  provider_type: 'saml',
  is_enabled: true,
  config: {
    entity_id: '',
    sso_url: '',
    slo_url: '',
    certificate: '',
    name_id_format: 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'
  },
  attribute_mapping: {
    email: 'email',
    username: 'uid',
    display_name: 'displayName'
  },
  role_mapping: {},
  auto_create_users: true,
  default_role: 'viewer'
})

const filteredProviders = computed(() => {
  return providers.value.filter(p => p.provider_type === activeTab.value)
})

async function fetchProviders() {
  loading.value = true
  error.value = null
  try {
    const response = await authStore.authFetch('/api/v1/identity-providers')
    if (!response.ok) throw new Error('Erreur chargement providers')
    providers.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  editingProvider.value = null
  if (activeTab.value === 'oidc') {
    oidcFormData.value = {
      name: '',
      display_name: '',
      provider_type: 'oidc',
      is_enabled: true,
      config: {
        client_id: '',
        client_secret: '',
        issuer_url: '',
        scopes: 'openid profile email',
        authorization_endpoint: '',
        token_endpoint: '',
        userinfo_endpoint: ''
      },
      attribute_mapping: { email: 'email', username: 'preferred_username', display_name: 'name' },
      role_mapping: {},
      auto_create_users: true,
      default_role: 'viewer'
    }
  } else {
    samlFormData.value = {
      name: '',
      display_name: '',
      provider_type: 'saml',
      is_enabled: true,
      config: {
        entity_id: '',
        sso_url: '',
        slo_url: '',
        certificate: '',
        name_id_format: 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'
      },
      attribute_mapping: { email: 'email', username: 'uid', display_name: 'displayName' },
      role_mapping: {},
      auto_create_users: true,
      default_role: 'viewer'
    }
  }
  showModal.value = true
}

function openEditModal(provider) {
  editingProvider.value = provider
  if (provider.provider_type === 'oidc') {
    oidcFormData.value = JSON.parse(JSON.stringify(provider))
    activeTab.value = 'oidc'
  } else {
    samlFormData.value = JSON.parse(JSON.stringify(provider))
    activeTab.value = 'saml'
  }
  showModal.value = true
}

async function saveProvider() {
  loading.value = true
  error.value = null

  try {
    const data = activeTab.value === 'oidc' ? oidcFormData.value : samlFormData.value
    const url = editingProvider.value
      ? `/api/v1/identity-providers/${editingProvider.value.id}`
      : '/api/v1/identity-providers'
    const method = editingProvider.value ? 'PUT' : 'POST'

    const response = await authStore.authFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })

    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur sauvegarde')
    }

    showModal.value = false
    await fetchProviders()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function deleteProvider(provider) {
  if (!confirm(`Supprimer le provider ${provider.display_name} ?`)) return

  loading.value = true
  try {
    const response = await authStore.authFetch(`/api/v1/identity-providers/${provider.id}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error('Erreur suppression')
    await fetchProviders()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function toggleProvider(provider) {
  loading.value = true
  try {
    const action = provider.is_enabled ? 'disable' : 'enable'
    const response = await authStore.authFetch(`/api/v1/identity-providers/${provider.id}/${action}`, {
      method: 'POST'
    })
    if (!response.ok) throw new Error('Erreur changement statut')
    await fetchProviders()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function discoverOidc() {
  if (!oidcFormData.value.config.issuer_url) {
    error.value = 'Veuillez saisir l\'URL de l\'issuer'
    return
  }

  loading.value = true
  error.value = null

  try {
    const response = await authStore.authFetch('/api/v1/identity-providers/discover-oidc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ issuer_url: oidcFormData.value.config.issuer_url })
    })

    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur découverte OIDC')
    }

    const discovery = await response.json()
    oidcFormData.value.config.authorization_endpoint = discovery.authorization_endpoint || ''
    oidcFormData.value.config.token_endpoint = discovery.token_endpoint || ''
    oidcFormData.value.config.userinfo_endpoint = discovery.userinfo_endpoint || ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchProviders)
</script>

<template>
  <div class="h-full overflow-auto p-6">
    <div class="max-w-6xl mx-auto">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-white">Configuration IAM</h1>
        <button
          @click="openCreateModal"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center"
        >
          <svg class="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Nouveau Provider
        </button>
      </div>

      <!-- Error -->
      <div v-if="error" class="mb-4 bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded">
        {{ error }}
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-gray-700 mb-6">
        <button
          @click="activeTab = 'oidc'"
          class="px-6 py-3 text-sm font-medium border-b-2 transition-colors"
          :class="activeTab === 'oidc'
            ? 'text-white border-blue-500'
            : 'text-gray-400 border-transparent hover:text-white'"
        >
          OpenID Connect
        </button>
        <button
          @click="activeTab = 'saml'"
          class="px-6 py-3 text-sm font-medium border-b-2 transition-colors"
          :class="activeTab === 'saml'
            ? 'text-white border-blue-500'
            : 'text-gray-400 border-transparent hover:text-white'"
        >
          SAML 2.0
        </button>
      </div>

      <!-- Providers List -->
      <div class="bg-gray-800 rounded-lg overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Provider</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Slug</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Statut</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase">Auto-création</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-700">
            <tr v-if="loading && filteredProviders.length === 0">
              <td colspan="5" class="px-4 py-8 text-center text-gray-400">
                Chargement...
              </td>
            </tr>
            <tr v-else-if="filteredProviders.length === 0">
              <td colspan="5" class="px-4 py-8 text-center text-gray-400">
                Aucun provider {{ activeTab.toUpperCase() }} configuré
              </td>
            </tr>
            <tr v-for="provider in filteredProviders" :key="provider.id" class="hover:bg-gray-750">
              <td class="px-4 py-3">
                <div class="text-white font-medium">{{ provider.display_name }}</div>
              </td>
              <td class="px-4 py-3 text-gray-400 font-mono text-sm">{{ provider.name }}</td>
              <td class="px-4 py-3">
                <span v-if="provider.is_enabled" class="text-green-400 flex items-center">
                  <span class="w-2 h-2 bg-green-400 rounded-full mr-2"></span>
                  Actif
                </span>
                <span v-else class="text-gray-400 flex items-center">
                  <span class="w-2 h-2 bg-gray-400 rounded-full mr-2"></span>
                  Inactif
                </span>
              </td>
              <td class="px-4 py-3 text-gray-300">
                {{ provider.auto_create_users ? 'Oui' : 'Non' }}
              </td>
              <td class="px-4 py-3 text-right space-x-2">
                <button
                  @click="openEditModal(provider)"
                  class="text-blue-400 hover:text-blue-300"
                  title="Modifier"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  @click="toggleProvider(provider)"
                  class="text-yellow-400 hover:text-yellow-300"
                  :title="provider.is_enabled ? 'Désactiver' : 'Activer'"
                >
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                  </svg>
                </button>
                <button
                  @click="deleteProvider(provider)"
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

      <!-- Help text -->
      <div class="mt-6 bg-gray-800 rounded-lg p-4">
        <h3 class="text-white font-medium mb-2">
          {{ activeTab === 'oidc' ? 'Configuration OpenID Connect' : 'Configuration SAML 2.0' }}
        </h3>
        <p class="text-gray-400 text-sm">
          <template v-if="activeTab === 'oidc'">
            Configurez un fournisseur d'identité OpenID Connect (Keycloak, Okta, Azure AD, Google, etc.)
            pour permettre l'authentification SSO. Le 2FA peut être géré directement par le fournisseur d'identité.
          </template>
          <template v-else>
            Configurez un fournisseur d'identité SAML 2.0 (Keycloak, ADFS, etc.) pour l'authentification SSO enterprise.
          </template>
        </p>
      </div>
    </div>

    <!-- Modal OIDC -->
    <div v-if="showModal && activeTab === 'oidc'" class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto py-4">
      <div class="absolute inset-0 bg-black/50" @click="showModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-2xl mx-4 p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-xl font-bold text-white mb-4">
          {{ editingProvider ? 'Modifier le provider OIDC' : 'Nouveau provider OIDC' }}
        </h2>

        <form @submit.prevent="saveProvider" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Slug (identifiant unique)</label>
              <input v-model="oidcFormData.name" type="text" required
                     class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                     placeholder="keycloak" :disabled="!!editingProvider" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Nom affiché</label>
              <input v-model="oidcFormData.display_name" type="text" required
                     class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                     placeholder="Keycloak SSO" />
            </div>
          </div>

          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-white font-medium mb-3">Configuration OIDC</h3>

            <div class="space-y-4">
              <div class="flex gap-2">
                <div class="flex-1">
                  <label class="block text-sm font-medium text-gray-300 mb-1">Issuer URL</label>
                  <input v-model="oidcFormData.config.issuer_url" type="url"
                         class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                         placeholder="https://keycloak.example.com/realms/myrealm" />
                </div>
                <div class="flex items-end">
                  <button type="button" @click="discoverOidc"
                          class="px-3 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-500">
                    Découvrir
                  </button>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-300 mb-1">Client ID</label>
                  <input v-model="oidcFormData.config.client_id" type="text" required
                         class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-300 mb-1">Client Secret</label>
                  <input v-model="oidcFormData.config.client_secret" type="password"
                         class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
                </div>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">Scopes</label>
                <input v-model="oidcFormData.config.scopes" type="text"
                       class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                       placeholder="openid profile email" />
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-300 mb-1">Authorization Endpoint</label>
                  <input v-model="oidcFormData.config.authorization_endpoint" type="url"
                         class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white text-sm" />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-300 mb-1">Token Endpoint</label>
                  <input v-model="oidcFormData.config.token_endpoint" type="url"
                         class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white text-sm" />
                </div>
              </div>
            </div>
          </div>

          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-white font-medium mb-3">Options</h3>
            <div class="flex items-center space-x-6">
              <label class="flex items-center">
                <input v-model="oidcFormData.is_enabled" type="checkbox"
                       class="rounded bg-gray-700 border-gray-600 text-blue-600" />
                <span class="ml-2 text-gray-300">Activé</span>
              </label>
              <label class="flex items-center">
                <input v-model="oidcFormData.auto_create_users" type="checkbox"
                       class="rounded bg-gray-700 border-gray-600 text-blue-600" />
                <span class="ml-2 text-gray-300">Auto-création utilisateurs</span>
              </label>
            </div>
            <div class="mt-3">
              <label class="block text-sm font-medium text-gray-300 mb-1">Rôle par défaut</label>
              <select v-model="oidcFormData.default_role"
                      class="px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white">
                <option value="viewer">Lecteur</option>
                <option value="operator">Opérateur</option>
                <option value="admin">Administrateur</option>
              </select>
            </div>
          </div>

          <div class="flex justify-end space-x-3 pt-4 border-t border-gray-700">
            <button type="button" @click="showModal = false"
                    class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700">
              Annuler
            </button>
            <button type="submit" :disabled="loading"
                    class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
              {{ loading ? 'Enregistrement...' : 'Enregistrer' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal SAML -->
    <div v-if="showModal && activeTab === 'saml'" class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto py-4">
      <div class="absolute inset-0 bg-black/50" @click="showModal = false"></div>
      <div class="relative bg-gray-800 rounded-lg w-full max-w-2xl mx-4 p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-xl font-bold text-white mb-4">
          {{ editingProvider ? 'Modifier le provider SAML' : 'Nouveau provider SAML' }}
        </h2>

        <form @submit.prevent="saveProvider" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Slug (identifiant unique)</label>
              <input v-model="samlFormData.name" type="text" required
                     class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                     placeholder="adfs" :disabled="!!editingProvider" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">Nom affiché</label>
              <input v-model="samlFormData.display_name" type="text" required
                     class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white"
                     placeholder="Active Directory FS" />
            </div>
          </div>

          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-white font-medium mb-3">Configuration SAML</h3>

            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">Entity ID (IdP)</label>
                <input v-model="samlFormData.config.entity_id" type="text" required
                       class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">SSO URL</label>
                <input v-model="samlFormData.config.sso_url" type="url" required
                       class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">SLO URL (optionnel)</label>
                <input v-model="samlFormData.config.slo_url" type="url"
                       class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white" />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-300 mb-1">Certificat X.509 (PEM)</label>
                <textarea v-model="samlFormData.config.certificate" rows="4"
                          class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white font-mono text-sm"
                          placeholder="-----BEGIN CERTIFICATE-----"></textarea>
              </div>
            </div>
          </div>

          <div class="border-t border-gray-700 pt-4">
            <h3 class="text-white font-medium mb-3">Options</h3>
            <div class="flex items-center space-x-6">
              <label class="flex items-center">
                <input v-model="samlFormData.is_enabled" type="checkbox"
                       class="rounded bg-gray-700 border-gray-600 text-blue-600" />
                <span class="ml-2 text-gray-300">Activé</span>
              </label>
              <label class="flex items-center">
                <input v-model="samlFormData.auto_create_users" type="checkbox"
                       class="rounded bg-gray-700 border-gray-600 text-blue-600" />
                <span class="ml-2 text-gray-300">Auto-création utilisateurs</span>
              </label>
            </div>
            <div class="mt-3">
              <label class="block text-sm font-medium text-gray-300 mb-1">Rôle par défaut</label>
              <select v-model="samlFormData.default_role"
                      class="px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white">
                <option value="viewer">Lecteur</option>
                <option value="operator">Opérateur</option>
                <option value="admin">Administrateur</option>
              </select>
            </div>
          </div>

          <div class="flex justify-end space-x-3 pt-4 border-t border-gray-700">
            <button type="button" @click="showModal = false"
                    class="px-4 py-2 border border-gray-600 text-gray-300 rounded-md hover:bg-gray-700">
              Annuler
            </button>
            <button type="submit" :disabled="loading"
                    class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50">
              {{ loading ? 'Enregistrement...' : 'Enregistrer' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
