<script setup>
import { ref, onMounted } from 'vue'

const emit = defineEmits(['close', 'keyDeployed'])

const keyInfo = ref(null)
const loading = ref(false)
const error = ref(null)
const success = ref(null)

// Deploy key form
const deployForm = ref({
  host: '',
  user: 'root',
  port: 22,
  password: '',
})
const deploying = ref(false)

async function fetchKeyInfo() {
  loading.value = true
  error.value = null

  try {
    const response = await fetch('/api/v1/ssh/key')
    if (!response.ok) throw new Error('Erreur chargement info cle SSH')
    keyInfo.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function generateKey(force = false) {
  loading.value = true
  error.value = null
  success.value = null

  try {
    const response = await fetch(`/api/v1/ssh/key/generate?force=${force}`, {
      method: 'POST',
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail || 'Erreur generation cle')
    }

    keyInfo.value = data.key_info
    success.value = data.message
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function deployKey() {
  if (!deployForm.value.host || !deployForm.value.password) {
    error.value = 'Veuillez remplir tous les champs'
    return
  }

  deploying.value = true
  error.value = null
  success.value = null

  try {
    const response = await fetch('/api/v1/ssh/key/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(deployForm.value),
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail || 'Erreur deploiement cle')
    }

    success.value = `Cle deployee sur ${deployForm.value.user}@${deployForm.value.host}`
    deployForm.value.password = ''
    emit('keyDeployed')
  } catch (e) {
    error.value = e.message
  } finally {
    deploying.value = false
  }
}

function copyPublicKey() {
  if (keyInfo.value?.public_key) {
    navigator.clipboard.writeText(keyInfo.value.public_key)
    success.value = 'Cle publique copiee dans le presse-papiers'
  }
}

onMounted(() => {
  fetchKeyInfo()
})
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="emit('close')">
    <div class="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-gray-700">
        <h2 class="text-lg font-semibold">Gestion des cles SSH</h2>
        <button
          @click="emit('close')"
          class="w-8 h-8 flex items-center justify-center hover:bg-gray-700 rounded"
        >
          x
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4 space-y-6">
        <!-- Messages -->
        <div v-if="error" class="p-3 bg-red-500/20 border border-red-500/50 rounded text-red-400 text-sm">
          {{ error }}
        </div>
        <div v-if="success" class="p-3 bg-green-500/20 border border-green-500/50 rounded text-green-400 text-sm">
          {{ success }}
        </div>

        <!-- Loading -->
        <div v-if="loading && !keyInfo" class="text-center py-8 text-gray-400">
          Chargement...
        </div>

        <template v-else>
          <!-- Key Status -->
          <div class="space-y-3">
            <h3 class="text-sm font-medium text-gray-400">Etat de la cle SSH</h3>

            <div v-if="keyInfo?.exists" class="p-4 bg-gray-900 rounded space-y-3">
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-green-500"></span>
                <span class="text-green-400">Cle SSH configuree</span>
              </div>

              <div v-if="keyInfo.fingerprint" class="text-xs text-gray-400 font-mono">
                {{ keyInfo.fingerprint }}
              </div>

              <div class="flex gap-2">
                <button
                  @click="copyPublicKey"
                  class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm"
                >
                  Copier la cle publique
                </button>
                <button
                  @click="generateKey(true)"
                  :disabled="loading"
                  class="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 rounded text-sm"
                >
                  Regenerer
                </button>
              </div>

              <!-- Public Key Display -->
              <div class="mt-3">
                <div class="text-xs text-gray-400 mb-1">Cle publique :</div>
                <pre class="p-2 bg-gray-800 rounded text-xs text-gray-300 overflow-x-auto">{{ keyInfo.public_key }}</pre>
              </div>
            </div>

            <div v-else class="p-4 bg-gray-900 rounded space-y-3">
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-yellow-500"></span>
                <span class="text-yellow-400">Aucune cle SSH configuree</span>
              </div>

              <button
                @click="generateKey(false)"
                :disabled="loading"
                class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm"
              >
                Generer une cle SSH
              </button>
            </div>
          </div>

          <!-- Deploy Key Section -->
          <div v-if="keyInfo?.exists" class="space-y-3">
            <h3 class="text-sm font-medium text-gray-400">Deployer la cle sur une VM</h3>

            <div class="p-4 bg-gray-900 rounded space-y-4">
              <p class="text-sm text-gray-400">
                Entrez les informations de connexion pour deployer la cle SSH.
                Le mot de passe est utilise uniquement pour cette operation.
              </p>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-xs text-gray-400 mb-1">Hote (IP ou hostname)</label>
                  <input
                    v-model="deployForm.host"
                    type="text"
                    placeholder="192.168.1.100"
                    class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label class="block text-xs text-gray-400 mb-1">Utilisateur</label>
                  <input
                    v-model="deployForm.user"
                    type="text"
                    placeholder="root"
                    class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label class="block text-xs text-gray-400 mb-1">Port SSH</label>
                  <input
                    v-model.number="deployForm.port"
                    type="number"
                    class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label class="block text-xs text-gray-400 mb-1">Mot de passe</label>
                  <input
                    v-model="deployForm.password"
                    type="password"
                    placeholder="********"
                    class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <button
                @click="deployKey"
                :disabled="deploying || !deployForm.host || !deployForm.password"
                class="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm"
              >
                {{ deploying ? 'Deploiement...' : 'Deployer la cle' }}
              </button>
            </div>
          </div>

          <!-- Instructions -->
          <div class="space-y-3">
            <h3 class="text-sm font-medium text-gray-400">Deploiement manuel</h3>
            <div class="p-4 bg-gray-900 rounded space-y-2 text-sm text-gray-400">
              <p>Vous pouvez aussi deployer la cle manuellement :</p>
              <ol class="list-decimal list-inside space-y-1 ml-2">
                <li>Copiez la cle publique ci-dessus</li>
                <li>Connectez-vous a la VM cible</li>
                <li>Ajoutez la cle dans <code class="px-1 bg-gray-800 rounded">~/.ssh/authorized_keys</code></li>
              </ol>
            </div>
          </div>
        </template>
      </div>

      <!-- Footer -->
      <div class="flex justify-end gap-2 p-4 border-t border-gray-700">
        <button
          @click="emit('close')"
          class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
        >
          Fermer
        </button>
      </div>
    </div>
  </div>
</template>
