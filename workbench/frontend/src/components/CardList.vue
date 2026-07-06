<template>
  <div class="list">
    <div class="list-head">卡片树（{{ totalCount }}）</div>
    <div class="list-body">
      <TreeNode
        v-for="root in roots"
        :key="root.id"
        :node="root"
        :depth="0"
        :selected-id="selectedId"
        @pick="$emit('pick', $event)"
      />
      <div v-if="!roots.length" class="empty">无卡片</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import TreeNode from './TreeNode.vue'

const props = defineProps({
  roots: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
})
defineEmits(['pick'])

const totalCount = computed(() => {
  const count = (arr) =>
    (arr || []).reduce((a, n) => a + 1 + count(n.children || []), 0)
  return count(props.roots)
})
</script>

<style scoped>
.list { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.list-head {
  padding: 10px 12px; font-size: 12px; font-weight: 600;
  color: var(--text-2); text-transform: uppercase; letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}
.list-body { flex: 1; overflow: auto; padding: 4px; }
.empty { padding: 12px; color: var(--text-2); font-size: 12px; text-align: center; }
</style>
