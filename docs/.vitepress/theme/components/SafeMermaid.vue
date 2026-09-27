<!--
  Replaces vitepress-plugin-mermaid's <Mermaid> component.

  The plugin's version re-renders on *any* attribute change of <html> (VitePress
  changes several during hydration and navigation), so renders overlap: they
  share mermaid's global config and the same element id, and whichever
  finishes last wins — sometimes a "Syntax error in text" box. Here renders
  run one at a time with unique ids, only when the theme actually changes, and
  a failed render keeps the last good diagram.
-->
<template>
  <div :class="props.class" v-html="svg"></div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{ graph: string; id: string; class?: string }>()
const svg = ref('')
let observer: MutationObserver | null = null
let renderedDark: boolean | null = null

type MermaidApi = typeof import('mermaid')['default']
let mermaidPromise: Promise<MermaidApi> | null = null
// Module-level: every diagram on the page renders through this one queue.
let queue: Promise<unknown> = Promise.resolve()
let counter = 0

function loadMermaid(): Promise<MermaidApi> {
  mermaidPromise ??= import('mermaid').then((m) => m.default)
  return mermaidPromise
}

async function renderNow(dark: boolean): Promise<void> {
  const mermaid = await loadMermaid()
  // The `mermaid:` block of config.mts; dark mode switches to mermaid's dark theme.
  const settings = ((await import('virtual:mermaid-config')) as { default?: { theme?: string } })
    .default ?? {}
  mermaid.initialize({
    ...settings,
    startOnLoad: false,
    theme: (dark ? 'dark' : settings.theme ?? 'default') as 'dark' | 'default',
  })
  const code = decodeURIComponent(props.graph)
  try {
    const { svg: out } = await mermaid.render(`${props.id}-r${counter++}`, code)
    svg.value = out
    renderedDark = dark
  } catch (err) {
    console.error(`mermaid: could not render ${props.id}`, err)
    // mermaid leaves its error element in <body>; don't show it to readers
    document.querySelectorAll('[id^="d' + props.id + '-r"]').forEach((el) => el.remove())
  }
}

function schedule(): void {
  const dark = document.documentElement.classList.contains('dark')
  if (dark === renderedDark) return
  queue = queue.then(() => renderNow(dark), () => renderNow(dark))
}

onMounted(() => {
  schedule()
  observer = new MutationObserver(schedule)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})

onUnmounted(() => observer?.disconnect())
</script>
