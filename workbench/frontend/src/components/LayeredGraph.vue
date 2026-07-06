<template>
  <div class="graph">
    <div v-if="!hasNodes" class="empty-state">
      <div class="empty-title">当前视角无卡片</div>
      <button class="empty-btn" @click="$emit('reset-view')">回到全局 L1</button>
    </div>
    <v-network-graph
      ref="graph"
      v-else
      class="canvas"
      :nodes="nodeMap"
      :edges="edgeMap"
      :layouts="layouts"
      :configs="configs"
      :event-handlers="handlers"
    >
      <template #override-node-label="{ nodeId, scale, x, y }">
        <g v-if="labelVisible(nodeMap[nodeId])" :transform="`translate(${x}, ${y})`">
          <text
            text-anchor="middle"
            dominant-baseline="hanging"
            :font-size="labelFontSize(nodeMap[nodeId], scale)"
            :font-weight="labelFontWeight(nodeMap[nodeId])"
            :fill="labelColor(nodeId)"
            stroke="#ffffff"
            :stroke-width="scale > 1 ? 2.5 : 2"
            stroke-opacity="0.85"
            paint-order="stroke"
            class="node-label-text"
          >
            <tspan
              v-for="(line, idx) in labelLines(nodeMap[nodeId])"
              :key="idx"
              x="0"
              :dy="idx === 0 ? '0.3em' : '1.15em'"
            >{{ line }}</tspan>
          </text>
        </g>
      </template>
      <template #override-node="{ nodeId }">
        <g v-if="nodeMap[nodeId]?.type === 'ns-boundary'" class="ns-boundary">
          <rect
            :x="-nodeMap[nodeId].w / 2"
            :y="-nodeMap[nodeId].h / 2"
            :width="nodeMap[nodeId].w"
            :height="nodeMap[nodeId].h"
            rx="14" ry="14"
            :fill="nodeMap[nodeId].fill"
            :stroke="nodeMap[nodeId].stroke"
            :stroke-width="nodeMap[nodeId].isTerritory ? 3 : 2"
            stroke-opacity="0.9"
          />
          <text
            :x="-nodeMap[nodeId].w / 2 + 10"
            :y="-nodeMap[nodeId].h / 2 + (nodeMap[nodeId].isTerritory ? 28 : 22)"
            :font-size="nodeMap[nodeId].isTerritory ? 20 : 16"
            font-weight="700"
            :fill="nodeMap[nodeId].stroke"
          >{{ nodeMap[nodeId].title }}</text>
        </g>
        <g v-else-if="nodeMap[nodeId]?.type === 'namespace'" class="ns-tile">
          <rect
            :x="-tileInfo(nodeMap[nodeId]).w / 2"
            :y="-tileInfo(nodeMap[nodeId]).h / 2"
            :width="tileInfo(nodeMap[nodeId]).w"
            :height="tileInfo(nodeMap[nodeId]).h"
            rx="18" ry="18"
            :fill="tileInfo(nodeMap[nodeId]).color + '20'"
            :stroke="tileInfo(nodeMap[nodeId]).color"
            :stroke-width="tileInfo(nodeMap[nodeId]).isMore ? 2 : 3"
            :stroke-dasharray="tileInfo(nodeMap[nodeId]).isMore ? '6 4' : '0'"
          />
          <text
            text-anchor="middle"
            :fill="tileInfo(nodeMap[nodeId]).color"
            :y="tileInfo(nodeMap[nodeId]).isMore ? 4 : -6"
            :font-size="tileInfo(nodeMap[nodeId]).isMore ? 13 : 22"
            font-weight="700"
          >{{ tileTitleParts(nodeMap[nodeId]).main }}</text>
          <text
            v-if="tileTitleParts(nodeMap[nodeId]).sub"
            text-anchor="middle"
            :fill="tileInfo(nodeMap[nodeId]).color"
            :y="22"
            :font-size="14"
            font-weight="500"
          >{{ tileTitleParts(nodeMap[nodeId]).sub }}</text>
        </g>
      </template>
    </v-network-graph>

    <div v-if="hasNodes" class="legend layer-help" :class="{ collapsed: !layerHelpOpen }">
      <div class="legend-title">
        分层（描边色）
        <button class="legend-toggle" @click="layerHelpOpen = !layerHelpOpen">{{ layerHelpOpen ? '−' : '+' }}</button>
      </div>
      <div v-if="layerHelpOpen" class="legend-body">
        <div class="layer-row" v-for="L in layerOrder" :key="L.key">
          <span class="ring" :style="{ borderColor: layerColor[L.key] }"></span>
          <span class="layer-label">{{ L.label }}</span>
          <span class="layer-hint">{{ L.hint }}</span>
        </div>
      </div>
    </div>

    <div v-if="hasNodes" class="legend type-help" :class="{ collapsed: !typeHelpOpen }">
      <div class="legend-title">
        类型（填充色）
        <button class="legend-toggle" @click="typeHelpOpen = !typeHelpOpen">{{ typeHelpOpen ? '−' : '+' }}</button>
      </div>
      <div v-if="typeHelpOpen" class="legend-body">
        <div class="type-grid">
          <div class="type-row" v-for="(color, type) in typeColor" :key="type">
            <span class="dot" :style="{ background: color }"></span>
            <span>{{ type }}</span>
          </div>
        </div>
        <div class="legend-sep"></div>
        <div class="legend-title">边类型</div>
        <div class="edge-row">
          <svg width="36" height="10"><line x1="2" y1="5" x2="34" y2="5" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 3"/></svg>
          <span>卢曼父子</span>
        </div>
        <div class="edge-row">
          <svg width="36" height="10"><line x1="2" y1="5" x2="34" y2="5" stroke="#2563eb" stroke-width="2.5"/></svg>
          <span>关联关系</span>
        </div>
      </div>
    </div>

    <div v-if="hasNodes" class="meta">
      <span>{{ nodes.length }} 节点</span>
      <span class="sep">·</span>
      <span>{{ hierarchyEdges.length }} 父子</span>
      <span class="sep">·</span>
      <span>{{ linkEdges.length }} 关联</span>
      <span class="sep">·</span>
      <span class="hint">滚轮缩放 · 单击选卡 · 双击聚焦</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, toRaw, onMounted } from 'vue'
import { VNetworkGraph } from 'v-network-graph'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  hierarchyEdges: { type: Array, default: () => [] },
  linkEdges: { type: Array, default: () => [] },
  clusterMap: { type: Object, default: null },
  selectedId: { type: String, default: '' },
  viewMode: { type: String, default: 'overview' },
  focusedId: { type: String, default: '' },
})
const emit = defineEmits(['pick', 'focus', 'reset-view'])

const layerOrder = [
  { key: 'L1', label: 'L1',  hint: '原始材料' },
  { key: 'L2_light', label: 'L2轻', hint: '轻摘要' },
  { key: 'L2',       label: 'L2',  hint: '主题/结构卡' },
  { key: 'L3',       label: 'L3',  hint: '深化卡' },
  { key: 'L4',       label: 'L4',  hint: '模式/判断' },
]
const layerColor = {
  L1: '#94a3b8', L2_light: '#a3bffa', L2: '#6366f1',
  L3: '#10b981', L4: '#f59e0b',
}
const nsColor = {
  fin: '#3b82f6', fit: '#14b8a6', gen: '#f59e0b',
  llm: '#ec4899', phil: '#ef4444',
}
const typeColor = {
  概念: '#3b82f6', 结构: '#8b5cf6', 机制: '#14b8a6', 案例: '#f59e0b',
  判断: '#ec4899', 反思: '#64748b', 模式: '#0d9488', 主题: '#2563eb',
  namespace: '#94a3b8',
}

const MORE_NODE_ID = '__more__'
const hoveredId = ref('')
const layerHelpOpen = ref(false)
const typeHelpOpen = ref(false)
const graph = ref(null)
const hasNodes = computed(() => props.nodes.length > 0)
// When the view gets crowded, labels shrink to a single line to reduce overlap.
const denseView = computed(() => props.nodes.length > 30)

// focusSet: the selected or focused card + its 1-hop neighbourhood.
// IMPORTANT: intentionally does NOT depend on hoveredId. Earlier versions
// included hoveredId here, which meant every mouse enter/leave rebuilt this
// Set AND cascaded into edgeMap (recreating every edge object) — that was
// the dominant source of jank at 700+ nodes. Hover now only affects the
// hovered node itself (via the node hover config + label visibility).
const focusSet = computed(() => {
  const focal = props.selectedId || props.focusedId
  if (!focal) return null
  const s = new Set([focal])
  for (const e of props.linkEdges) {
    if (e.source === focal) s.add(e.target)
    else if (e.target === focal) s.add(e.source)
  }
  for (const e of props.hierarchyEdges) {
    if (e.source === focal) s.add(e.target)
    else if (e.target === focal) s.add(e.source)
  }
  return s
})

const nodeMap = computed(() => {
  const m = { ...boundaryNodes.value }
  for (const n of props.nodes) {
    const raw = toRaw(n)
    m[raw.id] = { name: truncate(raw.title, 32), ...raw }
  }
  return m
})

// edgeMap: pure function of the edge data. No hovered/focal state — those
// drive styling via the focusSet computed, which the edge config reads.
// This keeps the edge object map referentially stable across hovers.
const edgeMap = computed(() => {
  const m = {}
  let i = 0
  const showHierarchy = !props.focusedId
  if (showHierarchy) {
    for (const e of props.hierarchyEdges) {
      const raw = toRaw(e)
      m[`h${i++}`] = {
        source: raw.source,
        target: raw.target,
        kind: 'hierarchy',
      }
    }
  }
  for (const e of props.linkEdges) {
    const raw = toRaw(e)
    m[`l${i++}`] = {
      source: raw.source,
      target: raw.target,
      kind: 'link',
    }
  }
  return m
})

// ----------------- Layout -----------------
const layoutPositions = ref({})

function clusterInitial(nodes, clusterMap, focusedId, viewMode) {
  if (focusedId) return focusInitial(nodes, focusedId)
  // L0 namespace overview: render territories as large tiles on a meta grid.
  if (viewMode === 'ns_overview') return territoryLayout(nodes)
  // L1+ overview: each ns is a rectangular block of ID-sorted cards.
  return gridByNamespace(nodes, clusterMap)
}

const CELL_W = 110
const CELL_H = 84
const NS_GAP_X = 200
const NS_GAP_Y = 140
const META_COLS = 2

// L0 territory layout: large tiles arranged in a small meta grid.
// Each tile is big enough to show the full "ns (count)" label.
const TERRITORY_W = 200
const TERRITORY_H = 140
const TERRITORY_GAP_X = 60
const TERRITORY_GAP_Y = 50
function territoryLayout(nodes) {
  if (!nodes.length) return {}
  const cols = nodes.length <= 4 ? 2 : 3
  const sorted = [...nodes].sort((a, b) => a.id.localeCompare(b.id))
  const pos = {}
  sorted.forEach((n, i) => {
    const c = i % cols
    const r = Math.floor(i / cols)
    pos[n.id] = {
      x: c * (TERRITORY_W + TERRITORY_GAP_X) + TERRITORY_W / 2,
      y: r * (TERRITORY_H + TERRITORY_GAP_Y) + TERRITORY_H / 2,
    }
  })
  return pos
}

function nsOf(node) {
  // node.namespace is set by backend; fall back to id prefix
  return node.namespace || (node.id.includes(':') ? node.id.split(':')[0] : '_default')
}

// Layout: each namespace occupies a rectangular block; inside the block cards
// are placed on a grid ordered by id.localeCompare. Blocks themselves are
// packed into a meta-grid. Result: ID-adjacent cards are physically adjacent,
// and each ns has clear bounds (drawn via clusterBounds).
function gridByNamespace(nodes, clusterMap) {
  if (!nodes.length) return {}
  const byNs = new Map()
  for (const n of nodes) {
    const c = clusterMap ? (clusterMap[n.id] || nsOf(n)) : nsOf(n)
    if (!byNs.has(c)) byNs.set(c, [])
    byNs.get(c).push(n)
  }
  // Sort each ns's cards by id for stable, dictionary-adjacent placement.
  for (const arr of byNs.values()) {
    arr.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  }

  // First pass: measure each ns block.
  const nsOrder = [...byNs.keys()].sort((a, b) => {
    if (a === MORE_NODE_ID) return 1
    if (b === MORE_NODE_ID) return -1
    return a.localeCompare(b)
  })
  const blocks = nsOrder.map((ns) => {
    const cards = byNs.get(ns)
    const cols = Math.max(1, Math.ceil(Math.sqrt(cards.length)))
    const rows = Math.ceil(cards.length / cols)
    return {
      ns,
      cards,
      cols,
      rows,
      w: cols * CELL_W,
      h: rows * CELL_H,
    }
  })

  // Second pass: pack blocks into a meta-grid.
  // Few namespaces (e.g. L0 territories) get 3 columns so they spread out;
  // many namespaces get 2 columns to keep the sheet readable.
  const metaCols = nsOrder.length <= 6 ? 3 : META_COLS
  const pos = {}
  let cursorX = 0
  let cursorY = 0
  let rowH = 0
  blocks.forEach((b, i) => {
    if (i > 0 && i % metaCols === 0) {
      cursorY += rowH + NS_GAP_Y
      cursorX = 0
      rowH = 0
    }
    b.cards.forEach((n, idx) => {
      const r = Math.floor(idx / b.cols)
      const c = idx % b.cols
      pos[n.id] = {
        x: cursorX + c * CELL_W + CELL_W / 2,
        y: cursorY + r * CELL_H + CELL_H / 2,
      }
    })
    cursorX += b.w + NS_GAP_X
    if (b.h > rowH) rowH = b.h
  })
  return pos
}

// Focus mode: center node at origin, others on concentric rings by layer
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
  const radii = [80, 130, 190, 260, 340]
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

watch(() => [props.nodes, props.hierarchyEdges, props.linkEdges, props.clusterMap, props.focusedId, props.viewMode], () => {
  // Recompute the full layout on every change.
  // gridByNamespace is O(N) and stable: when new cards arrive via expand,
  // they slot into their id-sorted position inside their ns block. Existing
  // cards keep their position unless a newly-arrived card has a smaller id
  // and pushes them one cell to the right — which matches user intuition
  // ("the new card appeared between its alphabetical neighbours").
  // Pinning was removed because the previous sunflower pinning produced
  // visually incoherent layouts after multiple expands.
  const init = clusterInitial(props.nodes, props.clusterMap, props.focusedId, props.viewMode)
  const fresh = {}
  for (const n of props.nodes) {
    fresh[n.id] = init[n.id] || { x: 0, y: 0 }
  }
  layoutPositions.value = fresh
}, { immediate: true, deep: false })

const layouts = computed(() => ({
  nodes: { ...layoutPositions.value, ...boundaryLayouts.value },
}))

// Cluster bounding boxes — drawn whenever we're NOT in focus mode.
// In focus mode there's only one center, so bounds are pointless.
// In overview / ns_overview, each namespace gets a labelled rectangle that
// gives the "map" feel: you can see which block is fin vs llm vs phil.
const clusterBounds = computed(() => {
  if (props.focusedId) return []
  // L0 uses large territory tiles; no need for extra bounding rectangles.
  if (props.viewMode === 'ns_overview') return []
  const groups = new Map()
  for (const n of props.nodes) {
    if (n.id === MORE_NODE_ID) continue
    const c = (props.clusterMap && props.clusterMap[n.id]) || nsOf(n)
    if (!groups.has(c)) groups.set(c, [])
    groups.get(c).push(n)
  }
  const PAD = 60
  const bounds = []
  for (const [c, nodes] of groups) {
    const ids = nodes.map((n) => n.id)
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const id of ids) {
      const p = layoutPositions.value[id]
      if (!p) continue
      if (p.x < minX) minX = p.x
      if (p.y < minY) minY = p.y
      if (p.x > maxX) maxX = p.x
      if (p.y > maxY) maxY = p.y
    }
    if (minX === Infinity) continue
    const color = c in nsColor ? nsColor[c] : '#94a3b8'
    // For territory (namespace-only) groups, show the real card count from the
    // virtual node's title instead of the virtual-node count (1).
    const isTerritory = nodes.length === 1 && nodes[0].type === 'namespace'
    const label = isTerritory ? (nodes[0].title || c) : c
    bounds.push({
      id: c, x: minX - PAD, y: minY - PAD,
      w: maxX - minX + 2 * PAD, h: maxY - minY + 2 * PAD,
      label, count: ids.length,
      fill: color + (isTerritory ? '26' : '14'), stroke: color,
      isTerritory,
    })
  }
  return bounds
})

// Synthetic "ns-boundary" nodes sit behind real cards and draw the labelled
// rectangle for each namespace block. They live inside the graph coordinate
// system, so they pan/zoom together with the real nodes.
const boundaryNodes = computed(() => {
  const m = {}
  for (const b of clusterBounds.value) {
    const bid = `__bound__${b.id}`
    m[bid] = {
      id: bid,
      type: 'ns-boundary',
      title: b.label,
      name: b.label,
      namespace: b.id,
      w: b.w,
      h: b.h,
      fill: b.fill,
      stroke: b.stroke,
      isTerritory: b.isTerritory,
    }
  }
  return m
})

const boundaryLayouts = computed(() => {
  const pos = {}
  for (const b of clusterBounds.value) {
    pos[`__bound__${b.id}`] = { x: b.x + b.w / 2, y: b.y + b.h / 2 }
  }
  return pos
})

const configs = computed(() => ({
  view: {
    scalingObjects: false, panEnabled: true, zoomEnabled: true,
    fitContentMargin: 40, autoPanAndZoomOnLoad: 'fit-content',
  },
  node: {
    selectable: true, hover: true, draggable: false,
    normal: {
      radius: (n) => nodeRadius(n),
      color: (n) => nodeFillColor(n),
      strokeWidth: (n) => nodeStrokeWidth(n),
      strokeColor: (n) => nodeStrokeColor(n),
    },
    hover: { color: '#2563eb', strokeWidth: 2, strokeColor: '#fff', radius: (n) => nodeRadius(n) + 2 },
    label: {
      visible: (n) => n.type !== 'ns-boundary' && n.type !== 'namespace',
      fontSize: 11,
      color: '#374151',
      lineHeight: 1.2, margin: 5, direction: 'south',
      background: false,
    },
  },
  edge: {
    selectable: false,
    normal: {
      width: (e) => edgeWidth(e),
      color: (e) => edgeColor(e),
      dasharray: (e) => e.kind === 'hierarchy' ? 4 : 0,
    },
    hover: { color: '#94a3b8' },
  },
}))

// Nodes whose label should always be visible (map landmarks).
const LANDMARK_TYPES = new Set(['namespace', '主题'])

function shouldShowLabel(n) {
  if (n.type === 'ns-boundary') return false
  // Territory/MORE tiles draw their own labels inside the tile shape.
  if (n.type === 'namespace') return false
  if (LANDMARK_TYPES.has(n.type)) return true
  // Always show L4 cards (rare, high-value) and the currently focal nodes
  if (n.layer === 'L4') return true
  if (n.id === hoveredId.value) return true
  if (n.id === props.selectedId) return true
  if (n.id === props.focusedId) return true
  // In dense views, hide most labels to avoid overlap; in moderate views,
  // show every label so the map is readable.
  if (props.nodes.length <= 160) return true
  // In focus mode, only show labels for center + direct neighbors (1-hop)
  if (props.focusedId) {
    if (!focusSet.value) return false
    for (const e of props.linkEdges) {
      if ((e.source === props.focusedId && e.target === n.id) ||
          (e.target === props.focusedId && e.source === n.id)) {
        return true
      }
    }
    for (const e of props.hierarchyEdges) {
      if ((e.source === props.focusedId && e.target === n.id) ||
          (e.target === props.focusedId && e.source === n.id)) {
        return true
      }
    }
    return false
  }
  if (focusSet.value && focusSet.value.has(n.id)) return true
  return false
}

// Label visibility: keep the map readable by not drowning it in text.
// - Hover/select/focus always get a label.
// - Small views (≤40 nodes) can show every label.
// - Moderate views (≤120 nodes) show landmark labels (theme / L4 / ns-boundary).
// - Dense views (>120 nodes) hide most labels; hover to read.
function labelVisible(n) {
  if (!n) return false
  if (n.type === 'ns-boundary' || n.type === 'namespace') return false
  if (n.id === hoveredId.value) return true
  if (n.id === props.selectedId) return true
  if (n.id === props.focusedId) return true
  if (props.focusedId && focusSet.value?.has(n.id)) return true
  if (!props.focusedId && focusSet.value?.has(n.id)) return true
  // Small/medium views (≤80 nodes) can show every label; >30 nodes uses single line.
  if (props.nodes.length <= 80) return true
  // Dense views (>80 nodes): only show high-value landmarks to avoid a soup of text.
  if (LANDMARK_TYPES.has(n.type) || n.layer === 'L4') return true
  return false
}

function isThemeCard(n) {
  return n.type === '主题' || n.type === 'namespace'
}

function withAlpha(base, focus, id) {
  if (!focus) return base
  return focus.has(id) ? base : base + '33'
}
function labelColor(id) {
  if (!focusSet.value) return '#374151'
  return focusSet.value.has(id) ? '#111827' : '#9ca3af'
}
function labelFontSize(n, scale) {
  if (n?.type === 'namespace') return Math.round(13 * scale)
  return Math.round(10 * scale)
}
function labelFontWeight(n) {
  return n?.type === 'namespace' ? 700 : 400
}
function edgeInFocus(e) {
  const fs = focusSet.value
  if (!fs) return false
  return fs.has(e.source) && fs.has(e.target)
}
function edgeWidth(e) {
  if (edgeInFocus(e)) return e.kind === 'link' ? 3.2 : 2
  return e.kind === 'link' ? 1 : 0.7
}
function edgeColor(e) {
  if (e.kind === 'hierarchy') {
    if (!focusSet.value) return 'rgba(148, 163, 184, 0.28)'
    return edgeInFocus(e) ? '#64748b' : 'rgba(148, 163, 184, 0.12)'
  }
  // link edge - visible but unobtrusive in overview; emphasized on focus
  if (props.viewMode === 'ns_overview') return 'rgba(37, 99, 235, 0.08)'
  if (!focusSet.value) return 'rgba(37, 99, 235, 0.22)'
  return edgeInFocus(e) ? '#1d4ed8' : 'rgba(37, 99, 235, 0.12)'
}
function nodeFillColor(n) {
  if (n.type === 'ns-boundary') return 'transparent'
  if (n.type === 'namespace') return 'transparent'  // tile draws its own fill
  return typeColor[n.type] || layerColor[n.layer] || '#94a3b8'
}
function nodeRadius(n) {
  if (n.type === 'ns-boundary') return 0
  if (n.type === 'namespace') return 0   // namespace tiles are drawn as rects
  // In focus mode keep the center card prominent but not overwhelming.
  if (n.id === props.focusedId) return 12
  if (n.id === props.selectedId) return 11
  if (isThemeCard(n)) return 8
  const use = (n.use_count || 0) + (n.search_count || 0)
  return 4 + Math.min(use * 0.12, 0.8)
}
function nodeStrokeWidth(n) {
  if (n.type === 'ns-boundary') return 0
  if (n.type === 'namespace') return 0
  if (n.id === props.focusedId) return 2
  if (n.id === props.selectedId) return 1.8
  if (isThemeCard(n) || n.type === 'namespace') return 1.2
  return 0.8
}
function nodeStrokeColor(n) {
  if (n.type === 'ns-boundary') return 'transparent'
  if (n.type === 'namespace') return 'transparent'
  if (n.id === props.focusedId || n.id === props.selectedId) return '#2563eb'
  if (props.clusterMap && props.clusterMap[n.id]) {
    const c = props.clusterMap[n.id]
    return c in nsColor ? nsColor[c] : '#94a3b8'
  }
  return layerColor[n.layer] || '#fff'
}

function tileInfo(n) {
  const isMore = n.id === MORE_NODE_ID
  const color = isMore ? '#64748b' : (nsColor[n.namespace || n.id] || '#94a3b8')
  return {
    w: isMore ? 180 : TERRITORY_W,
    h: isMore ? 100 : TERRITORY_H,
    color,
    isMore,
  }
}
function tileTitleParts(n) {
  const text = n.title || n.name || n.id
  if (n.id === MORE_NODE_ID) return { main: text, sub: '' }
  const m = text.match(/^(.+?)\s*\((\d+)\)$/)
  if (!m) return { main: text, sub: '' }
  return { main: m[1], sub: `(${m[2]})` }
}

let clickTimer = null
const handlers = {
  'node:pointerenter': ({ node }) => { hoveredId.value = node },
  'node:pointerleave': () => { hoveredId.value = '' },
  'node:click': ({ node }) => {
    if (node.startsWith('__bound__')) return
    // Distinguish single vs double click via 250ms timer
    if (clickTimer) {
      clearTimeout(clickTimer)
      clickTimer = null
      emit('focus', node)  // dblclick = focus
    } else {
      clickTimer = setTimeout(() => {
        emit('pick', node)  // single click = expand
        clickTimer = null
      }, 250)
    }
  },
  'node:dblclick': ({ node }) => {
    if (node.startsWith('__bound__')) return
    // Native double-click fallback for browsers/touchpads that fire it
    if (clickTimer) { clearTimeout(clickTimer); clickTimer = null }
    emit('focus', node)
  },
}

function labelLines(n) {
  let text = n?.title || n?.name || ''
  if (!text) return ['']
  // The "more" virtual node should show its full explanatory label.
  if (n?.id === MORE_NODE_ID) {
    return [text]
  }
  // For territory nodes, show just the namespace name (the count is already
  // visible in the cluster bound label and the meta counter).
  if (n?.type === 'namespace') {
    text = text.split(' ')[0]
  }
  const maxLine = n?.type === 'namespace' ? 12 : 16
  const maxRows = n?.type === 'namespace' ? 1 : (denseView.value ? 1 : 2)
  const lines = []
  for (let i = 0; i < text.length && lines.length < maxRows; i += maxLine) {
    lines.push(text.slice(i, i + maxLine))
  }
  if (text.length > maxLine * maxRows) {
    const last = lines[lines.length - 1]
    lines[lines.length - 1] = last.slice(0, -1) + '…'
  }
  return lines
}

function truncate(s, max) {
  if (!s) return ''
  return s.length > max ? s.slice(0, max) + '…' : s
}
</script>

<style scoped>
.graph { height: 100%; width: 100%; position: relative; background: var(--bg); }
.canvas { width: 100%; height: 100%; }
.empty-state {
  height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: var(--text-2);
}
.empty-title { font-size: 16px; font-weight: 500; }
.empty-btn {
  border: 1px solid var(--primary); background: var(--primary);
  color: #fff; padding: 8px 16px;
  border-radius: 6px; cursor: pointer; font-size: 13px;
}
.empty-btn:hover { opacity: 0.9; }

.ns-boundary { pointer-events: none; }

.legend {
  position: absolute;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(6px);
  font-size: 12px;
  line-height: 1.55;
}
.legend-title {
  font-size: 11px; font-weight: 700; color: var(--text);
  text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: 6px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.legend-toggle {
  border: none; background: var(--bg); color: var(--text-2);
  width: 18px; height: 18px; border-radius: 4px;
  font-size: 13px; line-height: 1; cursor: pointer; padding: 0;
}
.legend-toggle:hover { background: var(--border); color: var(--text); }
.legend.collapsed { padding: 6px 10px; }
.legend.collapsed .legend-title { margin-bottom: 0; }
.legend-sep { height: 1px; background: var(--border); margin: 8px 0; }
.layer-help { bottom: 16px; left: 16px; max-width: 220px; }
.layer-row { display: flex; align-items: center; gap: 8px; color: var(--text-2); padding: 2px 0; }
.ring {
  width: 12px; height: 12px; border-radius: 50%;
  border: 2.5px solid; background: transparent; flex-shrink: 0;
}
.layer-label { font-weight: 600; color: var(--text); min-width: 28px; }
.layer-hint { color: var(--text-2); font-size: 11px; }

.type-help { bottom: 16px; right: 16px; max-width: 220px; }
.type-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px 12px; }
.type-row { display: flex; align-items: center; gap: 6px; color: var(--text-2); }
.dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.edge-row { display: flex; align-items: center; gap: 8px; color: var(--text-2); padding: 3px 0; }

.meta {
  position: absolute; top: 16px; right: 16px;
  background: rgba(255,255,255,0.96);
  border: 1px solid var(--border);
  border-radius: 8px; padding: 5px 10px;
  font-size: 12px; color: var(--text-2);
  display: flex; gap: 6px;
  box-shadow: var(--shadow-sm);
}
.meta .sep { opacity: 0.5; }
.meta .hint { color: var(--text-2); font-size: 11px; margin-left: 4px; }

</style>
