<script setup>
import { ref, computed, watch } from 'vue'
import { useVmsStore } from '../stores/vms'

const props = defineProps({
  vm: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['save', 'close'])

const vmsStore = useVmsStore()

// Form state
const form = ref({
  name: '',
  hostname: '',
  ip_address: '',
  ssh_port: 22,
  ssh_user: 'root',
  os_type: 'unknown',
  tags: [],
  notes: '',
})

const newTag = ref('')
const sshTestResult = ref(null)
const sshTesting = ref(false)
const saving = ref(false)

const isEditing = computed(() => !!props.vm)

const osOptions = [
  { value: 'unknown', label: 'Non specifie' },
  { value: 'debian', label: 'Debian' },
  { value: 'ubuntu', label: 'Ubuntu' },
  { value: 'centos', label: 'CentOS / RHEL' },
  { value: 'macos', label: 'macOS' },
  { value: 'windows', label: 'Windows' },
]

// Initialize form when editing
watch(() => props.vm, (vm) => {
  if (vm) {
    form.value = {
      name: vm.name || '',
      hostname: vm.hostname || '',
      ip_address: vm.ip_address || '',
      ssh_port: vm.ssh_port || 22,
      ssh_user: vm.ssh_user || 'root',
      os_type: vm.os_type || 'unknown',
      tags: [...(vm.tags || [])],
      notes: vm.notes || '',
    }
  }
}, { immediate: true })

// Methods
function addTag() {
  const tag = newTag.value.trim()
  if (tag && !form.value.tags.includes(tag)) {
    form.value.tags.push(tag)
  }
  newTag.value = ''
}

function removeTag(tag) {
  form.value.tags = form.value.tags.filter(t => t !== tag)
}

async function testSshConnection() {
  sshTesting.value = true
  sshTestResult.value = null

  try {
    const result = await vmsStore.testSshConnection(
      form.value.ip_address,
      form.value.ssh_port,
      form.value.ssh_user
    )
    sshTestResult.value = result

    // Auto-detect OS if successful
    if (result.success && result.os_detected && form.value.os_type === 'unknown') {
      form.value.os_type = result.os_detected
    }
  } catch (e) {
    sshTestResult.value = { success: false, message: e.message }
  } finally {
    sshTesting.value = false
  }
}

async function handleSubmit() {
  if (!form.value.name || !form.value.hostname || !form.value.ip_address) {
    return
  }

  saving.value = true
  try {
    emit('save', { ...form.value })
  } finally {
    saving.value = false
  }
}

function handleClose() {
  emit('close')
}
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="handleClose">
    <div class="bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-gray-700">
        <h2 class="text-lg font-semibold">
          {{ isEditing ? 'Modifier la VM' : 'Ajouter une VM' }}
        </h2>
        <button
          @click="handleClose"
          class="w-8 h-8 flex items-center justify-center hover:bg-gray-700 rounded"
        >
          ✕
        </button>
      </div>

      <!-- Form -->
      <form @submit.prevent="handleSubmit" class="p-4 space-y-4">
        <!-- Name -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">
            Nom <span class="text-red-400">*</span>
          </label>
          <input
            v-model="form.name"
            type="text"
            required
            class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
            placeholder="Production Server 1"
          />
        </div>

        <!-- Hostname -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">
            Hostname <span class="text-red-400">*</span>
          </label>
          <input
            v-model="form.hostname"
            type="text"
            required
            class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
            placeholder="server1.example.com"
          />
        </div>

        <!-- IP + Port -->
        <div class="grid grid-cols-3 gap-4">
          <div class="col-span-2">
            <label class="block text-sm font-medium text-gray-300 mb-1">
              Adresse IP <span class="text-red-400">*</span>
            </label>
            <input
              v-model="form.ip_address"
              type="text"
              required
              class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
              placeholder="192.168.1.100"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1">
              Port SSH
            </label>
            <input
              v-model.number="form.ssh_port"
              type="number"
              min="1"
              max="65535"
              class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <!-- SSH User -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">
            Utilisateur SSH
          </label>
          <input
            v-model="form.ssh_user"
            type="text"
            class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
            placeholder="root"
          />
        </div>

        <!-- Test SSH Connection -->
        <div>
          <button
            type="button"
            @click="testSshConnection"
            :disabled="sshTesting || !form.ip_address"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm flex items-center gap-2"
          >
            <span v-if="sshTesting">Testing...</span>
            <span v-else>Tester la connexion SSH</span>
          </button>

          <div
            v-if="sshTestResult"
            class="mt-2 p-3 rounded text-sm"
            :class="sshTestResult.success ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'"
          >
            {{ sshTestResult.message }}
            <span v-if="sshTestResult.os_detected">
              (OS detecte: {{ sshTestResult.os_detected }})
            </span>
          </div>
        </div>

        <!-- OS Type -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">
            Systeme d'exploitation
          </label>
          <select
            v-model="form.os_type"
            class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
          >
            <option v-for="os in osOptions" :key="os.value" :value="os.value">
              {{ os.label }}
            </option>
          </select>
        </div>

        <!-- Tags -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">
            Tags
          </label>
          <div class="flex gap-2 mb-2">
            <input
              v-model="newTag"
              type="text"
              class="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500"
              placeholder="Ajouter un tag..."
              @keydown.enter.prevent="addTag"
            />
            <button
              type="button"
              @click="addTag"
              class="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded"
            >
              +
            </button>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="tag in form.tags"
              :key="tag"
              class="px-2 py-1 bg-gray-700 rounded text-sm flex items-center gap-1"
            >
              {{ tag }}
              <button
                type="button"
                @click="removeTag(tag)"
                class="hover:text-red-400"
              >
                ×
              </button>
            </span>
          </div>
        </div>

        <!-- Notes -->
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">
            Notes
          </label>
          <textarea
            v-model="form.notes"
            rows="3"
            class="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded focus:outline-none focus:border-blue-500 resize-none"
            placeholder="Notes optionnelles..."
          ></textarea>
        </div>

        <!-- Actions -->
        <div class="flex justify-end gap-3 pt-4 border-t border-gray-700">
          <button
            type="button"
            @click="handleClose"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded"
          >
            Annuler
          </button>
          <button
            type="submit"
            :disabled="saving || !form.name || !form.hostname || !form.ip_address"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded"
          >
            {{ isEditing ? 'Enregistrer' : 'Ajouter' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
