<template>
  <div class="panel">
    <!-- History navigation — placed at the top of the card panel so the
         mouse never has to leave the right column while browsing cards. -->
    <div class="history-bar">
      <button
        class="history-btn"
        :disabled="!canBack"
        @click="$emit('back')"
        title="后退（⌘←）"
      >‹</button>
      <button
        class="history-btn"
        :disabled="!canForward"
        @click="$emit('forward')"
        title="前进（⌘→）"
      >›</button>
      <div class="history-dropdown" v-click-outside="() => historyOpen = false">
        <button
          class="history-dropdown-btn"
          :disabled="!history.length"
          @click="historyOpen = !historyOpen"
          title="浏览历史"
        >▾<span v-if="history.length" class="history-count">{{ history.length }}</span></button>
        <div v-if="historyOpen" class="history-panel">
          <div class="history-panel-title">浏览历史（{{ history.length }}）</div>
          <div
            v-for="item in historyList"
            :key="item.idx"
            :class="['history-item', { active: item.idx === historyIndex }]"
            @click="onJump(item.idx)"
          >
            <span class="history-mark">{{ item.idx === historyIndex ? '▶' : '' }}</span>
            <code>{{ item.id }}</code>
          </div>
          <div v-if="!history.length" class="history-empty">尚无浏览记录</div>
        </div>
      </div>
    </div>

    <div v-if="!cardId" class="empty">点击图谱或列表中的卡片查看详情</div>
    <div v-else-if="loading" class="empty">加载中…</div>
    <div v-else-if="!card" class="empty">卡片不存在: {{ cardId }}</div>
    <article v-else class="card">
      <header>
        <span class="layer-tag" :style="{ background: layerColor[card.layer] }">
          {{ card.layer }}
        </span>
        <span class="type-tag">[{{ card.type }}]</span>
        <span v-if="card.origin === 'human'" class="origin-tag">human</span>
        <span class="ns">{{ card.namespace }}</span>
        <button class="focus-btn" @click="$emit('focus', card.id)" title="聚焦此卡">聚焦</button>
        <button class="close" @click="$emit('close')">✕</button>
      </header>
      <h2>{{ card.title }}</h2>
      <div class="id-line">
        <code>{{ card.id }}</code>
        <span v-for="tag in (card.tags || [])" :key="tag" class="tag-chip">{{ tag }}</span>
        <button
          v-if="isClickableSource"
          class="source source-link"
          title="查看 source 卡"
          @click="$emit('pick', card.source)"
        >
          ← {{ card.source }}
        </button>
        <span v-else-if="card.source" class="source">← {{ card.source }}</span>
      </div>

      <section v-if="card.links && card.links.length" class="links">
        <div class="section-title">链接（{{ card.links.length }}）</div>
        <div class="link-list">
          <button
            v-for="lid in card.links"
            :key="lid"
            class="link-chip"
            @click="$emit('pick', lid)"
          >
            {{ lid }}
          </button>
        </div>
      </section>

      <section class="content markdown" v-html="renderedContent"></section>

      <footer>
        <span>use: {{ card.use_count || 0 }}</span>
        <span>search: {{ card.search_count || 0 }}</span>
      </footer>
    </article>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { marked } from 'marked'
import { getCard } from '../api.js'

const props = defineProps({
  cardId: { type: String, default: '' },
  canBack: { type: Boolean, default: false },
  canForward: { type: Boolean, default: false },
  history: { type: Array, default: () => [] },
  historyIndex: { type: Number, default: -1 },
})
const emit = defineEmits(['pick', 'focus', 'close', 'back', 'forward', 'jump'])

function onJump(idx) {
  historyOpen.value = false
  emit('jump', idx)
}

const historyOpen = ref(false)

const historyList = computed(() =>
  props.history.map((id, idx) => ({ id, idx })).reverse()
)

// Simple click-outside directive for the history dropdown.
const vClickOutside = {
  mounted(el, binding) {
    el._clickOutside = (e) => { if (!el.contains(e.target)) binding.value() }
    document.addEventListener('click', el._clickOutside, true)
  },
  unmounted(el) {
    document.removeEventListener('click', el._clickOutside, true)
  },
}

const layerColor = {
  L1: '#94a3b8',
  L2_light: '#a3bffa',
  L2: '#6366f1',
  L3: '#10b981',
  L4: '#f59e0b',
}

const card = ref(null)
const loading = ref(false)

marked.setOptions({ breaks: true, gfm: true })

const renderedContent = computed(() => {
  if (!card.value?.content) return ''
  return marked.parse(card.value.content)
})

const isClickableSource = computed(() => {
  const source = card.value?.source || ''
  return source.includes(':') && !source.includes('/')
})

async function load(id) {
  if (!id) { card.value = null; return }
  loading.value = true
  try {
    card.value = await getCard(id)
  } catch (e) {
    card.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.cardId, load, { immediate: true })
</script>

<style scoped>
.panel { padding: 16px; }
.empty { color: var(--text-2); padding: 24px; text-align: center; font-size: 13px; }

.history-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: -8px -8px 12px -8px;
  padding: 6px 8px;
  background: var(--bg);
  border-radius: var(--radius);
}
.history-btn, .history-dropdown-btn {
  border: none;
  background: var(--surface);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  color: var(--text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 30px;
  line-height: 1;
  box-shadow: var(--shadow-sm);
}
.history-btn:hover:not(:disabled), .history-dropdown-btn:hover:not(:disabled) {
  background: #fff;
}
.history-btn:disabled, .history-dropdown-btn:disabled {
  color: var(--text-2);
  opacity: 0.4;
  cursor: default;
  box-shadow: none;
}
.history-count {
  font-size: 10px;
  font-weight: 700;
  background: var(--text-2);
  color: #fff;
  padding: 1px 5px;
  border-radius: 8px;
  line-height: 1;
}
.history-dropdown {
  position: relative;
}
.history-panel {
  position: absolute;
  top: 34px;
  left: 0;
  min-width: 320px;
  max-width: 440px;
  max-height: 360px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  z-index: 70;
  padding: 4px 0;
}
.history-panel-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 6px 12px 4px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
  border-bottom: 1px solid var(--bg);
}
.history-item:hover { background: var(--bg); }
.history-item.active { background: rgba(37, 99, 235, 0.08); }
.history-item.active code { color: var(--primary); font-weight: 600; }
.history-mark {
  width: 12px;
  color: var(--primary);
  font-size: 10px;
}
.history-item code {
  font-family: monospace;
  font-size: 11px;
  color: var(--text);
  word-break: break-all;
}
.history-empty {
  padding: 12px;
  color: var(--text-2);
  font-size: 12px;
  text-align: center;
}

.card header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
}
.layer-tag {
  display: inline-block; min-width: 36px; padding: 2px 6px;
  border-radius: 4px; color: #fff; font-size: 11px; text-align: center;
}
.type-tag { color: var(--text-2); font-size: 13px; }
.origin-tag {
  color: #047857;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.ns { color: var(--text-2); font-size: 12px; font-family: monospace; }
.focus-btn {
  margin-left: auto; border: 1px solid var(--primary); background: var(--primary);
  color: #fff; padding: 3px 10px; border-radius: 5px; cursor: pointer; font-size: 12px;
}
.focus-btn:hover { opacity: 0.9; }
.close {
  border: none; background: transparent;
  color: var(--text-2); cursor: pointer; font-size: 16px;
}
h2 { margin: 0 0 6px 0; font-size: 17px; line-height: 1.35; }
.id-line {
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
  font-size: 12px; color: var(--text-2);
  margin-bottom: 12px;
}
.id-line code {
  background: var(--bg); padding: 2px 6px; border-radius: 4px;
  font-family: monospace; font-size: 12px;
}
.source { font-style: italic; }
.source-link {
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  color: var(--text-2);
  font-family: monospace;
  font-size: 12px;
}
.source-link:hover { color: var(--primary); text-decoration: underline; }
.tag-chip {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #047857;
  padding: 1px 7px;
  border-radius: 12px;
  font-size: 11px;
}
.section-title {
  font-size: 12px; font-weight: 600; color: var(--text-2);
  margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em;
}
.links { margin-bottom: 16px; }
.link-list { display: flex; flex-wrap: wrap; gap: 4px; }
.link-chip {
  background: var(--bg); border: 1px solid var(--border);
  padding: 2px 8px; border-radius: 12px;
  font-size: 11px; font-family: monospace;
  cursor: pointer; color: var(--text-2);
}
.link-chip:hover { background: var(--primary); color: #fff; }
.content { border-top: 1px solid var(--border); padding-top: 12px; }
.markdown { font-size: 13px; line-height: 1.7; color: var(--text); }
.markdown :deep(h1) {
  font-size: 17px; font-weight: 700; margin: 16px 0 8px;
  padding-bottom: 4px; border-bottom: 1px solid var(--border);
}
.markdown :deep(h2) {
  font-size: 15px; font-weight: 700; margin: 14px 0 6px;
}
.markdown :deep(h3) {
  font-size: 14px; font-weight: 600; margin: 12px 0 4px; color: var(--text);
}
.markdown :deep(h4) {
  font-size: 13px; font-weight: 600; margin: 10px 0 4px; color: var(--text-2);
}
.markdown :deep(p) { margin: 6px 0; }
.markdown :deep(ul), .markdown :deep(ol) { margin: 6px 0; padding-left: 22px; }
.markdown :deep(li) { margin: 3px 0; }
.markdown :deep(strong) { font-weight: 600; color: var(--text); }
.markdown :deep(em) { font-style: italic; color: var(--text-2); }
.markdown :deep(code) {
  font-family: 'SF Mono', Menlo, Monaco, Consolas, monospace;
  font-size: 12px; background: var(--bg);
  padding: 1px 5px; border-radius: 3px;
}
.markdown :deep(pre) {
  background: var(--bg); padding: 10px 12px;
  border-radius: 6px; overflow-x: auto; margin: 8px 0;
}
.markdown :deep(pre code) { background: transparent; padding: 0; }
.markdown :deep(blockquote) {
  border-left: 3px solid var(--primary);
  margin: 8px 0; padding: 4px 12px;
  color: var(--text-2); background: rgba(37, 99, 235, 0.04);
}
.markdown :deep(hr) {
  border: none; border-top: 1px solid var(--border);
  margin: 12px 0;
}
.markdown :deep(a) {
  color: var(--primary); text-decoration: none;
}
.markdown :deep(a:hover) { text-decoration: underline; }
.markdown :deep(table) {
  border-collapse: collapse; width: 100%; margin: 8px 0;
  font-size: 12px;
}
.markdown :deep(th), .markdown :deep(td) {
  border: 1px solid var(--border); padding: 4px 8px; text-align: left;
}
.markdown :deep(th) { background: var(--bg); font-weight: 600; }
footer {
  margin-top: 16px; padding-top: 8px; border-top: 1px solid var(--border);
  display: flex; gap: 16px; font-size: 11px; color: var(--text-2);
}
</style>
