<template>
  <div
    class="card-node focus-center"
  >
    <div class="glow"></div>
    <div class="node-body">
      <span class="type-tag" :style="{ background: typeColor[data.cardType] || '#94a3b8' }">{{ data.cardType }}</span>
      <span class="layer-tag" :style="{ background: layerColor[data.layer] || '#94a3b8' }">{{ data.layer }}</span>
    </div>
    <div class="node-title">{{ data.title }}</div>
    <div class="node-ns">{{ data.namespace }}</div>

    <Handle type="target" :position="Position.Left" class="handle" />
    <Handle type="source" :position="Position.Right" class="handle" />
    <Handle type="source" :position="Position.Top" id="top" class="handle" />
    <Handle type="source" :position="Position.Bottom" id="bottom" class="handle" />
  </div>
</template>

<script setup>
import { Handle, Position } from '@vue-flow/core'

defineProps({
  data: { type: Object, required: true },
})

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
.focus-center {
  position: relative;
  width: 260px;
  min-height: 80px;
  border-radius: 12px;
  background: #ffffff;
  border: 2px solid #f59e0b;
  padding: 14px 16px;
  cursor: default;
  box-shadow: 0 4px 20px rgba(245, 158, 11, 0.2);
}

.glow {
  position: absolute;
  inset: -6px;
  border-radius: 16px;
  background: radial-gradient(ellipse at center, rgba(245, 158, 11, 0.1) 0%, transparent 70%);
  pointer-events: none;
  z-index: -1;
}

.node-body {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.type-tag, .layer-tag {
  font-size: 10px;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.node-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  color: #111827;
  margin-bottom: 4px;
}

.node-ns {
  font-size: 11px;
  color: #6b7280;
  font-family: monospace;
}

.handle {
  width: 6px;
  height: 6px;
  background: transparent;
  border: none;
}
</style>
