<template>
  <div class="ns">
    <div class="ns-head">命名空间</div>
    <div class="ns-body">
      <button
        :class="['ns-row', { active: !activeNs }]"
        @click="$emit('pick', '')"
      >
        <span class="ns-name">全部</span>
        <span class="ns-count">{{ totalCount }}</span>
      </button>
      <button
        v-for="(count, name) in counts"
        :key="name"
        :class="['ns-row', { active: activeNs === name }]"
        @click="$emit('pick', name)"
      >
        <span class="ns-name">{{ name }}</span>
        <span class="ns-count">{{ count }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  activeNs: { type: String, default: '' },
  counts: { type: Object, default: () => ({}) },
})
defineEmits(['pick'])
const totalCount = computed(() =>
  Object.values(props.counts).reduce((a, b) => a + b, 0)
)
</script>

<style scoped>
.ns { border-bottom: 1px solid var(--border); }
.ns-head {
  padding: 10px 12px; font-size: 12px; font-weight: 600;
  color: var(--text-2); text-transform: uppercase; letter-spacing: 0.04em;
}
.ns-body { display: flex; flex-direction: column; padding: 0 4px 8px 4px; }
.ns-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; border: none; background: transparent; cursor: pointer;
  border-radius: 6px; font-size: 13px;
}
.ns-row:hover { background: var(--bg); }
.ns-row.active { background: var(--primary); color: #fff; }
.ns-count {
  font-size: 11px; color: var(--text-2);
  background: var(--bg); padding: 1px 6px; border-radius: 8px;
}
.ns-row.active .ns-count { background: rgba(255,255,255,0.2); color: #fff; }
</style>
