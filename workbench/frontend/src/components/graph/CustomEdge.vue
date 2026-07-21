<template>
  <BaseEdge :path="path" :style="edgeStyle" :marker-end="markerEnd" />
</template>

<script setup>
import { computed } from 'vue'
import { BaseEdge } from '@vue-flow/core'

const props = defineProps({
  sourceX: { type: Number, required: true },
  sourceY: { type: Number, required: true },
  targetX: { type: Number, required: true },
  targetY: { type: Number, required: true },
  sourcePosition: { type: String, required: true },
  targetPosition: { type: String, required: true },
  data: { type: Object, default: () => ({}) },
  selected: { type: Boolean, default: false },
})

// 直接用直线连接（source/target 坐标已经是最近 handle 的位置）
// 加一点轻微弯曲让多条线不完全重叠
const path = computed(() => {
  const sx = props.sourceX
  const sy = props.sourceY
  const tx = props.targetX
  const ty = props.targetY
  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy)

  if (dist < 50) {
    // 非常近的直接直线
    return `M ${sx} ${sy} L ${tx} ${ty}`
  }

  // 轻微贝塞尔弯曲，弯曲程度和距离成正比但有上限
  const curvature = Math.min(dist * 0.15, 40)
  // 控制点偏移：垂直于连线方向
  const nx = -dy / dist * curvature
  const ny = dx / dist * curvature
  const cx = (sx + tx) / 2 + nx * 0.3
  const cy = (sy + ty) / 2 + ny * 0.3

  return `M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`
})

// state 来自 GraphExplorer 的 decorateEdges：
//   normal — 默认；active — 悬停/选中卡的关联边；
//   dim — 悬停别人时的无关边；faint — 聚焦模式下邻居↔邻居的背景边
const edgeStyle = computed(() => {
  const state = props.data?.state || (props.selected ? 'active' : 'normal')
  if (props.data?.kind === 'hierarchy') {
    const base = {
      stroke: 'rgba(100, 116, 139, 0.55)',
      strokeWidth: 1.2,
      strokeDasharray: '4 3',
    }
    if (state === 'active') return { ...base, stroke: '#7c3aed', strokeWidth: 2.2, strokeDasharray: 'none' }
    if (state === 'dim') return { ...base, opacity: 0.1 }
    if (state === 'faint') return { ...base, opacity: 0.15 }
    return base
  }
  const base = {
    stroke: 'rgba(37, 99, 235, 0.5)',
    strokeWidth: 1.5,
  }
  if (state === 'active') return { ...base, stroke: '#1d4ed8', strokeWidth: 2.5 }
  if (state === 'dim') return { ...base, opacity: 0.08 }
  if (state === 'faint') return { ...base, opacity: 0.12 }
  return base
})

// 箭头按 kind + 状态选 marker（marker 颜色固定在 defs 里，两套色）
const markerEnd = computed(() => {
  const state = props.data?.state || 'normal'
  if (state === 'dim' || state === 'faint') return ''
  if (props.data?.kind === 'hierarchy') {
    return state === 'active' ? 'url(#hier-arrow-active)' : 'url(#hier-arrow)'
  }
  return state === 'active' ? 'url(#link-arrow-active)' : 'url(#link-arrow)'
})
</script>
