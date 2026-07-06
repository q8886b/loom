<template>
  <div
    class="card-node"
    :class="[
      `layer-${(data.layer || 'L2').toLowerCase().replace('_', '-')}`,
      `type-${data.cardType}`,
      { selected: data.isSelected, expanded: data.isExpanded, 'has-children': data.hasChildren },
    ]"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <div class="node-body">
      <span class="type-dot" :style="{ background: typeColor[data.cardType] || '#94a3b8' }"></span>
      <div class="node-content">
        <div class="node-title">{{ data.title }}</div>
      </div>
      <span class="layer-bar" :style="{ background: layerColor[data.layer] || '#94a3b8' }"></span>
    </div>

    <!-- 聚合 badge：折叠时显示子节点数 -->
    <div v-if="data.hasChildren && !data.isExpanded" class="badge">
      <span class="badge-count">{{ data.childCount }}</span>
    </div>

    <!-- 展开/折叠 chevron：hover 时显示 -->
    <button
      v-if="data.hasChildren && !isCompact"
      v-show="hovered || data.isExpanded"
      class="chevron"
      :class="{ open: data.isExpanded }"
      @click.stop="onToggle"
    >
      <svg width="12" height="12" viewBox="0 0 12 12">
        <path d="M4 2 L8 6 L4 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>

    <!-- 连接点：四个方向，让 Vue Flow 自动选最近的 -->
    <Handle id="left" type="source" :position="Position.Left" class="handle" />
    <Handle id="right" type="source" :position="Position.Right" class="handle" />
    <Handle id="top" type="source" :position="Position.Top" class="handle" />
    <Handle id="bottom" type="source" :position="Position.Bottom" class="handle" />
    <Handle id="target-left" type="target" :position="Position.Left" class="handle" />
    <Handle id="target-right" type="target" :position="Position.Right" class="handle" />
    <Handle id="target-top" type="target" :position="Position.Top" class="handle" />
    <Handle id="target-bottom" type="target" :position="Position.Bottom" class="handle" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
})

function onToggle() {
  if (props.data.onToggleExpand) {
    props.data.onToggleExpand(props.id)
  }
}

const hovered = ref(false)

const typeColor = {
  概念: '#3b82f6',
  结构: '#8b5cf6',
  机制: '#14b8a6',
  案例: '#f59e0b',
  判断: '#ec4899',
  反思: '#64748b',
  模式: '#0d9488',
  主题: '#2563eb',
}

const layerColor = {
  L1: '#94a3b8',
  L2_light: '#a3bffa',
  L2: '#6366f1',
  L3: '#10b981',
  L4: '#f59e0b',
}
</script>

<style scoped>
.card-node {
  position: relative;
  width: 200px;
  min-height: 48px;
  border-radius: 8px;
  background: #ffffff;
  border: 1.5px solid #e5e7eb;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;
  user-select: none;
}

.card-node:hover {
  border-color: #2563eb;
  box-shadow: 0 2px 12px rgba(37, 99, 235, 0.12);
}

.card-node.selected {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
  transform: scale(1.02);
}

/* Layer 描边色 */
.card-node.layer-l4 { border-left: 3px solid #f59e0b; }
.card-node.layer-l3 { border-left: 3px solid #10b981; }
.card-node.layer-l2 { border-left: 3px solid #6366f1; }
.card-node.layer-l2-light { border-left: 3px solid #a3bffa; }
.card-node.layer-l1-only { border-left: 3px solid #94a3b8; }

.node-body {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
}

.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}

.node-content {
  flex: 1;
  min-width: 0;
}

.node-title {
  font-size: 12px;
  line-height: 1.4;
  color: #111827;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.layer-bar {
  width: 3px;
  min-height: 24px;
  border-radius: 2px;
  flex-shrink: 0;
  align-self: stretch;
  opacity: 0.6;
}

/* 聚合 badge */
.badge {
  position: absolute;
  bottom: -8px;
  right: 12px;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 1px 6px;
  font-size: 10px;
  color: #6b7280;
  line-height: 1.4;
}

.badge-count::before {
  content: '↓';
  margin-right: 2px;
  opacity: 0.6;
}

/* Chevron 按钮 */
.chevron {
  position: absolute;
  right: -10px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid #e5e7eb;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #6b7280;
  transition: background 0.15s, color 0.15s, transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  z-index: 2;
}

.chevron:hover {
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
}

.chevron.open svg {
  transform: rotate(90deg);
}

/* Handle 连接点（隐藏视觉，保留功能） */
.handle {
  width: 6px;
  height: 6px;
  background: transparent;
  border: none;
}

.handle-left {
  left: -3px;
}

.handle-right {
  right: -3px;
}
</style>
