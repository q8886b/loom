<template>
  <div class="tree-node">
    <button
      :class="['row', { active: node.id === selectedId, has: hasChildren }]"
      :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
      @click="onPick"
    >
      <span
        v-if="hasChildren"
        class="caret"
        :class="{ open: expanded }"
        @click.stop="toggle"
      >▸</span>
      <span v-else class="caret-spacer"></span>
      <span class="layer" :style="{ background: layerColor[node.layer] }">{{ layerShort[node.layer] }}</span>
      <span class="type">[{{ node.type }}]</span>
      <span class="title">{{ node.title }}</span>
      <span v-if="hasChildren" class="count">{{ node.children.length }}</span>
    </button>
    <div v-if="hasChildren && expanded" class="children">
      <TreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :selected-id="selectedId"
        @pick="$emit('pick', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  selectedId: { type: String, default: '' },
})
const emit = defineEmits(['pick'])

const layerColor = {
  L1: '#94a3b8',
  L2_light: '#a3bffa',
  L2:       '#6366f1',
  L3:       '#10b981',
  L4:       '#f59e0b',
}
const layerShort = {
  L1: 'L1', L2_light: 'L2轻', L2: 'L2', L3: 'L3', L4: 'L4',
}

const hasChildren = computed(() => (props.node.children?.length || 0) > 0)
const expanded = ref(false)

function toggle() { expanded.value = !expanded.value }
function onPick() { emit('pick', props.node.id) }

// Auto-expand the path to selected node
watch(() => props.selectedId, (id) => {
  if (id && id.startsWith(props.node.id) && id !== props.node.id) {
    expanded.value = true
  }
}, { immediate: true })
</script>

<style scoped>
.tree-node { width: 100%; }
.row {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 4px 8px 4px 0; border: none;
  background: transparent; cursor: pointer; text-align: left;
  border-radius: 6px; font-size: 13px;
}
.row:hover { background: var(--bg); }
.row.active { background: var(--primary); color: #fff; }
.row.active .type, .row.active .count { color: rgba(255,255,255,0.85); }
.caret {
  width: 12px; flex-shrink: 0; cursor: pointer;
  font-size: 10px; color: var(--text-2);
  transition: transform 0.15s;
}
.caret.open { transform: rotate(90deg); }
.caret-spacer { width: 12px; flex-shrink: 0; }
.layer {
  display: inline-block; min-width: 30px; padding: 1px 4px;
  border-radius: 3px; color: #fff; font-size: 10px; text-align: center;
  flex-shrink: 0;
}
.type { color: var(--text-2); font-size: 11px; flex-shrink: 0; }
.title {
  flex: 1; min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.count {
  font-size: 10px; color: var(--text-2);
  background: var(--bg); padding: 1px 6px; border-radius: 8px;
  flex-shrink: 0;
}
.row.active .count { background: rgba(255,255,255,0.2); }
.children { width: 100%; }
</style>
