<template>
  <div class="app">
    <header class="top">
      <div class="brand">Loom Workbench</div>

      <div class="search" v-click-outside="closeSearch">
        <input
          v-model="q"
          placeholder="搜索 (≥2 字)"
          @keyup.enter="runSearch"
          @input="onSearchInput"
          @focus="onSearchFocus"
        />
        <button class="search-btn" @click="runSearch">搜</button>
        <div v-if="searchOpen && (searchResults.length || searched)" class="search-panel">
          <div v-if="searched && !searchResults.length" class="search-empty">无结果</div>
          <div
            v-for="r in searchResults"
            :key="r.id"
            class="search-item"
            @click="pickSearch(r.id)"
          >
            <span class="search-layer" :style="{ background: layerColor[r.layer] }">{{ r.layer }}</span>
            <span class="search-type">[{{ r.type }}]</span>
            <span class="search-title">{{ r.title }}</span>
            <span class="search-id">{{ r.id }}</span>
          </div>
        </div>
      </div>

      <div class="stats">
        <button v-for="L in layerOrder" :key="L.key"
          class="chip"
          :class="{ zero: (layerCounts[L.key] || 0) === 0, active: activeLayer === L.key }"
          :title="activeLayer === L.key ? `取消 ${L.label} 筛选` : `只看 ${L.label}`"
          @click="toggleLayer(L.key)"
        >
          <span class="chip-dot" :style="{ background: layerColor[L.key] }"></span>
          {{ L.label }} <b>{{ layerCounts[L.key] || 0 }}</b>
        </button>
      </div>

      <div v-if="isLargeNamespace" class="graph-mode">
        <button
          class="mode-btn"
          :class="{ active: graphMode === 'summary' }"
          @click="setGraphMode('summary')"
          title="只画 L3/L4、当前选中和最近访问"
        >摘要</button>
        <button
          class="mode-btn"
          :class="{ active: graphMode === 'all' }"
          @click="setGraphMode('all')"
          title="显示当前筛选下的全部节点"
        >全量</button>
        <span class="mode-count">{{ graphNodeCount }} / {{ namespaceCards.length }}</span>
      </div>
    </header>

    <main class="body">
      <aside class="left">
        <Sidebar
          :ns-counts="nsCounts"
          :tags="tags"
          :active-tags="activeTags"
          :active-ns="activeNs"
          :selected-id="workspaceSelectedId"
          :recent-cards="recentCards"
          :cards="sidebarCards"
          @pick-ns="onPickNs"
          @toggle-tag="toggleTag"
          @pick-card="onPickCard"
        />
      </aside>
      <section class="center">
        <GraphExplorer
          ref="explorer"
          :tree-roots="graphTreeRoots"
          :link-edges="visibleLinkEdges"
          :all-link-edges="allLinkEdges"
          :card-index="cardIndex"
          :selected-id="workspaceSelectedId"
          :focus-data="focusData"
          @select="onSelectCard"
          @focus="onFocusCard"
          @navigate="onNavigate"
        />
      </section>
      <div class="panel-resizer" title="拖拽调整详情栏宽度" @mousedown="startResize"></div>
      <aside class="right" :style="{ width: `${rightWidth}px` }">
        <CardPanel
          :card-id="detailSelectedId"
          :can-back="historyIndex > 0"
          :can-forward="historyIndex < history.length - 1"
          :history="history"
          :history-index="historyIndex"
          @pick="onDetailPickCard"
          @focus="onFocusCard"
          @close="detailSelectedId = ''"
          @back="goBack"
          @forward="goForward"
          @jump="onPickHistory"
        />
      </aside>
    </main>
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  getStats, getVersion, getCardsByNs, getGraphByNs, getGraphCluster,
  getTags,
  search as apiSearch,
} from './api.js'
import GraphExplorer from './components/graph/GraphExplorer.vue'
import Sidebar from './components/graph/Sidebar.vue'
import CardPanel from './components/CardPanel.vue'

// click-outside directive for search dropdown
const vClickOutside = {
  mounted(el, binding) {
    el._clickOutside = (e) => { if (!el.contains(e.target)) binding.value() }
    document.addEventListener('click', el._clickOutside, true)
  },
  unmounted(el) {
    document.removeEventListener('click', el._clickOutside, true)
  },
}

const layerOrder = [
  { key: 'L1', label: 'L1' },
  { key: 'L2_light', label: 'L2轻' },
  { key: 'L2',       label: 'L2' },
  { key: 'L3',       label: 'L3' },
  { key: 'L4',       label: 'L4' },
]
const layerColor = {
  L1: '#94a3b8', L2_light: '#a3bffa', L2: '#6366f1',
  L3: '#10b981', L4: '#f59e0b',
}

const activeNs = ref('gen')
const activeLayer = ref('')
const activeTags = ref([])
const detailSelectedId = ref('')
const workspaceSelectedId = ref('')
const treeRoots = shallowRef([])
const linkEdges = shallowRef([])
const allLinkEdges = shallowRef([])
const cardIndex = shallowRef({})
const namespaceCards = shallowRef([])
const focusData = ref(null)
const nsCounts = ref({})
const layerCounts = ref({})
const tags = ref([])
const explorer = ref(null)
const rightWidth = ref(360)
const MIN_RIGHT_WIDTH = 300
const MAX_RIGHT_WIDTH = 720
const graphMode = ref('summary')
const GRAPH_SUMMARY_THRESHOLD = 80
const GRAPH_SUMMARY_NODE_LIMIT = 160
let dataRequestSeq = 0
let graphRequestSeq = 0
const cardsCache = new Map()
const graphCache = new Map()
let cacheVersionKey = ''

// 搜索
const q = ref('')
const searchOpen = ref(false)
const searched = ref(false)
const searchResults = ref([])

// 浏览历史
const history = ref([])
const historyIndex = ref(-1)
const HISTORY_CAP = 50

function flattenTreeIds(nodes, ids = new Set()) {
  for (const node of nodes || []) {
    ids.add(node.id)
    flattenTreeIds(node.children || [], ids)
  }
  return ids
}

function filterTreeByLayer(nodes, layer) {
  if (!layer) return nodes || []
  const result = []
  for (const node of nodes || []) {
    const children = filterTreeByLayer(node.children || [], layer)
    if (node.layer === layer) {
      result.push({ ...node, children })
    } else {
      result.push(...children)
    }
  }
  return result
}

const visibleTreeRoots = computed(() => filterTreeByLayer(treeRoots.value, activeLayer.value))
const isLargeNamespace = computed(() => namespaceCards.value.length > GRAPH_SUMMARY_THRESHOLD)
const summaryIds = computed(() => {
  if (!isLargeNamespace.value || graphMode.value === 'all') return null
  const ids = new Set()
  let summaryCount = 0
  for (const card of namespaceCards.value) {
    const matchesSummaryLayer = activeLayer.value
      ? card.layer === activeLayer.value
      : (card.layer === 'L3' || card.layer === 'L4')
    if (matchesSummaryLayer) {
      ids.add(card.id)
      summaryCount++
      if (summaryCount >= GRAPH_SUMMARY_NODE_LIMIT) break
    }
  }
  if (workspaceSelectedId.value) ids.add(workspaceSelectedId.value)
  for (const card of recentCards.value) ids.add(card.id)
  return ids
})
function filterTreeByIds(nodes, ids) {
  if (!ids) return nodes || []
  const result = []
  for (const node of nodes || []) {
    const children = filterTreeByIds(node.children || [], ids)
    if (ids.has(node.id)) {
      result.push({ ...node, children })
    } else {
      result.push(...children)
    }
  }
  return result
}
const graphTreeRoots = computed(() => filterTreeByIds(visibleTreeRoots.value, summaryIds.value))
const graphNodeCount = computed(() => flattenTreeIds(graphTreeRoots.value).size)
const visibleLinkEdges = computed(() => {
  const ids = flattenTreeIds(graphTreeRoots.value)
  if (!activeLayer.value && !summaryIds.value) return linkEdges.value
  return linkEdges.value.filter(e => ids.has(e.source) && ids.has(e.target))
})
const activeTagParam = computed(() => activeTags.value.join(','))
const sidebarCards = computed(() => {
  const cards = namespaceCards.value || []
  const filtered = activeLayer.value
    ? cards.filter(card => card.layer === activeLayer.value)
    : cards
  return [...filtered].sort((a, b) => a.id.localeCompare(b.id))
})

// 最近访问（去重，最多 8 条）
const recentCards = computed(() => {
  const seen = new Set()
  const result = []
  for (let i = history.value.length - 1; i >= 0 && result.length < 8; i--) {
    const id = history.value[i]
    if (seen.has(id)) continue
    seen.add(id)
    const card = cardIndex.value[id]
    if (card) result.push(card)
  }
  return result
})

function pushHistory(id) {
  if (!id) return
  if (history.value[historyIndex.value] === id) return
  history.value = history.value.slice(0, historyIndex.value + 1)
  history.value.push(id)
  if (history.value.length > HISTORY_CAP) history.value.shift()
  historyIndex.value = history.value.length - 1
}

// 数据加载
function asGraphRoots(cards) {
  return (cards || []).map(card => ({ ...card, children: [] }))
}

function filterKey(ns, tagValuesOrParam = activeTags.value) {
  const tagParam = Array.isArray(tagValuesOrParam)
    ? tagValuesOrParam.join(',')
    : (tagValuesOrParam || '')
  return `${ns}|${tagParam}`
}

function graphIncludeParam() {
  const ids = new Set()
  if (workspaceSelectedId.value) ids.add(workspaceSelectedId.value)
  for (const card of recentCards.value) ids.add(card.id)
  return [...ids].join(',')
}

function graphHasCard(id) {
  return flattenTreeIds(treeRoots.value).has(id)
}

async function refreshDataVersion() {
  const version = await getVersion()
  const next = `${version.cards_updated_at}|${version.cards_count}|${version.tag_edges}`
  if (cacheVersionKey && cacheVersionKey !== next) {
    cardsCache.clear()
    graphCache.clear()
    const [tagsData, statsData] = await Promise.all([getTags(), getStats()])
    tags.value = tagsData.tags || []
    nsCounts.value = statsData.namespaces || {}
  }
  cacheVersionKey = next
}

function applyCardsData(cardsData) {
  namespaceCards.value = cardsData.cards || []
  layerCounts.value = cardsData.by_layer || {}
  // 构建 cardIndex
  const idx = {}
  for (const n of namespaceCards.value) {
    idx[n.id] = n
  }
  cardIndex.value = idx
}

function applyGraphData(graphData) {
  treeRoots.value = asGraphRoots(graphData.nodes || [])
  linkEdges.value = graphData.link_edges || []

  const idx = { ...cardIndex.value }
  for (const n of (graphData.nodes || [])) {
    idx[n.id] = n
  }
  // 跨域 link 的外部卡也加入 cardIndex（停靠区需要标题等信息）
  for (const cl of (graphData.cross_links || [])) {
    if (!idx[cl.external_id]) {
      idx[cl.external_id] = {
        id: cl.external_id,
        title: cl.external_title,
        type: cl.external_type,
        layer: cl.external_layer,
        namespace: cl.external_ns,
      }
    }
  }
  cardIndex.value = idx
  // 跨域 link 用于停靠区
  allLinkEdges.value = [
    ...(graphData.link_edges || []),
    ...(graphData.cross_links || []).map(cl => ({ source: cl.source, target: cl.target })),
  ]
}

function syncSelectionToVisible() {
  if (!workspaceSelectedId.value) return
  const card = namespaceCards.value.find(c => c.id === workspaceSelectedId.value)
  if (!card || (activeLayer.value && card.layer !== activeLayer.value)) {
    workspaceSelectedId.value = ''
    focusData.value = null
    explorer.value?.exitFocus()
  }
}

async function loadNamespaceData(ns = activeNs.value, tagValues = activeTags.value) {
  const requestId = ++dataRequestSeq
  graphRequestSeq++
  await refreshDataVersion()
  if (requestId !== dataRequestSeq) return
  const tagsParam = tagValues.join(',')
  const key = filterKey(ns, tagsParam)
  activeNs.value = ns
  activeTags.value = [...tagValues]
  graphMode.value = 'summary'
  treeRoots.value = []
  linkEdges.value = []
  allLinkEdges.value = []
  if (!cardsCache.has(key)) {
    namespaceCards.value = []
    layerCounts.value = {}
    cardIndex.value = {}
  }

  const cardsData = cardsCache.get(key) || await getCardsByNs(ns, tagsParam || undefined)
  if (requestId !== dataRequestSeq) return
  cardsCache.set(key, cardsData)

  applyCardsData(cardsData)
  syncSelectionToVisible()
  const nextGraphMode = cardsData.count > GRAPH_SUMMARY_THRESHOLD ? 'summary' : 'all'
  graphMode.value = nextGraphMode
  await loadGraphData(nextGraphMode, requestId)
}

async function loadGraphData(view = graphMode.value, namespaceRequestId = dataRequestSeq) {
  const requestId = ++graphRequestSeq
  await refreshDataVersion()
  if (namespaceRequestId !== dataRequestSeq || requestId !== graphRequestSeq) return
  const tagsParam = activeTagParam.value
  const layerParam = view === 'summary' ? activeLayer.value : ''
  const includeParam = view === 'summary' ? graphIncludeParam() : ''
  const key = `${filterKey(activeNs.value, tagsParam)}|${view}|${layerParam}|${includeParam}`
  const graphData = graphCache.get(key) || await getGraphByNs(
    activeNs.value,
    tagsParam || undefined,
    view,
    layerParam || undefined,
    includeParam || undefined,
    view === 'summary' ? GRAPH_SUMMARY_NODE_LIMIT : 0,
  )
  if (namespaceRequestId !== dataRequestSeq || requestId !== graphRequestSeq) return
  graphCache.set(key, graphData)
  applyGraphData(graphData)
  syncSelectionToVisible()
}

function setGraphMode(mode) {
  if (graphMode.value === mode) return
  graphMode.value = mode
  focusData.value = null
  explorer.value?.exitFocus()
  loadGraphData(mode)
}

async function loadStats() {
  const s = await getStats()
  nsCounts.value = s.namespaces || {}
}

async function loadTags() {
  const data = await getTags()
  tags.value = data.tags || []
}

async function loadFocus(cardId) {
  const data = await getGraphCluster(cardId, 2)
  const center = data.center || (data.nodes && data.nodes[0])
  if (!center) return
  const neighbors = (data.nodes || []).filter(n => n.id !== cardId)
  focusData.value = {
    center,
    neighbors,
    hierarchyEdges: data.hierarchy_edges || [],
    linkEdges: data.link_edges || [],
  }
}

// 事件处理
function onPickNs(ns) {
  if (activeNs.value === ns) return
  graphMode.value = 'summary'
  focusData.value = null
  explorer.value?.exitFocus()
  loadNamespaceData(ns, activeTags.value)
}

function toggleLayer(layer) {
  activeLayer.value = activeLayer.value === layer ? '' : layer
  focusData.value = null
  explorer.value?.exitFocus()
  syncSelectionToVisible()
  if (isLargeNamespace.value) {
    graphMode.value = 'summary'
    loadGraphData('summary')
  }
}

function toggleTag(tag) {
  const set = new Set(activeTags.value)
  if (set.has(tag)) set.delete(tag)
  else set.add(tag)
  graphMode.value = 'summary'
  focusData.value = null
  explorer.value?.exitFocus()
  loadNamespaceData(activeNs.value, [...set])
}

function onSelectCard(id) {
  workspaceSelectedId.value = id
  detailSelectedId.value = id
  pushHistory(id)
  if (isLargeNamespace.value && graphMode.value === 'summary' && !graphHasCard(id)) {
    loadGraphData('summary')
  }
}

function onPickCard(id) {
  // 检查是否需要切换 namespace
  const ns = id.includes(':') ? id.split(':')[0] : ''
  if (ns && ns !== activeNs.value) {
    graphMode.value = 'summary'
    loadNamespaceData(ns, activeTags.value)
  }
  workspaceSelectedId.value = id
  detailSelectedId.value = id
  pushHistory(id)
  if (isLargeNamespace.value && graphMode.value === 'summary' && !graphHasCard(id)) {
    loadGraphData('summary')
  }
}

function onDetailPickCard(id) {
  detailSelectedId.value = id
  pushHistory(id)
}

async function onFocusCard(id) {
  workspaceSelectedId.value = id
  detailSelectedId.value = id
  pushHistory(id)
  await loadFocus(id)
  explorer.value?.enterFocus()
}

function onNavigate(cardId) {
  const ns = cardId.includes(':') ? cardId.split(':')[0] : ''
  if (ns && ns !== activeNs.value) {
    graphMode.value = 'summary'
    loadNamespaceData(ns, activeTags.value)
  }
  workspaceSelectedId.value = cardId
  detailSelectedId.value = cardId
  pushHistory(cardId)
  focusData.value = null
}

function goBack() {
  if (historyIndex.value <= 0) return
  historyIndex.value--
  detailSelectedId.value = history.value[historyIndex.value]
}

function goForward() {
  if (historyIndex.value >= history.value.length - 1) return
  historyIndex.value++
  detailSelectedId.value = history.value[historyIndex.value]
}

function onPickHistory(idx) {
  if (idx === historyIndex.value) return
  historyIndex.value = idx
  detailSelectedId.value = history.value[idx]
}

function moveSidebarSelection(delta) {
  const cards = sidebarCards.value || []
  if (!cards.length) return
  let idx = cards.findIndex(card => card.id === workspaceSelectedId.value)
  if (idx < 0) idx = delta > 0 ? -1 : 0
  const nextIdx = Math.min(cards.length - 1, Math.max(0, idx + delta))
  const next = cards[nextIdx]
  if (!next || next.id === workspaceSelectedId.value) return
  workspaceSelectedId.value = next.id
  detailSelectedId.value = next.id
  pushHistory(next.id)
}

async function runSearch() {
  if (!q.value || q.value.trim().length < 2) return
  searchOpen.value = true
  try {
    const data = await apiSearch(q.value.trim(), 30, activeTagParam.value)
    searchResults.value = data.results
    searched.value = true
  } catch (e) {
    searchResults.value = []
    searched.value = true
  }
}

// 输入时自动搜索（debounce 300ms）
let searchTimer = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!q.value || q.value.trim().length < 2) {
    searchResults.value = []
    searched.value = false
    return
  }
  searchTimer = setTimeout(() => runSearch(), 300)
}

function onSearchFocus() {
  if (q.value && q.value.trim().length >= 2 && searchResults.value.length) {
    searchOpen.value = true
  }
}

function closeSearch() {
  searchOpen.value = false
}

function pickSearch(id) {
  searchOpen.value = false
  q.value = ''
  searchResults.value = []
  searched.value = false
  onPickCard(id)
}

function onKeyDown(e) {
  const target = e.target
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
  if (!(e.metaKey || e.ctrlKey) && e.key === 'ArrowUp') {
    e.preventDefault()
    moveSidebarSelection(-1)
    return
  }
  if (!(e.metaKey || e.ctrlKey) && e.key === 'ArrowDown') {
    e.preventDefault()
    moveSidebarSelection(1)
    return
  }
  if (!(e.metaKey || e.ctrlKey)) return
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    goBack()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    goForward()
  }
}

function startResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = rightWidth.value
  document.body.classList.add('resizing-panel')

  const onMove = (event) => {
    const delta = startX - event.clientX
    const next = Math.min(MAX_RIGHT_WIDTH, Math.max(MIN_RIGHT_WIDTH, startWidth + delta))
    rightWidth.value = next
  }
  const onUp = () => {
    document.body.classList.remove('resizing-panel')
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

onMounted(async () => {
  await Promise.all([loadNamespaceData(), loadStats(), loadTags()])
  window.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  document.body.classList.remove('resizing-panel')
})
</script>

<style>
:root {
  --primary: #2563eb;
  --bg: #f5f6f7;
  --surface: #ffffff;
  --border: #e5e7eb;
  --text: #111827;
  --text-2: #6b7280;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.06);
  --radius: 8px;
}
* { box-sizing: border-box; }
html, body, #app { margin: 0; padding: 0; height: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
}
.app { display: flex; flex-direction: column; height: 100vh; }

.top {
  display: flex; align-items: center; gap: 14px;
  padding: 0 16px; height: 52px;
  background: var(--surface); border-bottom: 1px solid var(--border);
}
.brand { font-weight: 700; font-size: 15px; }

.search { position: relative; display: flex; gap: 4px; flex: 0 0 280px; }
.search input {
  flex: 1; padding: 6px 10px; border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px;
}
.search-btn {
  padding: 6px 12px; border: 1px solid var(--border); background: var(--surface);
  border-radius: 6px; cursor: pointer; font-size: 13px;
}
.search-panel {
  position: absolute; top: 38px; left: 0; right: 0;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow-md);
  max-height: 320px; overflow: auto; z-index: 50;
}
.search-item {
  padding: 8px 10px; cursor: pointer; display: flex; align-items: center; gap: 6px;
  font-size: 13px; border-bottom: 1px solid var(--bg);
}
.search-item:hover { background: var(--bg); }
.search-layer {
  display: inline-block; min-width: 32px; padding: 1px 6px;
  border-radius: 4px; color: #fff; font-size: 11px; text-align: center;
}
.search-type { color: var(--text-2); }
.search-id { margin-left: auto; color: var(--text-2); font-family: monospace; font-size: 11px; }
.search-empty { padding: 12px; color: var(--text-2); font-size: 13px; text-align: center; }

.stats { margin-left: auto; display: flex; gap: 6px; align-items: center; }
.graph-mode {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding-left: 8px;
  border-left: 1px solid var(--border);
}
.mode-btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-2);
  border-radius: 6px;
  padding: 4px 9px;
  font-size: 12px;
  cursor: pointer;
}
.mode-btn:hover {
  background: var(--bg);
  color: var(--text);
}
.mode-btn.active {
  border-color: var(--primary);
  background: #eff6ff;
  color: var(--primary);
  font-weight: 600;
}
.mode-count {
  color: var(--text-2);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  margin-left: 3px;
}
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 12px; background: var(--bg);
  font-size: 12px; color: var(--text-2);
  border: 1px solid transparent;
  cursor: pointer;
  font: inherit;
  line-height: 1.4;
  transition: background 0.12s, border-color 0.12s, color 0.12s, box-shadow 0.12s;
}
.chip b { color: var(--text); font-weight: 600; }
.chip-dot { width: 8px; height: 8px; border-radius: 50%; }
.chip.zero { opacity: 0.4; }
.chip:hover {
  background: #eef2ff;
  border-color: #c7d2fe;
  color: var(--text);
}
.chip.active {
  background: #eff6ff;
  border-color: var(--primary);
  color: var(--primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.08);
  opacity: 1;
}
.chip.active b { color: var(--primary); }

.body { flex: 1; display: flex; min-height: 0; }
.left {
  width: 200px; flex-shrink: 0; background: var(--surface);
  border-right: 1px solid var(--border);
  min-height: 0;
}
.center { flex: 1; min-width: 0; position: relative; }
.panel-resizer {
  width: 6px;
  flex: 0 0 6px;
  cursor: col-resize;
  background: var(--surface);
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  transition: background 0.12s;
}
.panel-resizer:hover {
  background: #dbeafe;
}
.resizing-panel {
  cursor: col-resize;
  user-select: none;
}
.right {
  flex-shrink: 0; background: var(--surface);
  overflow: auto; min-height: 0;
}
</style>
