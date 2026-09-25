<script setup lang="ts">
// Inline verdict chip: <Verdict kind="block" />
defineProps<{ kind: 'allow' | 'sanitize' | 'block' | 'require_approval' }>()
</script>

<template>
  <span class="verdict" :class="`verdict--${kind}`">{{ kind }}</span>
</template>

<style scoped>
.verdict {
  display: inline-block;
  padding: 0 10px;
  border-radius: 999px;
  font-family: var(--vp-font-family-mono);
  font-size: 0.8em;
  line-height: 1.7;
  border: 1px solid currentColor;
  white-space: nowrap;
  vertical-align: 0.05em;
}
.verdict--allow { color: var(--aegis-allow); background: var(--aegis-allow-soft); }
.verdict--sanitize { color: var(--aegis-sanitize); background: var(--aegis-sanitize-soft); }
.verdict--block { color: var(--aegis-block); background: var(--aegis-block-soft); }
.verdict--require_approval { color: var(--aegis-approval); background: var(--aegis-approval-soft); }
</style>
