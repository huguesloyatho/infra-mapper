<script setup>
import { ref, computed, onMounted } from 'vue'

// State
const activeTab = ref('alerts') // alerts, rules, channels
const loading = ref(false)
const error = ref(null)

// Data
const alerts = ref([])
const rules = ref([])
const channels = ref([])
const alertsCounts = ref({ total: 0, info: 0, warning: 0, critical: 0 })

// Filters
const alertStatusFilter = ref('active')
const alertSeverityFilter = ref('')

// Modals
const showRuleModal = ref(false)
const showChannelModal = ref(false)
const editingRule = ref(null)
const editingChannel = ref(null)

// Rule form
const ruleForm = ref({
  name: '',
  description: '',
  rule_type: 'host_offline',
  severity: 'warning',
  enabled: true,
  config: {},
  host_filter: '',
  container_filter: '',
  project_filter: '',
  cooldown_minutes: 15,
})

// Channel form
const channelForm = ref({
  name: '',
  channel_type: 'slack',
  enabled: true,
  config: {},
  severity_filter: [],
  rule_type_filter: [],
})

// Rule types with labels
const ruleTypes = [
  { value: 'host_offline', label: 'Host hors ligne', description: 'Alerte quand un host ne repond plus' },
  { value: 'container_stopped', label: 'Container arrete', description: 'Alerte quand un container s\'arrete' },
  { value: 'container_unhealthy', label: 'Container unhealthy', description: 'Alerte quand un healthcheck echoue' },
]

// Channel types with labels
const channelTypes = [
  { value: 'slack', label: 'Slack', icon: '💬', fields: ['webhook_url'] },
  { value: 'discord', label: 'Discord', icon: '🎮', fields: ['webhook_url'] },
  { value: 'telegram', label: 'Telegram', icon: '📱', fields: ['bot_token', 'chat_id'] },
  { value: 'email', label: 'Email', icon: '📧', fields: ['smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'from', 'to'] },
  { value: 'ntfy', label: 'ntfy', icon: '🔔', fields: ['server', 'topic', 'token'] },
  { value: 'webhook', label: 'Webhook', icon: '🔗', fields: ['url', 'method', 'headers'] },
]

const severities = [
  { value: 'info', label: 'Info', color: 'blue' },
  { value: 'warning', label: 'Warning', color: 'yellow' },
  { value: 'critical', label: 'Critical', color: 'red' },
]

// Computed
const filteredAlerts = computed(() => {
  let result = alerts.value

  if (alertStatusFilter.value) {
    result = result.filter(a => a.status === alertStatusFilter.value)
  }

  if (alertSeverityFilter.value) {
    result = result.filter(a => a.severity === alertSeverityFilter.value)
  }

  return result
})

const currentChannelType = computed(() => {
  return channelTypes.find(t => t.value === channelForm.value.channel_type)
})

// API calls
async function fetchAlerts() {
  try {
    const params = new URLSearchParams()
    if (alertStatusFilter.value) params.append('status', alertStatusFilter.value)
    if (alertSeverityFilter.value) params.append('severity', alertSeverityFilter.value)

    const response = await fetch(`/api/v1/alerts?${params}`)
    if (response.ok) {
      alerts.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur fetch alerts:', e)
  }
}

async function fetchAlertsCounts() {
  try {
    const response = await fetch('/api/v1/alerts/count')
    if (response.ok) {
      alertsCounts.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur fetch counts:', e)
  }
}

async function fetchRules() {
  try {
    const response = await fetch('/api/v1/alerts/rules')
    if (response.ok) {
      rules.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur fetch rules:', e)
  }
}

async function fetchChannels() {
  try {
    const response = await fetch('/api/v1/alerts/channels')
    if (response.ok) {
      channels.value = await response.json()
    }
  } catch (e) {
    console.error('Erreur fetch channels:', e)
  }
}

async function acknowledgeAlert(alertId) {
  try {
    const response = await fetch(`/api/v1/alerts/${alertId}/acknowledge`, { method: 'POST' })
    if (response.ok) {
      await fetchAlerts()
      await fetchAlertsCounts()
    }
  } catch (e) {
    console.error('Erreur acknowledge:', e)
  }
}

async function resolveAlert(alertId) {
  try {
    const response = await fetch(`/api/v1/alerts/${alertId}/resolve`, { method: 'POST' })
    if (response.ok) {
      await fetchAlerts()
      await fetchAlertsCounts()
    }
  } catch (e) {
    console.error('Erreur resolve:', e)
  }
}

async function deleteAlert(alertId) {
  if (!confirm('Supprimer cette alerte ?')) return

  try {
    const response = await fetch(`/api/v1/alerts/${alertId}`, { method: 'DELETE' })
    if (response.ok) {
      await fetchAlerts()
      await fetchAlertsCounts()
    }
  } catch (e) {
    console.error('Erreur delete alert:', e)
  }
}

// Rules CRUD
function openRuleModal(rule = null) {
  if (rule) {
    editingRule.value = rule
    ruleForm.value = { ...rule }
  } else {
    editingRule.value = null
    ruleForm.value = {
      name: '',
      description: '',
      rule_type: 'host_offline',
      severity: 'warning',
      enabled: true,
      config: {},
      host_filter: '',
      container_filter: '',
      project_filter: '',
      cooldown_minutes: 15,
    }
  }
  showRuleModal.value = true
}

async function saveRule() {
  loading.value = true
  try {
    const url = editingRule.value
      ? `/api/v1/alerts/rules/${editingRule.value.id}`
      : '/api/v1/alerts/rules'
    const method = editingRule.value ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ruleForm.value),
    })

    if (response.ok) {
      showRuleModal.value = false
      await fetchRules()
    } else {
      const data = await response.json()
      error.value = data.detail || 'Erreur sauvegarde'
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function deleteRule(ruleId) {
  if (!confirm('Supprimer cette regle ?')) return

  try {
    const response = await fetch(`/api/v1/alerts/rules/${ruleId}`, { method: 'DELETE' })
    if (response.ok) {
      await fetchRules()
    }
  } catch (e) {
    console.error('Erreur delete rule:', e)
  }
}

async function toggleRule(rule) {
  try {
    await fetch(`/api/v1/alerts/rules/${rule.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !rule.enabled }),
    })
    await fetchRules()
  } catch (e) {
    console.error('Erreur toggle rule:', e)
  }
}

// Channels CRUD
function openChannelModal(channel = null) {
  if (channel) {
    editingChannel.value = channel
    channelForm.value = { ...channel }
  } else {
    editingChannel.value = null
    channelForm.value = {
      name: '',
      channel_type: 'slack',
      enabled: true,
      config: {},
      severity_filter: [],
      rule_type_filter: [],
    }
  }
  showChannelModal.value = true
}

async function saveChannel() {
  loading.value = true
  try {
    const url = editingChannel.value
      ? `/api/v1/alerts/channels/${editingChannel.value.id}`
      : '/api/v1/alerts/channels'
    const method = editingChannel.value ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(channelForm.value),
    })

    if (response.ok) {
      showChannelModal.value = false
      await fetchChannels()
    } else {
      const data = await response.json()
      error.value = data.detail || 'Erreur sauvegarde'
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function deleteChannel(channelId) {
  if (!confirm('Supprimer ce canal ?')) return

  try {
    const response = await fetch(`/api/v1/alerts/channels/${channelId}`, { method: 'DELETE' })
    if (response.ok) {
      await fetchChannels()
    }
  } catch (e) {
    console.error('Erreur delete channel:', e)
  }
}

async function testChannel(channelId) {
  loading.value = true
  try {
    const response = await fetch(`/api/v1/alerts/channels/${channelId}/test`, { method: 'POST' })
    const data = await response.json()

    if (data.success) {
      alert('Test reussi ! Verifiez votre canal.')
    } else {
      alert(`Erreur: ${data.error}`)
    }
    await fetchChannels()
  } catch (e) {
    alert(`Erreur: ${e.message}`)
  } finally {
    loading.value = false
  }
}

async function toggleChannel(channel) {
  try {
    await fetch(`/api/v1/alerts/channels/${channel.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !channel.enabled }),
    })
    await fetchChannels()
  } catch (e) {
    console.error('Erreur toggle channel:', e)
  }
}

// Helpers
function formatDate(date) {
  if (!date) return '-'
  return new Date(date).toLocaleString('fr-FR')
}

function getSeverityClass(severity) {
  switch (severity) {
    case 'critical': return 'bg-red-500/20 text-red-400 border-red-500'
    case 'warning': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500'
    case 'info': return 'bg-blue-500/20 text-blue-400 border-blue-500'
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500'
  }
}

function getStatusClass(status) {
  switch (status) {
    case 'active': return 'bg-red-500/20 text-red-400'
    case 'acknowledged': return 'bg-yellow-500/20 text-yellow-400'
    case 'resolved': return 'bg-green-500/20 text-green-400'
    default: return 'bg-gray-500/20 text-gray-400'
  }
}

function getRuleTypeLabel(type) {
  return ruleTypes.find(r => r.value === type)?.label || type
}

function getChannelTypeIcon(type) {
  return channelTypes.find(c => c.value === type)?.icon || '📢'
}

onMounted(async () => {
  loading.value = true
  await Promise.all([
    fetchAlerts(),
    fetchAlertsCounts(),
    fetchRules(),
    fetchChannels(),
  ])
  loading.value = false
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-900 text-white overflow-hidden">
    <!-- Header with stats -->
    <header class="p-4 border-b border-gray-700">
      <div class="flex items-center justify-between">
        <h1 class="text-xl font-bold">Alerting</h1>

        <!-- Alert counts -->
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <span class="px-2 py-1 bg-gray-700 rounded text-sm">
              Total: {{ alertsCounts.total }}
            </span>
            <span v-if="alertsCounts.critical > 0" class="px-2 py-1 bg-red-500/20 text-red-400 rounded text-sm">
              🚨 {{ alertsCounts.critical }}
            </span>
            <span v-if="alertsCounts.warning > 0" class="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-sm">
              ⚠️ {{ alertsCounts.warning }}
            </span>
            <span v-if="alertsCounts.info > 0" class="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-sm">
              ℹ️ {{ alertsCounts.info }}
            </span>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex gap-4 mt-4">
        <button
          @click="activeTab = 'alerts'"
          class="px-4 py-2 rounded-t text-sm font-medium transition-colors"
          :class="activeTab === 'alerts' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'"
        >
          Alertes
        </button>
        <button
          @click="activeTab = 'rules'"
          class="px-4 py-2 rounded-t text-sm font-medium transition-colors"
          :class="activeTab === 'rules' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'"
        >
          Regles ({{ rules.length }})
        </button>
        <button
          @click="activeTab = 'channels'"
          class="px-4 py-2 rounded-t text-sm font-medium transition-colors"
          :class="activeTab === 'channels' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'"
        >
          Canaux ({{ channels.length }})
        </button>
      </div>
    </header>

    <!-- Content -->
    <div class="flex-1 overflow-auto p-4">
      <!-- Alerts Tab -->
      <div v-if="activeTab === 'alerts'">
        <!-- Filters -->
        <div class="flex items-center gap-4 mb-4">
          <select
            v-model="alertStatusFilter"
            @change="fetchAlerts()"
            class="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm"
          >
            <option value="">Tous les statuts</option>
            <option value="active">Actives</option>
            <option value="acknowledged">Acquittees</option>
            <option value="resolved">Resolues</option>
          </select>

          <select
            v-model="alertSeverityFilter"
            @change="fetchAlerts()"
            class="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm"
          >
            <option value="">Toutes severites</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>

          <button
            @click="fetchAlerts(); fetchAlertsCounts()"
            class="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
          >
            Rafraichir
          </button>
        </div>

        <!-- Alerts list -->
        <div class="space-y-3">
          <div
            v-for="alert in filteredAlerts"
            :key="alert.id"
            class="p-4 bg-gray-800 rounded-lg border-l-4"
            :class="getSeverityClass(alert.severity)"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-semibold">{{ alert.title }}</span>
                  <span
                    class="px-2 py-0.5 rounded text-xs"
                    :class="getStatusClass(alert.status)"
                  >
                    {{ alert.status }}
                  </span>
                </div>
                <p class="text-gray-400 text-sm mb-2">{{ alert.message }}</p>
                <div class="flex items-center gap-4 text-xs text-gray-500">
                  <span v-if="alert.host_name">Host: {{ alert.host_name }}</span>
                  <span v-if="alert.container_name">Container: {{ alert.container_name }}</span>
                  <span>{{ formatDate(alert.triggered_at) }}</span>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <button
                  v-if="alert.status === 'active'"
                  @click="acknowledgeAlert(alert.id)"
                  class="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-sm"
                  title="Acquitter"
                >
                  Acquitter
                </button>
                <button
                  v-if="alert.status !== 'resolved'"
                  @click="resolveAlert(alert.id)"
                  class="px-3 py-1 bg-green-600 hover:bg-green-500 rounded text-sm"
                  title="Resoudre"
                >
                  Resoudre
                </button>
                <button
                  @click="deleteAlert(alert.id)"
                  class="p-1 hover:bg-gray-700 rounded text-red-400"
                  title="Supprimer"
                >
                  🗑️
                </button>
              </div>
            </div>
          </div>

          <div v-if="filteredAlerts.length === 0" class="text-center text-gray-500 py-8">
            Aucune alerte
          </div>
        </div>
      </div>

      <!-- Rules Tab -->
      <div v-if="activeTab === 'rules'">
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-lg font-semibold">Regles d'alerte</h2>
          <button
            @click="openRuleModal()"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm"
          >
            + Nouvelle regle
          </button>
        </div>

        <div class="space-y-3">
          <div
            v-for="rule in rules"
            :key="rule.id"
            class="p-4 bg-gray-800 rounded-lg"
          >
            <div class="flex items-center justify-between">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-semibold">{{ rule.name }}</span>
                  <span
                    class="px-2 py-0.5 rounded text-xs"
                    :class="getSeverityClass(rule.severity)"
                  >
                    {{ rule.severity }}
                  </span>
                  <span class="px-2 py-0.5 bg-gray-700 rounded text-xs">
                    {{ getRuleTypeLabel(rule.rule_type) }}
                  </span>
                </div>
                <p v-if="rule.description" class="text-gray-400 text-sm">{{ rule.description }}</p>
                <div class="flex items-center gap-4 text-xs text-gray-500 mt-1">
                  <span v-if="rule.host_filter">Host: {{ rule.host_filter }}</span>
                  <span v-if="rule.container_filter">Container: {{ rule.container_filter }}</span>
                  <span>Cooldown: {{ rule.cooldown_minutes }}min</span>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <button
                  @click="toggleRule(rule)"
                  class="px-3 py-1 rounded text-sm"
                  :class="rule.enabled ? 'bg-green-600 hover:bg-green-500' : 'bg-gray-600 hover:bg-gray-500'"
                >
                  {{ rule.enabled ? 'Active' : 'Inactive' }}
                </button>
                <button
                  @click="openRuleModal(rule)"
                  class="p-1 hover:bg-gray-700 rounded"
                  title="Modifier"
                >
                  ✏️
                </button>
                <button
                  @click="deleteRule(rule.id)"
                  class="p-1 hover:bg-gray-700 rounded text-red-400"
                  title="Supprimer"
                >
                  🗑️
                </button>
              </div>
            </div>
          </div>

          <div v-if="rules.length === 0" class="text-center text-gray-500 py-8">
            Aucune regle configuree
          </div>
        </div>
      </div>

      <!-- Channels Tab -->
      <div v-if="activeTab === 'channels'">
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-lg font-semibold">Canaux de notification</h2>
          <button
            @click="openChannelModal()"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm"
          >
            + Nouveau canal
          </button>
        </div>

        <div class="space-y-3">
          <div
            v-for="channel in channels"
            :key="channel.id"
            class="p-4 bg-gray-800 rounded-lg"
          >
            <div class="flex items-center justify-between">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-xl">{{ getChannelTypeIcon(channel.channel_type) }}</span>
                  <span class="font-semibold">{{ channel.name }}</span>
                  <span class="px-2 py-0.5 bg-gray-700 rounded text-xs">
                    {{ channel.channel_type }}
                  </span>
                </div>
                <div class="text-xs text-gray-500">
                  <span v-if="channel.last_used_at">
                    Dernier envoi: {{ formatDate(channel.last_used_at) }}
                  </span>
                  <span v-if="channel.last_error" class="text-red-400 ml-2">
                    Erreur: {{ channel.last_error }}
                  </span>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <button
                  @click="testChannel(channel.id)"
                  :disabled="loading"
                  class="px-3 py-1 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded text-sm"
                >
                  Tester
                </button>
                <button
                  @click="toggleChannel(channel)"
                  class="px-3 py-1 rounded text-sm"
                  :class="channel.enabled ? 'bg-green-600 hover:bg-green-500' : 'bg-gray-600 hover:bg-gray-500'"
                >
                  {{ channel.enabled ? 'Actif' : 'Inactif' }}
                </button>
                <button
                  @click="openChannelModal(channel)"
                  class="p-1 hover:bg-gray-700 rounded"
                  title="Modifier"
                >
                  ✏️
                </button>
                <button
                  @click="deleteChannel(channel.id)"
                  class="p-1 hover:bg-gray-700 rounded text-red-400"
                  title="Supprimer"
                >
                  🗑️
                </button>
              </div>
            </div>
          </div>

          <div v-if="channels.length === 0" class="text-center text-gray-500 py-8">
            Aucun canal configure
          </div>
        </div>
      </div>
    </div>

    <!-- Rule Modal -->
    <div v-if="showRuleModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-gray-800 rounded-lg p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <h3 class="text-lg font-semibold mb-4">
          {{ editingRule ? 'Modifier la regle' : 'Nouvelle regle' }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Nom</label>
            <input
              v-model="ruleForm.name"
              type="text"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded focus:outline-none focus:border-blue-500"
              placeholder="Ex: Host production offline"
            />
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Description</label>
            <textarea
              v-model="ruleForm.description"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded focus:outline-none focus:border-blue-500"
              rows="2"
            ></textarea>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Type</label>
              <select
                v-model="ruleForm.rule_type"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                :disabled="editingRule"
              >
                <option v-for="rt in ruleTypes" :key="rt.value" :value="rt.value">
                  {{ rt.label }}
                </option>
              </select>
            </div>

            <div>
              <label class="block text-sm text-gray-400 mb-1">Severite</label>
              <select
                v-model="ruleForm.severity"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              >
                <option v-for="s in severities" :key="s.value" :value="s.value">
                  {{ s.label }}
                </option>
              </select>
            </div>
          </div>

          <!-- Config based on rule type -->
          <div v-if="ruleForm.rule_type === 'host_offline'">
            <label class="block text-sm text-gray-400 mb-1">Timeout (minutes)</label>
            <input
              v-model.number="ruleForm.config.timeout_minutes"
              type="number"
              min="1"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              placeholder="5"
            />
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Filtre host (regex)</label>
            <input
              v-model="ruleForm.host_filter"
              type="text"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              placeholder="Ex: prod-* ou ^web-.*"
            />
          </div>

          <div v-if="ruleForm.rule_type !== 'host_offline'">
            <label class="block text-sm text-gray-400 mb-1">Filtre container (regex)</label>
            <input
              v-model="ruleForm.container_filter"
              type="text"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              placeholder="Ex: nginx-* ou ^api-.*"
            />
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Cooldown (minutes)</label>
            <input
              v-model.number="ruleForm.cooldown_minutes"
              type="number"
              min="1"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
            />
            <p class="text-xs text-gray-500 mt-1">Temps minimum entre 2 alertes identiques</p>
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showRuleModal = false"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded"
          >
            Annuler
          </button>
          <button
            @click="saveRule"
            :disabled="loading || !ruleForm.name"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded"
          >
            {{ loading ? 'Enregistrement...' : 'Enregistrer' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Channel Modal -->
    <div v-if="showChannelModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-gray-800 rounded-lg p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <h3 class="text-lg font-semibold mb-4">
          {{ editingChannel ? 'Modifier le canal' : 'Nouveau canal' }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Nom</label>
            <input
              v-model="channelForm.name"
              type="text"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded focus:outline-none focus:border-blue-500"
              placeholder="Ex: Slack Ops"
            />
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Type</label>
            <select
              v-model="channelForm.channel_type"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              :disabled="editingChannel"
            >
              <option v-for="ct in channelTypes" :key="ct.value" :value="ct.value">
                {{ ct.icon }} {{ ct.label }}
              </option>
            </select>
          </div>

          <!-- Slack config -->
          <div v-if="channelForm.channel_type === 'slack'">
            <label class="block text-sm text-gray-400 mb-1">Webhook URL</label>
            <input
              v-model="channelForm.config.webhook_url"
              type="url"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              placeholder="https://hooks.slack.com/services/..."
            />
          </div>

          <!-- Discord config -->
          <div v-if="channelForm.channel_type === 'discord'">
            <label class="block text-sm text-gray-400 mb-1">Webhook URL</label>
            <input
              v-model="channelForm.config.webhook_url"
              type="url"
              class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              placeholder="https://discord.com/api/webhooks/..."
            />
          </div>

          <!-- Telegram config -->
          <div v-if="channelForm.channel_type === 'telegram'" class="space-y-3">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Bot Token</label>
              <input
                v-model="channelForm.config.bot_token"
                type="text"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="123456:ABC-DEF..."
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Chat ID</label>
              <input
                v-model="channelForm.config.chat_id"
                type="text"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="-1001234567890"
              />
            </div>
          </div>

          <!-- ntfy config -->
          <div v-if="channelForm.channel_type === 'ntfy'" class="space-y-3">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Serveur</label>
              <input
                v-model="channelForm.config.server"
                type="url"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="https://ntfy.sh"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Topic</label>
              <input
                v-model="channelForm.config.topic"
                type="text"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="my-alerts"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Token (optionnel)</label>
              <input
                v-model="channelForm.config.token"
                type="text"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="tk_..."
              />
            </div>
          </div>

          <!-- Email config -->
          <div v-if="channelForm.channel_type === 'email'" class="space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm text-gray-400 mb-1">Serveur SMTP</label>
                <input
                  v-model="channelForm.config.smtp_host"
                  type="text"
                  class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  placeholder="smtp.gmail.com"
                />
              </div>
              <div>
                <label class="block text-sm text-gray-400 mb-1">Port</label>
                <input
                  v-model.number="channelForm.config.smtp_port"
                  type="number"
                  class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                  placeholder="587"
                />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm text-gray-400 mb-1">Utilisateur</label>
                <input
                  v-model="channelForm.config.smtp_user"
                  type="text"
                  class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                />
              </div>
              <div>
                <label class="block text-sm text-gray-400 mb-1">Mot de passe</label>
                <input
                  v-model="channelForm.config.smtp_password"
                  type="password"
                  class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">De (From)</label>
              <input
                v-model="channelForm.config.from"
                type="email"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="alerts@example.com"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Destinataires (separes par virgule)</label>
              <input
                v-model="channelForm.config.to_string"
                type="text"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="admin@example.com, ops@example.com"
                @blur="channelForm.config.to = channelForm.config.to_string?.split(',').map(e => e.trim()).filter(Boolean)"
              />
            </div>
          </div>

          <!-- Webhook config -->
          <div v-if="channelForm.channel_type === 'webhook'" class="space-y-3">
            <div>
              <label class="block text-sm text-gray-400 mb-1">URL</label>
              <input
                v-model="channelForm.config.url"
                type="url"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
                placeholder="https://example.com/webhook"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Methode</label>
              <select
                v-model="channelForm.config.method"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded"
              >
                <option value="POST">POST</option>
              </select>
            </div>
          </div>

          <!-- Severity filter -->
          <div>
            <label class="block text-sm text-gray-400 mb-1">Filtrer par severite (optionnel)</label>
            <div class="flex gap-3">
              <label v-for="s in severities" :key="s.value" class="flex items-center gap-2">
                <input
                  type="checkbox"
                  :value="s.value"
                  v-model="channelForm.severity_filter"
                  class="rounded bg-gray-700 border-gray-600"
                />
                <span>{{ s.label }}</span>
              </label>
            </div>
            <p class="text-xs text-gray-500 mt-1">Vide = toutes les severites</p>
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showChannelModal = false"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded"
          >
            Annuler
          </button>
          <button
            @click="saveChannel"
            :disabled="loading || !channelForm.name"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded"
          >
            {{ loading ? 'Enregistrement...' : 'Enregistrer' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
