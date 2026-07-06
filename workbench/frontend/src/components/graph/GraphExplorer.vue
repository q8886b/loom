<template>
  <div class="graph-explorer">
    <!-- 主画布 -->
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      :node-types="nodeTypes"
      :edge-types="edgeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.85 }"
      :min-zoom="0.2"
      :max-zoom="2.5"
      :fit-view-on-init="true"
      :fit-view-on-init-options="{ padding: 0.15, maxZoom: 1.0 }"
      :nodes-draggable="false"
      :nodes-connectable="false"
      :edges-updatable="false"
      @node-click="onNodeClick"
      @node-double-click="onNodeDblClick"
    >
      <Background />

      <!-- SVG marker for link arrows -->
      <template #connection-line />
      <svg>
        <defs>
          <marker
            id="link-arrow"
            viewBox="0 0 10 10"
            refX="10"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(37, 99, 235, 0.6)" />
          </marker>
        </defs>
      </svg>
    </VueFlow>

    <!-- 停靠区 -->
    <DockPanel
      :groups="dockGroups"
      @navigate="onDockNavigate"
    />

    <!-- 视图信息 -->
    <div class="view-info">
      <span>{{ flowNodes.length }} 节点</span>
      <span class="sep">·</span>
      <span>滚轮缩放 · 单击选卡 · 双击聚焦</span>
    </div>

    <!-- 聚焦模式返回按钮 -->
    <button v-if="mode === 'focus'" class="back-btn" @click="exitFocus">
      ← 返回树视图
    </button>
  </div>
</template>

<script setup>
import { ref, computed, watch, shallowRef, markRaw, nextTick } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

import CardNode from './CardNode.vue'
import CardNodeCenter from './CardNodeCenter.vue'
import CustomEdge from './CustomEdge.vue'
import DockPanel from './DockPanel.vue'
import { layoutTree, layoutLinks, computeDockLinks, layoutFocus } from './TreeLayout.js'

const props = defineProps({
  treeRoots: { type: Array, default: () => [] },
  linkEdges: { type: Array, default: () => [] },
  allLinkEdges: { type: Array, default: () => [] },
  cardIndex: { type: Object, default: () => ({}) },
  selectedId: { type: String, default: '' },
  focusData: { type: Object, default: null },
})

const emit = defineEmits(['select', 'focus', 'navigate', 'toggle-expand'])

const nodeTypes = markRaw({
  card: CardNode,
  'card-focus-center': CardNodeCenter,
})

const edgeTypes = markRaw({
  hierarchy: CustomEdge,
  link: CustomEdge,
})

const mode = ref('tree') // 'tree' | 'focus'
const expanded = ref(new Set())

const vueFlow = useVueFlow()
const { fitView } = vueFlow
let getFlowNodeCount = () => 0

function fitCurrentView(options = {}) {
  nextTick(() => {
    requestAnimationFrame(() => {
      setTimeout(() => {
        const minZoom = getFlowNodeCount() <= 80 ? 0.4 : 0.2
        fitView({
          padding: 0.12,
          minZoom,
          maxZoom: 1.0,
          duration: 250,
          ...options,
        })
      }, 0)
    })
  })
}

// 初始展开：只有少量 roots（<=20）才默认展开，和多列布局阈值一致
watch(() => props.treeRoots, (roots) => {
  if (!roots.length) return
  const initial = new Set()
  if (roots.length <= 20) {
    for (const root of roots) {
      initial.add(root.id)
    }
  }
  expanded.value = initial
  // namespace 切换后重新 fitView
  fitCurrentView({ padding: 0.1, maxZoom: 1.0, duration: 300 })
}, { immediate: true })

// 展开/折叠回调——通过 node.data 传递给 CardNode
function handleToggleExpand(nodeId) {
  toggleExpand(nodeId)
}

// 缓存布局结果，避免 selectedId 变化时重新计算（力导向带随机性会跳变）
let cachedLayoutKey = ''
let cachedLayout = { nodes: [], edges: [] }

function collectTreeIds(nodes, ids = []) {
  for (const node of nodes || []) {
    ids.push(node.id)
    collectTreeIds(node.children || [], ids)
  }
  return ids
}

function treeLayoutKey(roots, expanded, linkEdges) {
  const ids = collectTreeIds(roots).join(',')
  const expandedIds = [...expanded].sort().join(',')
  const links = (linkEdges || [])
    .map(e => `${e.source}>${e.target}`)
    .sort()
    .join(',')
  return `${ids}|${expandedIds}|${links}`
}

// 树模式节点和边
const treeResult = computed(() => {
  if (mode.value !== 'tree') return { nodes: [], edges: [] }
  // 布局只依赖 treeRoots + expanded + linkEdges，不依赖 selectedId
  const key = treeLayoutKey(props.treeRoots, expanded.value, props.linkEdges)
  if (key !== cachedLayoutKey) {
    cachedLayoutKey = key
    cachedLayout = layoutTree(props.treeRoots, expanded.value, '', props.linkEdges)
  }
  // 注入 onToggleExpand 和 isSelected（不触发布局重算）
  for (const node of cachedLayout.nodes) {
    node.data.onToggleExpand = handleToggleExpand
    node.data.isSelected = node.id === props.selectedId
  }
  return cachedLayout
})

const treeLinkEdges = computed(() => {
  if (mode.value !== 'tree') return []
  const visibleIds = new Set(treeResult.value.nodes.map(n => n.id))
  return layoutLinks(props.linkEdges, visibleIds)
})

// 聚焦模式节点和边
const focusResult = computed(() => {
  if (mode.value !== 'focus' || !props.focusData) return { nodes: [], edges: [] }
  return layoutFocus(
    props.focusData.center,
    props.focusData.neighbors,
    props.focusData.hierarchyEdges,
    props.focusData.linkEdges,
  )
})

// 合并输出给 VueFlow
const flowNodes = computed(() => {
  return mode.value === 'focus' ? focusResult.value.nodes : treeResult.value.nodes
})

getFlowNodeCount = () => flowNodes.value.length

const flowNodeSignature = computed(() => flowNodes.value.map(node => {
  const x = Math.round(node.position?.x || 0)
  const y = Math.round(node.position?.y || 0)
  return `${node.id}:${x}:${y}`
}).join('|'))

watch(flowNodeSignature, (signature) => {
  if (!signature) return
  fitCurrentView({
    padding: mode.value === 'focus' ? 0.15 : 0.12,
    maxZoom: mode.value === 'focus' ? 1.2 : 1.0,
    duration: 200,
  })
}, { flush: 'post' })

const flowEdges = computed(() => {
  if (mode.value === 'focus') return focusResult.value.edges
  return [...treeResult.value.edges, ...treeLinkEdges.value]
})

// 停靠区数据
const dockGroups = computed(() => {
  if (mode.value !== 'tree') return {}
  const visibleIds = new Set(treeResult.value.nodes.map(n => n.id))
  return computeDockLinks(props.allLinkEdges, visibleIds, props.cardIndex)
})

// 事件处理
function onNodeClick({ node }) {
  emit('select', node.id)
}

function onNodeDblClick({ node }) {
  if (node.type === 'card-focus-center') return
  emit('focus', node.id)
  mode.value = 'focus'
  // 进入聚焦模式后，fitView 居中显示所有节点
  fitCurrentView({ padding: 0.15, maxZoom: 1.2, duration: 300 })
}

function onDockNavigate(cardId) {
  mode.value = 'tree'
  emit('navigate', cardId)
}

function exitFocus() {
  mode.value = 'tree'
  // 返回树视图后 fitView 重新定位
  fitCurrentView({ padding: 0.1, maxZoom: 1.0, duration: 300 })
}

// 暴露给父组件：展开/折叠
function toggleExpand(nodeId) {
  const next = new Set(expanded.value)
  if (next.has(nodeId)) {
    next.delete(nodeId)
  } else {
    next.add(nodeId)
  }
  expanded.value = next
}

// 外部控制进入聚焦模式
function enterFocus() {
  mode.value = 'focus'
  // 聚焦模式加载后 fitView 居中
  fitCurrentView({ padding: 0.15, maxZoom: 1.2, duration: 300 })
}

defineExpose({ toggleExpand, enterFocus, exitFocus })
</script>

<style scoped>
.graph-explorer {
  width: 100%;
  height: 100%;
  position: relative;
  background: #f8fafc;
}

.view-info {
  position: absolute;
  bottom: 16px;
  left: 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 5px 12px;
  font-size: 11px;
  color: #6b7280;
  display: flex;
  gap: 6px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.view-info .sep {
  opacity: 0.4;
}

.back-btn {
  position: absolute;
  top: 16px;
  left: 16px;
  border: none;
  background: #2563eb;
  color: #fff;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
  transition: opacity 0.15s;
  z-index: 20;
}

.back-btn:hover {
  opacity: 0.9;
}
</style>
