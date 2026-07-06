<template>
  <div class="canvas-root">
    <!-- 视图 A: 域级 tile -->
    <section v-if="viewMode === 'ns_overview'" class="view view-domains">
      <header class="view-head">
        <div class="view-title">知识地图</div>
        <div class="view-sub">点一个领域进入主干视图</div>
      </header>
      <div class="domain-grid">
        <button
          v-for="d in domainTiles"
          :key="d.name"
          class="domain-tile"
          :style="{ '--tile-color': d.color }"
          :class="{ active: d.name === activeNs }"
          @click="$emit('pick', d.name)"
          @dblclick="$emit('pick', d.name)"
        >
          <div class="dt-name">{{ d.name }}</div>
          <div class="dt-count">{{ d.count }} 张</div>
          <div class="dt-hint">{{ d.hint }}</div>
        </button>
      </div>
    </section>

    <!-- 视图 B: 卡片网格 -->
    <section v-else-if="viewMode === 'overview'" class="view view-grid">
      <header class="view-head">
        <div class="view-title">
          {{ activeNs || '全部' }} 卡片网格
          <span class="view-meta">{{ cards.length }} 张 · 按 ID 分组</span>
        </div>
        <div class="view-sub">单击=选中 · 双击=聚焦关联网络</div>
      </header>
      <div class="grid-scroll">
        <div
          v-for="grp in groupedCards"
          :key="grp.key"
          class="card-group"
        >
          <div class="group-head">
            <span class="group-key">{{ grp.label }}</span>
            <span class="group-count">{{ grp.cards.length }}</span>
          </div>
          <div class="card-grid">
            <button
              v-for="c in grp.cards"
              :key="c.id"
              class="card-tile"
              :class="[
                `layer-${(c.layer || 'L2').toLowerCase()}`,
                { selected: c.id === selectedId }
              ]"
              :title="c.title"
              @click="$emit('pick', c.id)"
              @dblclick="$emit('focus', c.id)"
            >
              <div class="ct-head">
                <span class="ct-type" :style="{ background: typeColor[c.type] || '#999' }">{{ c.type }}</span>
                <span class="ct-id">{{ shortId(c.id) }}</span>
              </div>
              <div class="ct-title">{{ c.title }}</div>
              <div class="ct-foot">
                <span v-if="c.use_count" class="ct-stat">读 {{ c.use_count }}</span>
                <span v-if="c.search_count" class="ct-stat">搜 {{ c.search_count }}</span>
              </div>
            </button>
          </div>
        </div>
        <div v-if="!groupedCards.length" class="empty">本域无卡片</div>
      </div>
    </section>

    <!-- 视图 C: 关联网络 -->
    <section v-else class="view view-focus">
      <header class="view-head focus-head">
        <div class="view-title">聚焦视图</div>
        <button class="focus-exit" @click="$emit('reset-view')">← 返回网格</button>
      </header>
      <div class="focus-canvas">
        <VNetworkGraph
          ref="graph"
          class="vng-canvas"
          :nodes="focusNodes"
          :edges="focusEdges"
          :layouts="focusLayouts"
          :configs="focusConfigs"
          :event-handlers="handlers"
        >
          <template #override-node-label="{ nodeId, scale, x, y }">
            <g :transform="`translate(${x}, ${y})`">
              <text
                text-anchor="middle"
                dominant-baseline="hanging"
                :font-size="focusLabelSize(nodeId, scale)"
                :font-weight="nodeId === focusedId ? 700 : 500"
                :fill="nodeId === selectedId ? '#2563eb' : '#111827'"
                stroke="#ffffff"
                stroke-width="2"
                stroke-opacity="0.9"
                paint-order="stroke"
              >
                <tspan
                  v-for="(line, idx) in wrapTitle(nodeMap[nodeId]?.title, 12)"
                  :key="idx"
                  x="0"
                  :dy="idx === 0 ? '0.3em' : '1.15em'"
                >{{ line }}</tspan>
              </text>
            </g>
          </template>
        </VNetworkGraph>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { VNetworkGraph } from 'v-network-graph'

const props = defineProps({
  // 图谱数据（视图 B/C 用）
  cards: { type: Array, default: () => [] },
  hierarchyEdges: { type: Array, default: () => [] },
  linkEdges: { type: Array, default: () => [] },
  // 当前状态
  viewMode: { type: String, default: 'ns_overview' }, // ns_overview / overview / focused
  activeNs: { type: String, default: '' },
  selectedId: { type: String, default: '' },
  focusedId: { type: String, default: '' },
  // 域级信息（视图 A 用）
  nsCounts: { type: Object, default: () => ({}) },
})
defineEmits(['pick', 'focus', 'reset-view'])

const DOMAIN_META = {
  fin:  { color: '#0ea5e9', hint: '金融·交易·经济' },
  fit:  { color: '#22c55e', hint: '健身·身体' },
  gen:  { color: '#f59e0b', hint: '元层·跨域模式' },
  llm:  { color: '#8b5cf6', hint: 'AI·Agent·Prompt' },
  phil: { color: '#ec4899', hint: '哲学·认知·思维' },
  med:  { color: '#ef4444', hint: '医学' },
  law:  { color: '#6366f1', hint: '法律' },
  sw:   { color: '#14b8a6', hint: '软件·工程' },
  prod: { color: '#84cc16', hint: '产品·业务' },
}

const typeColor = {
  主题: '#ef4444',
  概念: '#3b82f6',
  结构: '#8b5cf6',
  机制: '#f97316',
  案例: '#10b981',
  判断: '#eab308',
  反思: '#06b6d4',
  模式: '#ec4899',
}

const domainTiles = computed(() => {
  const counts = props.nsCounts || {}
  const names = Object.keys(counts).sort((a, b) => counts[b] - counts[a])
  return names.map(name => ({
    name,
    count: counts[name],
    color: (DOMAIN_META[name] || {}).color || '#64748b',
    hint: (DOMAIN_META[name] || {}).hint || '',
  }))
})

// 视图 B：按 ID 前缀分组
function prefixOf(id) {
  // gen:1a → "1";  llm:harness:01a → "harness";  fin:3a1 → "3"
  const parts = id.split(':')
  const last = parts[parts.length - 1]
  // 取前缀（数字部分第一位 或 字母段）
  const m = last.match(/^(\d+|[a-zA-Z]+)/)
  if (!m) return '其他'
  // 数字前缀取第一位
  if (/^\d/.test(m[1])) return m[1][0] + '*'
  return m[1]
}

function groupLabel(ns, key) {
  // gen: "1*", "2*"  → "1 系列"
  // 其他: book 名 → "harness"
  if (key.endsWith('*')) return `${ns} · ${key} 系列`
  if (ns && parts(ns, key)) return `${ns} · ${key}`  // 书目
  return key
}

function parts(ns, key) {
  return ns !== ''
}

function shortId(id) {
  const seg = id.split(':')
  return seg[seg.length - 1]
}

// 按 ns + 卢曼 ID 前缀分组
const groupedCards = computed(() => {
  if (!props.cards.length) return []
  const buckets = new Map()
  for (const c of props.cards) {
    const key = prefixOf(c.id)
    if (!buckets.has(key)) buckets.set(key, [])
    buckets.get(key).push(c)
  }
  // 排序：数字前缀按数字，其他按字母
  const sortedKeys = [...buckets.keys()].sort((a, b) => {
    const ai = a.match(/^(\d)\*/)?.[1]
    const bi = b.match(/^(\d)\*/)?.[1]
    if (ai && bi) return Number(ai) - Number(bi)
    if (ai) return -1
    if (bi) return 1
    return a.localeCompare(b)
  })
  return sortedKeys.map(k => ({
    key: k,
    label: groupLabel(props.activeNs, k),
    cards: buckets.get(k).sort((a, b) => a.id.localeCompare(b.id)),
  }))
})

// 视图 C：focus 网络
const nodeMap = computed(() => {
  const m = {}
  for (const n of props.cards) m[n.id] = n
  return m
})

const focusNodes = computed(() => {
  const m = {}
  for (const n of props.cards) {
    m[n.id] = {
      name: n.title,
      type: n.type,
      layer: n.layer,
      isCenter: n.id === props.focusedId,
    }
  }
  return m
})

const focusEdges = computed(() => {
  const m = {}
  const add = (e, kind) => {
    const k = `${e.source}__${e.target}__${kind}`
    m[k] = { source: e.source, target: e.target, kind }
  }
  for (const e of props.hierarchyEdges) add(e, 'hierarchy')
  for (const e of props.linkEdges) add(e, 'link')
  return m
})

const focusLayouts = computed(() => {
  // 同心圆布局：中心节点在原点，其他按 layer 排成环
  const nodes = props.cards
  if (!nodes.length) return { nodes: {} }
  const center = props.focusedId
  const layerRing = { L1: 1, L2_light: 1, L2: 1, L3: 2, L4: 3 }
  const ringRadii = [0, 140, 240, 340, 440]
  const ringBuckets = {}
  // 中心节点的直接邻居（一跳）排第一环
  const oneHop = new Set()
  for (const e of props.hierarchyEdges.concat(props.linkEdges)) {
    if (e.source === center) oneHop.add(e.target)
    if (e.target === center) oneHop.add(e.source)
  }
  for (const n of nodes) {
    if (n.id === center) {
      ringBuckets[0] = ringBuckets[0] || []
      ringBuckets[0].push(n.id)
    } else if (oneHop.has(n.id)) {
      ringBuckets[1] = ringBuckets[1] || []
      ringBuckets[1].push(n.id)
    } else {
      const r = layerRing[n.layer] || 3
      ringBuckets[r] = ringBuckets[r] || []
      ringBuckets[r].push(n.id)
    }
  }
  const out = {}
  for (const [ringStr, ids] of Object.entries(ringBuckets)) {
    const ring = Number(ringStr)
    const r = ringRadii[ring] || 440
    if (ring === 0) {
      out[ids[0]] = { x: 0, y: 0 }
      continue
    }
    const n = ids.length
    ids.forEach((id, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2
      out[id] = { x: Math.cos(a) * r, y: Math.sin(a) * r }
    })
  }
  return { nodes: out }
})

const focusConfigs = {
  view: {
    autoPanOnLoad: true,
    scaling: { nodes: 1, min: 0.2, max: 3 },
    grid: { visible: false },
  },
  node: {
    normal: { type: 'circle', radius: (n) => n?.isCenter ? 24 : 10, color: (n) => n?.isCenter ? '#f59e0b' : '#6366f1' },
    hover: { color: '#2563eb' },
    selected: { color: '#2563eb', strokeWidth: 3 },
    label: { visible: false },
  },
  edge: {
    normal: {
      color: (e) => e?.kind === 'hierarchy' ? '#c7d2fe' : '#fde68a',
      width: (e) => e?.kind === 'hierarchy' ? 1 : 1.5,
      gapWithNode: 4,
    },
    hover: { width: 2.5 },
  },
}

function focusLabelSize(nodeId, scale) {
  const n = nodeMap.value[nodeId]
  if (!n) return 10
  if (nodeId === props.focusedId) return 14 / scale
  return 11 / scale
}

function wrapTitle(t, max = 12) {
  if (!t) return ['(无标题)']
  if (t.length <= max) return [t]
  const lines = []
  for (let i = 0; i < t.length; i += max) lines.push(t.slice(i, i + max))
  return lines.slice(0, 3)
}

const handlers = {
  'node:click': ({ nodeId }) => {
    // 防止 ns 边界节点等被点
    if (!nodeId || !nodeMap.value[nodeId]) return
    // 单击：仅选中（不重排）
  },
  'node:dblclick': ({ nodeId }) => {
    if (!nodeId || !nodeMap.value[nodeId]) return
    // 双击：切换中心
  },
}
</script>

<style scoped>
.canvas-root {
  height: 100%;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.view-head {
  padding: 12px 20px 8px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  flex-shrink: 0;
}
.view-title {
  font-size: 14px;
  font-weight: 700;
}
.view-meta {
  font-size: 11px;
  color: var(--text-2);
  margin-left: 8px;
  font-weight: 400;
}
.view-sub {
  font-size: 11px;
  color: var(--text-2);
}

/* 视图 A: 域级 tile */
.domain-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  padding: 24px;
  align-content: start;
  overflow: auto;
}
.domain-tile {
  --tile-color: #64748b;
  position: relative;
  border: 2px solid transparent;
  background: linear-gradient(135deg, var(--tile-color) 8%, color-mix(in srgb, var(--tile-color) 25%, white) 100%);
  color: #fff;
  border-radius: 14px;
  padding: 28px 22px;
  min-height: 130px;
  cursor: pointer;
  text-align: left;
  transition: transform .15s, box-shadow .15s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.domain-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0,0,0,0.12);
}
.domain-tile.active {
  border-color: #fff;
  outline: 3px solid var(--tile-color);
  outline-offset: 1px;
}
.dt-name {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0.02em;
}
.dt-count {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.95;
  margin-top: 4px;
}
.dt-hint {
  font-size: 11px;
  opacity: 0.85;
  margin-top: 14px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* 视图 B: 卡片网格 */
.grid-scroll {
  flex: 1;
  overflow: auto;
  padding: 14px 20px 40px;
}
.card-group {
  margin-bottom: 28px;
}
.group-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 14px;
}
.group-key {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}
.group-count {
  font-size: 11px;
  color: var(--text-2);
  background: var(--bg);
  padding: 1px 8px;
  border-radius: 10px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.card-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color .15s, box-shadow .15s;
  border-left-width: 4px;
  min-height: 92px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.card-tile:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px rgba(37,99,235,0.1);
}
.card-tile.selected {
  border-color: var(--primary);
  background: #eff6ff;
}
.card-tile.layer-l4 { border-left-color: #f59e0b; }
.card-tile.layer-l3 { border-left-color: #10b981; }
.card-tile.layer-l2 { border-left-color: #6366f1; }
.card-tile.layer-l2_light { border-left-color: #a3bffa; }
.card-tile.layer-l1_only { border-left-color: #94a3b8; }
.ct-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.ct-type {
  font-size: 10px;
  color: #fff;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.ct-id {
  font-size: 10px;
  color: var(--text-2);
  font-family: monospace;
}
.ct-title {
  font-size: 12px;
  line-height: 1.35;
  color: var(--text);
  flex: 1;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.ct-foot {
  display: flex;
  gap: 6px;
  font-size: 10px;
  color: var(--text-2);
}
.ct-stat {
  background: var(--bg);
  padding: 1px 5px;
  border-radius: 3px;
}

.empty {
  padding: 40px;
  color: var(--text-2);
  text-align: center;
  font-size: 13px;
}

/* 视图 C: 聚焦网络 */
.view-focus .focus-head { background: #fef3c7; }
.focus-exit {
  border: none;
  background: var(--primary);
  color: #fff;
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.focus-exit:hover { opacity: 0.9; }
.focus-canvas {
  flex: 1;
  min-height: 0;
  position: relative;
}
.vng-canvas {
  width: 100%;
  height: 100%;
}
</style>
