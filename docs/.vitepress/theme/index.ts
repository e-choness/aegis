import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import { h } from 'vue'
import AegisHero from './components/AegisHero.vue'
import VerdictBadge from './components/VerdictBadge.vue'
import SafeMermaid from './components/SafeMermaid.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  // The home page's hero is a custom stage (AegisHero.vue), placed before the features.
  Layout: () => h(DefaultTheme.Layout, null, { 'home-hero-before': () => h(AegisHero) }),
  enhanceApp({ app }) {
    app.component('Verdict', VerdictBadge)
    // Replaces the mermaid plugin's component, whose overlapping renders can
    // leave "Syntax error in text" boxes on the page (see SafeMermaid.vue).
    app.component('Mermaid', SafeMermaid)
  },
} satisfies Theme
