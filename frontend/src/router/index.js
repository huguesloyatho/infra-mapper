/**
 * Vue Router avec guards d'authentification.
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// Lazy loading des vues
const LoginView = () => import('../views/LoginView.vue')
const SsoCallbackView = () => import('../views/SsoCallbackView.vue')
const MainLayout = () => import('../layouts/MainLayout.vue')
const GraphView = () => import('../components/GraphView.vue')
const SettingsView = () => import('../views/SettingsView.vue')
const VmManagement = () => import('../components/VmManagement.vue')
const UsersView = () => import('../views/UsersView.vue')
const IamView = () => import('../views/IamView.vue')
const AuditView = () => import('../views/AuditView.vue')
const SecurityView = () => import('../views/SecurityView.vue')
const InventoryView = () => import('../views/InventoryView.vue')
const AlertsView = () => import('../views/AlertsView.vue')
const BackupView = () => import('../views/BackupView.vue')
const LogsView = () => import('../views/LogsView.vue')
const MetricsView = () => import('../views/MetricsView.vue')
const LogSinksView = () => import('../views/LogSinksView.vue')
const AgentHealthView = () => import('../views/AgentHealthView.vue')
const OrganizationsView = () => import('../views/OrganizationsView.vue')

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true }
  },
  {
    path: '/auth/callback',
    name: 'sso-callback',
    component: SsoCallbackView,
    meta: { public: true }
  },
  {
    path: '/',
    component: MainLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/graph'
      },
      {
        path: 'graph',
        name: 'graph',
        component: GraphView,
        meta: { title: 'Graphe Infrastructure' }
      },
      {
        path: 'inventory',
        name: 'inventory',
        component: InventoryView,
        meta: { title: 'Inventaire' }
      },
      {
        path: 'logs',
        name: 'logs',
        component: LogsView,
        meta: { title: 'Logs' }
      },
      {
        path: 'metrics',
        name: 'metrics',
        component: MetricsView,
        meta: { title: 'Metriques' }
      },
      {
        path: 'security',
        name: 'security',
        component: SecurityView,
        meta: {
          title: 'Securite'
        }
      },
      {
        path: 'settings',
        component: SettingsView,
        meta: {
          title: 'Parametres',
          roles: ['admin', 'operator']
        },
        children: [
          {
            path: '',
            redirect: '/settings/vms'
          },
          {
            path: 'vms',
            name: 'settings-vms',
            component: VmManagement,
            meta: {
              title: 'Gestion VMs / Agents',
              roles: ['admin', 'operator']
            }
          },
          {
            path: 'users',
            name: 'settings-users',
            component: UsersView,
            meta: {
              title: 'Gestion Utilisateurs',
              roles: ['admin']
            }
          },
          {
            path: 'iam',
            name: 'settings-iam',
            component: IamView,
            meta: {
              title: 'Configuration IAM',
              roles: ['admin']
            }
          },
          {
            path: 'audit',
            name: 'settings-audit',
            component: AuditView,
            meta: {
              title: 'Logs d\'audit',
              roles: ['admin']
            }
          },
          {
            path: 'alerts',
            name: 'settings-alerts',
            component: AlertsView,
            meta: {
              title: 'Alertes',
              roles: ['admin', 'operator']
            }
          },
          {
            path: 'backups',
            name: 'settings-backups',
            component: BackupView,
            meta: {
              title: 'Sauvegardes',
              roles: ['admin']
            }
          },
          {
            path: 'log-sinks',
            name: 'settings-log-sinks',
            component: LogSinksView,
            meta: {
              title: 'Puits de Logs',
              roles: ['admin', 'operator']
            }
          },
          {
            path: 'agent-health',
            name: 'settings-agent-health',
            component: AgentHealthView,
            meta: {
              title: 'Sante des Agents',
              roles: ['admin', 'operator']
            }
          },
          {
            path: 'organizations',
            name: 'settings-organizations',
            component: OrganizationsView,
            meta: {
              title: 'Organisations',
              roles: ['super_admin']
            }
          }
        ]
      }
    ]
  },
  // Catch-all route
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Initialiser le store si pas encore fait
  if (!authStore.initialized) {
    await authStore.initialize()
  }

  // Routes publiques
  if (to.meta.public) {
    // Si déjà connecté et va sur login, rediriger vers home
    if (to.name === 'login' && authStore.isAuthenticated) {
      return next({ name: 'graph' })
    }
    return next()
  }

  // Si l'auth n'est pas activée (AUTH_ENABLED=false), permettre l'accès
  // On vérifie si on a reçu des providers ou un user
  // Si non, on considère que l'auth est désactivée
  if (!authStore.authEnabled && !authStore.isAuthenticated) {
    return next()
  }

  // Routes protégées
  if (to.meta.requiresAuth || to.matched.some(r => r.meta.requiresAuth)) {
    if (!authStore.isAuthenticated) {
      // Sauvegarder la destination pour redirect après login
      sessionStorage.setItem('redirect_after_login', to.fullPath)
      return next({ name: 'login' })
    }

    // Vérifier les rôles si spécifiés
    if (to.meta.roles && to.meta.roles.length > 0) {
      const userRole = authStore.user?.role
      // super_admin a accès à tout
      if (userRole !== 'super_admin' && !to.meta.roles.includes(userRole)) {
        // Pas les droits, rediriger vers la page d'accueil
        return next({ name: 'graph' })
      }
    }
  }

  next()
})

// Mettre à jour le titre de la page
router.afterEach((to) => {
  const title = to.meta.title
  if (title) {
    document.title = `${title} - Infra-Mapper`
  } else {
    document.title = 'Infra-Mapper'
  }
})

export default router
