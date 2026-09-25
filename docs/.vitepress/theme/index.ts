import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import VerdictBadge from './components/VerdictBadge.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('Verdict', VerdictBadge)
  },
} satisfies Theme
