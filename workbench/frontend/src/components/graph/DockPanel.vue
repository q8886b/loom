<template>
  <div class="dock" v-if="Object.keys(groups).length">
    <div class="dock-title">跨域连接</div>
    <div
      v-for="(group, ns) in groups"
      :key="ns"
      class="dock-group"
      :class="{ open: openNs === ns }"
    >
      <button class="dock-ns" @click="toggleNs(ns)">
        <span class="dock-dot" :style="{ background: nsColor[ns] || '#94a3b8' }"></span>
        <span class="dock-ns-name">{{ ns }}</span>
        <span class="dock-count">{{ group.count }}</span>
        <svg class="dock-chevron" :class="{ open: openNs === ns }" width="10" height="10" viewBox="0 0 10 10">
          <path d="M3 2 L7 5 L3 8" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
        </svg>
      </button>
      <div v-if="openNs === ns" class="dock-cards">
        <button
          v-for="card in group.cards.slice(0, 10)"
          :key="card.id"
          class="dock-card"
          @click="$emit('navigate', card.id)"
        >
          <span class="dock-card-type" :style="{ background: typeColor[card.type] || '#94a3b8' }"></span>
          <span class="dock-card-title">{{ card.title }}</span>
          <span class="dock-card-id">{{ shortId(card.id) }}</span>
        </button>
        <div v-if="group.cards.length > 10" class="dock-more">
          还有 {{ group.cards.length - 10 }} 张…
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  groups: { type: Object, default: () => ({}) },
})

defineEmits(['navigate'])

const openNs = ref('')

function toggleNs(ns) {
  openNs.value = openNs.value === ns ? '' : ns
}

function shortId(id) {
  const parts = id.split(':')
  return parts[parts.length - 1]
}

const nsColor = {
  fin: '#0ea5e9',
  fit: '#22c55e',
  gen: '#f59e0b',
  llm: '#8b5cf6',
  phil: '#ec4899',
  med: '#ef4444',
  law: '#6366f1',
  sw: '#14b8a6',
  prod: '#84cc16',
}

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
</script>

<style scoped>
.dock {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 200px;
  max-height: calc(100% - 32px);
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(8px);
  z-index: 20;
}

.dock-title {
  font-size: 10px;
  font-weight: 700;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding: 0 4px;
}

.dock-group {
  margin-bottom: 4px;
}

.dock-ns {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: #374151;
  transition: background 0.12s;
}

.dock-ns:hover {
  background: #f3f4f6;
}

.dock-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dock-ns-name {
  font-weight: 600;
  flex: 1;
  text-align: left;
}

.dock-count {
  font-size: 10px;
  color: #9ca3af;
  background: #f3f4f6;
  padding: 1px 5px;
  border-radius: 8px;
}

.dock-chevron {
  color: #9ca3af;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.dock-chevron.open {
  transform: rotate(90deg);
}

.dock-cards {
  padding: 4px 0 4px 20px;
}

.dock-card {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 6px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  color: #374151;
  text-align: left;
  transition: background 0.12s;
}

.dock-card:hover {
  background: #eff6ff;
}

.dock-card-type {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dock-card-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dock-card-id {
  font-size: 10px;
  color: #9ca3af;
  font-family: monospace;
  flex-shrink: 0;
}

.dock-more {
  font-size: 10px;
  color: #9ca3af;
  padding: 4px 6px;
}
</style>
