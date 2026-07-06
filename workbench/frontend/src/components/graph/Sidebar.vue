<template>
  <div class="sidebar">
    <div class="sidebar-section">
      <button class="section-toggle" @click="domainsOpen = !domainsOpen">
        <span>域</span>
        <span class="section-count">{{ domains.length }}</span>
        <span class="section-arrow" :class="{ open: domainsOpen }">›</span>
      </button>
      <div v-if="domainsOpen" class="ns-list">
        <button
          v-for="d in domains"
          :key="d.name"
          class="ns-item"
          :class="{ active: d.name === activeNs }"
          @click="$emit('pick-ns', d.name)"
        >
          <span class="ns-dot" :style="{ background: d.color }"></span>
          <span class="ns-name">{{ d.name }}</span>
          <span class="ns-count">{{ d.count }}</span>
        </button>
      </div>
    </div>

    <div class="sidebar-section">
      <button class="section-toggle" @click="tagsOpen = !tagsOpen">
        <span>Tags</span>
        <span class="section-count">{{ tags.length }}</span>
        <span class="section-arrow" :class="{ open: tagsOpen }">›</span>
      </button>
      <div v-if="tagsOpen" class="tag-list">
        <button
          v-for="item in tags"
          :key="item.tag"
          class="tag-item"
          :class="{ active: activeTagSet.has(item.tag) }"
          @click="$emit('toggle-tag', item.tag)"
        >
          <span class="tag-name">{{ item.tag }}</span>
          <span class="tag-count">{{ item.count }}</span>
        </button>
        <div v-if="!tags.length" class="tag-empty">暂无 tag</div>
      </div>
    </div>

    <div class="sidebar-section" v-if="recentCards.length">
      <button class="section-toggle" @click="recentOpen = !recentOpen">
        <span>最近访问</span>
        <span class="section-count">{{ recentCards.length }}</span>
        <span class="section-arrow" :class="{ open: recentOpen }">›</span>
      </button>
      <div v-if="recentOpen" class="recent-list">
        <button
          v-for="card in recentCards"
          :key="card.id"
          class="recent-item"
          :class="{ active: card.id === selectedId }"
          @click="$emit('pick-card', card.id)"
        >
          <span class="recent-type" :style="{ background: typeColor[card.type] || '#94a3b8' }"></span>
          <span class="recent-title">{{ card.title }}</span>
        </button>
      </div>
    </div>

    <div class="sidebar-section">
      <button class="section-toggle" @click="cardsOpen = !cardsOpen">
        <span>卡片列表</span>
        <span class="section-count">{{ cards.length }}</span>
        <span class="section-arrow" :class="{ open: cardsOpen }">›</span>
      </button>
      <div v-if="cardsOpen" ref="cardListEl" class="card-list" @scroll="onCardListScroll">
        <button
          v-for="(card, index) in visibleCards"
          :key="card.id"
          class="card-list-item"
          :class="{ active: card.id === selectedId }"
          @click="$emit('pick-card', card.id)"
        >
          <span class="card-list-index">{{ index + 1 }}</span>
          <span class="card-list-main">
            <span class="card-list-title">{{ card.title }}</span>
            <span class="card-list-id">{{ card.id }} · {{ card.type }}</span>
          </span>
        </button>
        <div v-if="!cards.length" class="card-list-empty">无卡片</div>
        <div v-else class="card-list-more">
          已显示 {{ visibleCards.length }} / {{ cards.length }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  nsCounts: { type: Object, default: () => ({}) },
  tags: { type: Array, default: () => [] },
  activeTags: { type: Array, default: () => [] },
  activeNs: { type: String, default: '' },
  selectedId: { type: String, default: '' },
  recentCards: { type: Array, default: () => [] },
  cards: { type: Array, default: () => [] },
})

defineEmits(['pick-ns', 'pick-card', 'toggle-tag'])

const DOMAIN_META = {
  fin:  { color: '#0ea5e9', hint: '金融' },
  fit:  { color: '#22c55e', hint: '健身' },
  gen:  { color: '#f59e0b', hint: '元层' },
  llm:  { color: '#8b5cf6', hint: 'AI' },
  phil: { color: '#ec4899', hint: '哲学' },
  med:  { color: '#ef4444', hint: '医学' },
  law:  { color: '#6366f1', hint: '法律' },
  sw:   { color: '#14b8a6', hint: '软件' },
  prod: { color: '#84cc16', hint: '产品' },
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

const domains = computed(() => {
  const counts = props.nsCounts || {}
  return Object.keys(counts)
    .sort((a, b) => counts[b] - counts[a])
    .map(name => ({
      name,
      count: counts[name],
      color: (DOMAIN_META[name] || {}).color || '#64748b',
    }))
})

const activeTagSet = computed(() => new Set(props.activeTags || []))
const domainsOpen = ref(true)
const tagsOpen = ref(false)
const recentOpen = ref(false)
const cardsOpen = ref(true)
const cardListEl = ref(null)
const visibleCount = ref(100)
const BATCH_SIZE = 100

const visibleCards = computed(() => props.cards.slice(0, visibleCount.value))

watch(() => props.cards, () => {
  visibleCount.value = BATCH_SIZE
}, { deep: false })

watch(() => props.selectedId, async (id) => {
  if (!id) return
  if (!cardsOpen.value) cardsOpen.value = true
  const idx = props.cards.findIndex(card => card.id === id)
  if (idx >= visibleCount.value) {
    visibleCount.value = Math.ceil((idx + 1) / BATCH_SIZE) * BATCH_SIZE
  }
  await nextTick()
  scrollSelectedIntoView()
})

function scrollSelectedIntoView() {
  const el = cardListEl.value
  if (!el) return
  const active = el.querySelector('.card-list-item.active')
  if (!active) return
  active.scrollIntoView({ block: 'nearest' })
}

function onCardListScroll(e) {
  const el = e.currentTarget
  if (!el || visibleCount.value >= props.cards.length) return
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80
  if (nearBottom) {
    visibleCount.value = Math.min(props.cards.length, visibleCount.value + BATCH_SIZE)
  }
}
</script>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100%;
  overflow-y: auto;
  padding: 12px 0;
}

.sidebar-section {
  padding: 0 12px;
  margin-bottom: 20px;
}

.section-title {
  font-size: 10px;
  font-weight: 700;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding: 0 4px;
}

.ns-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ns-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #374151;
  text-align: left;
  transition: background 0.12s;
}

.ns-item:hover {
  background: #f3f4f6;
}

.ns-item.active {
  background: #eff6ff;
  color: #2563eb;
  font-weight: 600;
}

.ns-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ns-name {
  flex: 1;
}

.ns-count {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
}

.ns-item.active .ns-count {
  color: #2563eb;
}

.tag-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: #374151;
  text-align: left;
  transition: background 0.12s, color 0.12s;
}

.tag-item:hover {
  background: #f3f4f6;
}

.tag-item.active {
  background: #ecfdf5;
  color: #047857;
  font-weight: 600;
}

.tag-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-count {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
}

.tag-item.active .tag-count {
  color: #047857;
}

.tag-empty {
  padding: 6px 10px;
  font-size: 12px;
  color: #9ca3af;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 10px;
  border: none;
  background: transparent;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
  color: #374151;
  text-align: left;
  transition: background 0.12s;
}

.recent-item:hover {
  background: #f3f4f6;
}

.recent-item.active {
  background: #eff6ff;
}

.recent-type {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.recent-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.section-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: #6b7280;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  text-align: left;
}

.section-toggle:hover {
  color: #374151;
}

.section-count {
  margin-left: auto;
  color: #9ca3af;
  font-size: 11px;
}

.section-arrow {
  display: inline-block;
  transition: transform 0.12s;
  font-size: 14px;
  line-height: 1;
}

.section-arrow.open {
  transform: rotate(90deg);
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 2px;
}

.card-list-item {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  width: 100%;
  padding: 5px 5px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: #374151;
  text-align: left;
}

.card-list-item:hover {
  background: #f3f4f6;
}

.card-list-item.active {
  background: #eff6ff;
}

.card-list-index {
  width: 22px;
  flex-shrink: 0;
  color: #9ca3af;
  font-variant-numeric: tabular-nums;
  text-align: right;
  font-size: 11px;
  line-height: 18px;
}

.card-list-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.card-list-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 18px;
  color: #374151;
}

.card-list-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #9ca3af;
  font-family: monospace;
  font-size: 10px;
  line-height: 14px;
}

.card-list-empty {
  padding: 8px;
  font-size: 12px;
  color: #9ca3af;
}

.card-list-more {
  padding: 6px 8px;
  color: #9ca3af;
  font-size: 11px;
  text-align: center;
}
</style>
