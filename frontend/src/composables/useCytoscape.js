import { ref, shallowRef, onMounted, onUnmounted, watch, triggerRef } from 'vue'
import cytoscape from 'cytoscape'

// Palette de couleurs distinctes pour les VMs
const VM_COLORS = [
  '#3b82f6', // blue
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#f97316', // orange
  '#14b8a6', // teal
  '#eab308', // yellow
  '#06b6d4', // cyan
  '#84cc16', // lime
  '#f43f5e', // rose
  '#6366f1', // indigo
]

// Cache pour les couleurs par hostname
const hostColorCache = new Map()
let colorIndex = 0

export function getHostColor(hostname) {
  // Toujours retourner une couleur valide
  const key = hostname || '__default__'
  if (hostColorCache.has(key)) {
    return hostColorCache.get(key)
  }
  const color = VM_COLORS[colorIndex % VM_COLORS.length]
  hostColorCache.set(key, color)
  colorIndex++
  return color
}

export function useCytoscape(containerRef, nodes, edges, edgeFilters = null, hostFilters = null, options = {}) {
  const cy = ref(null)
  const selectedNode = shallowRef(null)  // Use shallowRef for better reactivity with external objects
  const isFirstLoad = ref(true)

  // Options pour les dashboards personnalisés
  const savedPositions = ref(options.savedPositions || {})
  const onPositionChange = options.onPositionChange || null
  const onContextMenu = options.onContextMenu || null

  // Style du graphe - simple et lisible
  const style = [
    // Nœuds hôtes - rectangle bien visible
    {
      selector: 'node[type="host"]',
      style: {
        'background-color': '#1e40af',
        'label': 'data(label)',
        'color': '#fff',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '14px',
        'font-weight': 'bold',
        'width': 120,
        'height': 40,
        'shape': 'round-rectangle',
        'border-width': 2,
        'border-color': '#3b82f6',
      },
    },
    // Nœuds conteneurs - style de base (sera complété dynamiquement)
    {
      selector: 'node[type="container"]',
      style: {
        'label': 'data(label)',
        'color': '#fff',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '10px',
        'text-wrap': 'wrap',
        'text-max-width': '120px',
        'width': 130,
        'height': 50,
        'shape': 'round-rectangle',
        'border-width': 3,
      },
    },
    // Nœuds externes
    {
      selector: 'node[type="external"]',
      style: {
        'background-color': '#6b21a8',
        'label': 'data(label)',
        'color': '#fff',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 5,
        'font-size': '9px',
        'text-wrap': 'wrap',
        'text-max-width': '100px',
        'width': 40,
        'height': 40,
        'shape': 'diamond',
        'border-width': 2,
        'border-color': '#a855f7',
      },
    },
    // Arêtes de connexion internes (inter-conteneurs même VM) - vert
    {
      selector: 'edge[type="connection"][connection_type="internal"]',
      style: {
        'width': 1.5,
        'line-color': '#22c55e',
        'target-arrow-color': '#22c55e',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.6,
        'curve-style': 'bezier',
        'opacity': 0.6,
      },
    },
    // Arêtes de connexion cross-host (inter-VM Tailscale) - cyan
    {
      selector: 'edge[type="connection"][connection_type="cross-host"]',
      style: {
        'width': 1.5,
        'line-color': '#06b6d4',
        'target-arrow-color': '#06b6d4',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.6,
        'curve-style': 'bezier',
        'opacity': 0.6,
      },
    },
    // Arêtes de connexion externes (vers internet) - amber
    {
      selector: 'edge[type="connection"][connection_type="external"]',
      style: {
        'width': 1.5,
        'line-color': '#f59e0b',
        'target-arrow-color': '#f59e0b',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.6,
        'curve-style': 'bezier',
        'opacity': 0.6,
      },
    },
    // Fallback pour connexions sans type spécifié
    {
      selector: 'edge[type="connection"]',
      style: {
        'width': 1.5,
        'line-color': '#f59e0b',
        'target-arrow-color': '#f59e0b',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.6,
        'curve-style': 'bezier',
        'opacity': 0.6,
      },
    },
    // Arêtes de dépendance
    {
      selector: 'edge[type="dependency"]',
      style: {
        'width': 2,
        'line-color': '#06b6d4',
        'target-arrow-color': '#06b6d4',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.7,
        'curve-style': 'bezier',
        'line-style': 'dashed',
        'opacity': 0.8,
      },
    },
    // Sélection
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': '#fbbf24',
      },
    },
    // Hover
    {
      selector: 'node:active',
      style: {
        'overlay-opacity': 0.2,
        'overlay-color': '#fff',
      },
    },
  ]

  function initCytoscape() {
    if (!containerRef.value) return

    cy.value = cytoscape({
      container: containerRef.value,
      style,
      layout: { name: 'preset' }, // On utilisera cola après
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    })

    // Events
    cy.value.on('tap', 'node', (event) => {
      const data = event.target.data()
      console.log('[TAP] Node clicked:', data.label, data.type)
      selectedNode.value = { ...data }  // Create a new object to ensure reactivity
      triggerRef(selectedNode)  // Force trigger reactivity
      console.log('[TAP] selectedNode set to:', selectedNode.value?.label)
    })

    cy.value.on('tap', (event) => {
      if (event.target === cy.value) {
        selectedNode.value = null
      }
    })

    // Right-click context menu on nodes
    cy.value.on('cxttap', 'node', (event) => {
      const data = event.target.data()
      console.log('[CXTTAP] Right-click on node:', data.label, data.type)
      if (onContextMenu) {
        onContextMenu(event, { ...data })
      }
    })

    // Setup selection styles for containers
    setupSelectionStyles()

    // Notifier les changements de position (pour dashboards personnalisés)
    cy.value.on('dragfree', 'node', (event) => {
      if (onPositionChange) {
        const node = event.target
        const pos = node.position()
        onPositionChange(node.id(), pos.x, pos.y)
      }
    })
  }

  function updateGraph(newNodes, newEdges) {
    if (!cy.value) return

    // Sauvegarder les positions actuelles avant de supprimer les éléments
    const currentPositions = {}
    cy.value.nodes().forEach(node => {
      const pos = node.position()
      // Ne sauvegarder que si la position est valide (pas à l'origine)
      if (pos && (pos.x !== 0 || pos.y !== 0)) {
        currentPositions[node.id()] = { x: pos.x, y: pos.y }
      }
    })

    // Convertir les données pour Cytoscape
    const elements = []

    // Ajouter les nœuds
    for (const node of newNodes) {
      const isRunning = node.data?.status === 'running'
      const hostname = node.data?.hostname || ''
      const vmColor = getHostColor(hostname)

      // Fusionner node et node.data pour que Cytoscape accède aux propriétés directement
      elements.push({
        group: 'nodes',
        data: {
          id: node.id,
          label: node.label,
          type: node.type,
          parent: node.parent,
          ...node.data,  // hostname, status, etc. accessibles directement
          running: isRunning,
          vmColor: vmColor,
        },
      })
    }

    // Ajouter les arêtes (aplatir edge.data pour que Cytoscape y accède directement)
    for (const edge of newEdges) {
      elements.push({
        group: 'edges',
        data: {
          ...edge,
          ...edge.data,  // Aplatir connection_type, source_method, etc.
        },
      })
    }

    // Mettre à jour le graphe
    cy.value.elements().remove()
    cy.value.add(elements)

    // Appliquer les positions sauvegardées (dashboard) ou les positions actuelles (live)
    const hasSavedPositions = Object.keys(savedPositions.value).length > 0
    const hasCurrentPositions = Object.keys(currentPositions).length > 0
    let nodesWithPos = 0
    const nodesWithoutPos = []

    cy.value.nodes().forEach(node => {
      // Priorité: positions sauvegardées (dashboard) > positions actuelles (live refresh)
      const pos = savedPositions.value[node.id()] || currentPositions[node.id()]
      if (pos) {
        node.position({ x: pos.x, y: pos.y })
        nodesWithPos++
      } else {
        nodesWithoutPos.push(node)
      }
    })

    // Appliquer les styles dynamiques aux containers (couleur VM + état)
    applyContainerStyles()

    // S'assurer que les nœuds externes ont leur label visible
    cy.value.nodes('[type="external"]').forEach(node => {
      const label = node.data('label')
      if (label) {
        node.style('label', label)
      }
    })

    // Si premier chargement
    if (isFirstLoad.value) {
      if (hasSavedPositions && nodesWithPos > 0) {
        // Mode dashboard: on a des positions sauvegardées
        // Positionner les nouveaux nœuds (sans position) près de leurs voisins connectés
        if (nodesWithoutPos.length > 0) {
          positionNewNodes(nodesWithoutPos)
        }
        cy.value.fit(undefined, 50)
      } else {
        // Mode live sans positions: lancer le layout complet
        runLayout()
      }
      isFirstLoad.value = false
    } else {
      // Rafraîchissement (pas premier chargement)
      if (nodesWithoutPos.length > 0) {
        // De nouveaux nœuds sont apparus, les positionner près de leurs voisins
        if (nodesWithPos > 0) {
          positionNewNodes(nodesWithoutPos)
        } else {
          // Aucun nœud n'a de position, relancer le layout complet
          runLayout()
        }
      }
      // Si tous les nœuds ont des positions, on ne fait rien (positions conservées)
    }
  }

  // Appliquer les styles dynamiques aux containers
  function applyContainerStyles() {
    if (!cy.value) return

    cy.value.nodes('[type="container"]').forEach(node => {
      const data = node.data()
      const vmColor = data.vmColor || '#4b5563'
      const isRunning = data.running === true

      // Couleur de fond = couleur de la VM
      node.style('background-color', vmColor)

      // Bordure selon l'état (seulement si non sélectionné)
      // On stocke la couleur de bordure normale dans data pour pouvoir la restaurer
      const normalBorderColor = isRunning ? '#22c55e' : '#ef4444'
      node.data('normalBorderColor', normalBorderColor)

      // Ne pas écraser la bordure si le nœud est sélectionné
      if (!node.selected()) {
        node.style('border-color', normalBorderColor)
      }

      node.style('opacity', isRunning ? 1 : 0.6)
    })
  }

  // Mettre à jour la bordure quand un nœud est sélectionné/désélectionné
  function setupSelectionStyles() {
    if (!cy.value) return

    cy.value.on('select', 'node[type="container"]', (event) => {
      event.target.style('border-color', '#fbbf24') // jaune
      event.target.style('border-width', 4)
    })

    cy.value.on('unselect', 'node[type="container"]', (event) => {
      const normalColor = event.target.data('normalBorderColor') || '#22c55e'
      event.target.style('border-color', normalColor)
      event.target.style('border-width', 3)
    })
  }

  function positionNewNodes(nodes) {
    // Positionner les nouveaux nœuds près de leurs voisins ou en périphérie
    const existingNodes = cy.value.nodes().filter(n => !nodes.includes(n))

    if (existingNodes.length === 0) return

    // Calculer le centre et le rayon du graphe existant
    const bb = existingNodes.boundingBox()
    const centerX = (bb.x1 + bb.x2) / 2
    const centerY = (bb.y1 + bb.y2) / 2
    const radius = Math.max(bb.w, bb.h) / 2 + 150

    nodes.forEach((node, i) => {
      // Chercher un voisin connecté avec une position
      const neighbors = node.neighborhood('node')
      const positionedNeighbor = neighbors.filter(n => !nodes.includes(n)).first()

      if (positionedNeighbor && positionedNeighbor.length > 0) {
        // Positionner près du voisin
        const neighborPos = positionedNeighbor.position()
        const angle = Math.random() * 2 * Math.PI
        const dist = 80 + Math.random() * 40
        node.position({
          x: neighborPos.x + Math.cos(angle) * dist,
          y: neighborPos.y + Math.sin(angle) * dist,
        })
      } else {
        // Positionner en périphérie du graphe
        const angle = (i / nodes.length) * 2 * Math.PI
        node.position({
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        })
      }
    })
  }

  function runLayout() {
    if (!cy.value || cy.value.nodes().length === 0) return

    // Layout force-directed simple - tous les nœuds sont indépendants
    cy.value.layout({
      name: 'cose',
      animate: false,
      randomize: true,
      nodeDimensionsIncludeLabels: true,
      nodeRepulsion: 8000,
      idealEdgeLength: 150,
      edgeElasticity: 50,
      gravity: 0.3,
      numIter: 500,
      fit: true,
      padding: 50,
    }).run()

    // Notifier les nouvelles positions après le layout
    if (onPositionChange) {
      cy.value.nodes().forEach(node => {
        const pos = node.position()
        onPositionChange(node.id(), pos.x, pos.y)
      })
    }
  }

  function setSavedPositions(newPositions) {
    savedPositions.value = newPositions || {}
    // Réinitialiser isFirstLoad pour que les positions soient appliquées au prochain updateGraph
    isFirstLoad.value = true
  }

  function getAllPositions() {
    if (!cy.value) return {}

    const positions = {}
    cy.value.nodes().forEach(node => {
      const pos = node.position()
      positions[node.id()] = { x: pos.x, y: pos.y }
    })
    return positions
  }

  function fitGraph() {
    if (cy.value) {
      cy.value.fit(undefined, 50)
    }
  }

  function zoomIn() {
    if (cy.value) {
      cy.value.zoom(cy.value.zoom() * 1.2)
    }
  }

  function zoomOut() {
    if (cy.value) {
      cy.value.zoom(cy.value.zoom() / 1.2)
    }
  }

  function exportPng() {
    if (!cy.value) return

    const png = cy.value.png({
      output: 'blob',
      bg: '#1f2937',
      scale: 2,
      full: true,
    })

    const link = document.createElement('a')
    link.href = URL.createObjectURL(png)
    link.download = `infra-map-${new Date().toISOString().split('T')[0]}.png`
    link.click()
  }

  function updateEdgeVisibility(filters) {
    if (!cy.value || !filters) return

    cy.value.edges().forEach(edge => {
      const data = edge.data()
      let visible = true

      // Filtrer par type de lien
      if (data.type === 'connection') {
        if (!filters.showConnections) {
          visible = false
        } else {
          // Filtrer par type de connexion (réseau)
          const connType = data.connection_type
          if (connType === 'internal' && !filters.showInternal) visible = false
          if (connType === 'cross-host' && !filters.showCrossHost) visible = false
          if (connType === 'external' && !filters.showExternal) visible = false

          // Filtrer par source de détection
          const sourceMethod = data.source_method || 'proc_net'
          // "both" signifie détecté par les deux méthodes
          if (sourceMethod === 'proc_net' && !filters.showProcNet) visible = false
          if (sourceMethod === 'tcpdump' && !filters.showTcpdump) visible = false
          // "both" est visible si au moins un des deux filtres est actif
          if (sourceMethod === 'both' && !filters.showProcNet && !filters.showTcpdump) visible = false
        }
      }

      if (data.type === 'dependency' && !filters.showDependencies) {
        visible = false
      }

      edge.style('display', visible ? 'element' : 'none')
    })
  }

  function updateHostVisibility(filters) {
    if (!cy.value || !filters) return

    // Masquer/afficher les containers par hostname
    cy.value.nodes().forEach(node => {
      const data = node.data()
      if (data.type === 'container') {
        const hostname = data.hostname
        // undefined ou true = visible, false = masqué
        const visible = filters[hostname] !== false
        node.style('display', visible ? 'element' : 'none')
      }
    })

    // Masquer les edges dont source ou target est masqué
    cy.value.edges().forEach(edge => {
      const source = cy.value.getElementById(edge.data('source'))
      const target = cy.value.getElementById(edge.data('target'))
      const sourceVisible = source.length === 0 || source.style('display') !== 'none'
      const targetVisible = target.length === 0 || target.style('display') !== 'none'
      if (!sourceVisible || !targetVisible) {
        edge.style('display', 'none')
      }
    })

    // Masquer les nœuds externes qui n'ont plus aucun voisin visible
    cy.value.nodes('[type="external"]').forEach(node => {
      // Récupérer tous les voisins connectés (containers)
      const neighbors = node.neighborhood('node')
      // Vérifier si au moins un voisin est visible
      const hasVisibleNeighbor = neighbors.some(neighbor => {
        return neighbor.style('display') !== 'none'
      })
      node.style('display', hasVisibleNeighbor ? 'element' : 'none')
    })
  }

  // Watch pour les changements de données
  watch([nodes, edges], ([newNodes, newEdges]) => {
    if (newNodes && newEdges) {
      updateGraph(newNodes, newEdges)
      // Réappliquer les filtres après mise à jour du graphe
      if (edgeFilters?.value) {
        updateEdgeVisibility(edgeFilters.value)
      }
    }
  }, { deep: true })

  // Watch pour les changements de filtres d'edges
  if (edgeFilters) {
    watch(edgeFilters, (newFilters) => {
      updateEdgeVisibility(newFilters)
    }, { deep: true })
  }

  // Watch pour les changements de filtres de VM/hosts
  if (hostFilters) {
    watch(hostFilters, (newFilters) => {
      updateHostVisibility(newFilters)
      // Réappliquer les filtres d'edges après car certains edges peuvent avoir été masqués
      if (edgeFilters?.value) {
        updateEdgeVisibility(edgeFilters.value)
      }
    }, { deep: true })
  }

  onMounted(() => {
    initCytoscape()
  })

  onUnmounted(() => {
    if (cy.value) {
      cy.value.destroy()
    }
  })

  // Recherche et sélection de nœuds par nom
  function searchNodes(query) {
    if (!cy.value) return []

    if (!query || query.trim() === '') {
      // Réinitialiser la sélection et l'opacité
      cy.value.nodes().unselect()
      cy.value.nodes().style('opacity', null)
      cy.value.edges().style('opacity', null)
      return []
    }

    const searchTerm = query.toLowerCase().trim()

    // Trouver les nœuds containers qui correspondent
    const matchingNodes = cy.value.nodes().filter(node => {
      const data = node.data()
      // Chercher dans le label et le nom du container
      const label = (data.label || '').toLowerCase()
      const name = (data.name || '').toLowerCase()
      const containerName = (data.container_name || '').toLowerCase()
      return data.type === 'container' && (
        label.includes(searchTerm) ||
        name.includes(searchTerm) ||
        containerName.includes(searchTerm)
      )
    })

    // Désélectionner tout d'abord
    cy.value.nodes().unselect()

    // Mettre en évidence les nœuds correspondants
    if (matchingNodes.length > 0) {
      // Réduire l'opacité des nœuds non correspondants
      cy.value.nodes().style('opacity', 0.3)
      cy.value.edges().style('opacity', 0.1)

      // Mettre en évidence les nœuds correspondants
      matchingNodes.style('opacity', 1)
      matchingNodes.select()

      // Centrer sur les nœuds correspondants si un seul résultat
      if (matchingNodes.length === 1) {
        cy.value.animate({
          center: { eles: matchingNodes },
          zoom: cy.value.zoom(),
          duration: 300
        })
      } else if (matchingNodes.length <= 5) {
        // Si peu de résultats, ajuster la vue pour les montrer tous
        cy.value.animate({
          fit: { eles: matchingNodes, padding: 100 },
          duration: 300
        })
      }
    } else {
      // Réinitialiser l'opacité si aucun résultat
      cy.value.nodes().style('opacity', null)
      cy.value.edges().style('opacity', null)
    }

    // Retourner les données des nœuds correspondants pour affichage
    return matchingNodes.map(node => node.data())
  }

  // Effacer la recherche
  function clearSearch() {
    if (!cy.value) return

    cy.value.nodes().unselect()
    cy.value.nodes().style('opacity', null)
    cy.value.edges().style('opacity', null)
  }

  return {
    cy,
    selectedNode,
    runLayout,
    fitGraph,
    zoomIn,
    zoomOut,
    exportPng,
    updateEdgeVisibility,
    updateHostVisibility,
    setSavedPositions,
    getAllPositions,
    searchNodes,
    clearSearch,
  }
}
