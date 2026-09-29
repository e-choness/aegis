// Copies the site-facing files from media/ (the single home of Aegis brand assets)
// into docs/public, which VitePress serves at the site root. docs/public copies are
// git-ignored; edit media/ and re-run (docs:* npm scripts do this automatically).
import { cpSync, mkdirSync } from 'node:fs'

const out = 'docs/public'
mkdirSync(`${out}/fonts`, { recursive: true })
for (const f of ['logo.svg', 'social-preview.png']) cpSync(`media/${f}`, `${out}/${f}`)
cpSync('media/fonts/MontserratAlternates-Bold-latin.woff2', `${out}/fonts/MontserratAlternates-Bold-latin.woff2`)
