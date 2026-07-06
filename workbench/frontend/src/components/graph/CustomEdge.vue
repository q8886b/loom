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

const edgeStyle = computed(() => {
  if (props.data?.kind === 'hierarchy') {
    return {
      stroke: props.selected ? '#64748b' : 'rgba(148, 163, 184, 0.4)',
      strokeWidth: props.selected ? 1.5 : 1,
      strokeDasharray: '4 3',
    }
  }
  return {
    stroke: props.selected ? '#1d4ed8' : 'rgba(37, 99, 235, 0.45)',
    strokeWidth: props.selected ? 2.5 : 1.5,
  }
})

const markerEnd = computed(() => {
  if (props.data?.kind === 'link') return 'url(#link-arrow)'
  return ''
})
</script>
