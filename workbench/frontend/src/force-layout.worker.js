// Force layout computation in a Web Worker to keep the main thread responsive.
// The heavy force simulation is intentionally skipped; the initial layouts
// (sunflower / grouped clusters / concentric focus rings) already produce
// readable, human-friendly positions without blocking the UI.

self.onmessage = function (event) {
  const { nodes, hierarchyEdges, linkEdges, clusterMap, focusedId, pinPositions } = event.data
  const start = Date.now()
  const positions = computeLayout(nodes, clusterMap, focusedId, pinPositions)
  const duration = Date.now() - start
  self.postMessage({ positions, duration })
}

function sunflower(nodes) {
  const pos = {}
  nodes.forEach((n, i) => {
    const angle = i * 2.39996
    const r = Math.sqrt(i + 1) * 55
    pos[n.id] = { x: r * Math.cos(angle), y: r * Math.sin(angle) }
  })
  return pos
}

function groupedInitial(nodes, clusterMap) {
  const byCluster = new Map()
  for (const n of nodes) {
    const c = clusterMap[n.id] || '_default'
    if (!byCluster.has(c)) byCluster.set(c, [])
    byCluster.get(c).push(n)
  }
  const clusters = [...byCluster.keys()]
  const pos = {}
  clusters.forEach((c, i) => {
    const angle = (2 * Math.PI * i) / Math.max(clusters.length, 1) - Math.PI / 2
    const r = 280 + (i % 3) * 80
    const cx = r * Math.cos(angle), cy = r * Math.sin(angle)
    const members = byCluster.get(c)
    members.forEach((n, idx) => {
      const a = (2 * Math.PI * idx) / Math.max(members.length, 1)
      const rr = 30 + Math.sqrt(idx + 1) * 12
      pos[n.id] = { x: cx + rr * Math.cos(a), y: cy + rr * Math.sin(a) }
    })
  })
  return pos
}

function focusInitial(nodes, focusedId) {
  const layerOrder = { L1: 0, L2_light: 1, L2: 2, L3: 3, L4: 4 }
  const pos = {}
  const center = nodes.find((n) => n.id === focusedId)
  if (center) pos[center.id] = { x: 0, y: 0 }
  const others = nodes.filter((n) => n.id !== focusedId)
  const byLayer = [[], [], [], [], []]
  for (const n of others) {
    const idx = layerOrder[n.layer] ?? 2
    byLayer[idx].push(n)
  }
  const radii = [120, 200, 320, 460, 620]
  for (let li = 0; li < byLayer.length; li++) {
    const ring = byLayer[li]
    if (!ring.length) continue
    const r = radii[li]
    ring.forEach((n, idx) => {
      const a = (2 * Math.PI * idx) / ring.length - Math.PI / 2
      pos[n.id] = { x: r * Math.cos(a), y: r * Math.sin(a) }
    })
  }
  return pos
}

function clusterInitial(nodes, clusterMap, focusedId) {
  if (focusedId) return focusInitial(nodes, focusedId)
  if (clusterMap) return groupedInitial(nodes, clusterMap)
  return sunflower(nodes)
}

function computeLayout(nodes, clusterMap, focusedId, pinPositions) {
  if (nodes.length === 0) return {}
  const init = clusterInitial(nodes, clusterMap, focusedId)
  const pos = {}
  for (const n of nodes) {
    if (pinPositions && pinPositions[n.id]) {
      pos[n.id] = { ...pinPositions[n.id] }
    } else {
      pos[n.id] = init[n.id] || { x: 0, y: 0 }
    }
  }
  return pos
}
