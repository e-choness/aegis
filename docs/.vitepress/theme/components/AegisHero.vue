<!--
  Home-page hero: a dark stage with a layered shield at its centre and the three
  things Aegis does — guard, pause, prove — floating around it.
-->
<template>
  <section class="aegis-stage">
    <svg class="blobs" viewBox="0 0 1200 700" preserveAspectRatio="none" aria-hidden="true">
      <path d="M-40 -20 C 180 40, 260 180, 180 360 S 60 640, 240 760 L -40 760 Z" />
      <path d="M1240 470 C 1100 430, 980 520, 1010 640 S 1120 760, 1240 760 Z" />
    </svg>

    <a class="side side-left" :href="withBase('/guide/')">Self-hosted · AGPL-3.0</a>
    <a class="side side-right" href="https://huggingface.co/spaces/echoness/aegis-server" target="_blank" rel="noopener">Live demo ↗</a>

    <div class="inner">
      <div class="copy">
        <p class="eyebrow">AEGIS</p>
        <h1>The self-hosted AI gateway that shows its&nbsp;work</h1>
        <p class="tagline">
          Put guardrails, human approvals and a tamper-evident audit trail between your apps and any
          LLM — behind an OpenAI-compatible endpoint, configured in one YAML file.
        </p>
        <div class="actions">
          <a class="btn primary" :href="withBase('/guide/quickstart')">Quickstart →</a>
          <a class="btn" href="https://huggingface.co/spaces/echoness/aegis-server" target="_blank" rel="noopener">Live demo ↗</a>
          <a class="btn" :href="withBase('/guide/concepts')">How it works</a>
          <a class="btn" :href="withBase('/develop/plugins')">Write a plugin</a>
        </div>
      </div>

      <div class="gem-wrap">
        <svg class="gem" viewBox="0 0 600 600" role="img" aria-label="Aegis shield">
          <defs>
            <radialGradient id="aegis-glow" cx="42%" cy="44%" r="50%">
              <stop offset="0%" stop-color="#22e3f2" stop-opacity="0.55" />
              <stop offset="100%" stop-color="#22e3f2" stop-opacity="0" />
            </radialGradient>
          </defs>
          <circle cx="260" cy="270" r="250" fill="url(#aegis-glow)" />
          <polygon
            v-for="(layer, i) in layers"
            :key="i"
            :points="layer.points"
            :fill="layer.color"
            :style="{ animationDuration: `${14 + i * 3}s`, animationDelay: `${-i * 1.7}s` }"
            class="layer"
          />
        </svg>

        <a v-for="w in words" :key="w.word" :class="['word', w.pos]" :href="withBase(w.link)">
          <span class="big">{{ w.word }}<span class="plus" aria-hidden="true">+</span></span>
          <span class="sub">{{ w.sub }}</span>
        </a>
      </div>
    </div>

    <a class="scroll" href="#see-it-work">See it work</a>
  </section>
</template>

<script setup lang="ts">
import { withBase } from 'vitepress'

// A hand-drawn shield outline (viewBox 600×600): flat-ish top, tapering to a point.
const SHIELD: [number, number][] = [
  [312, 64], [480, 124], [508, 262], [454, 404], [320, 530],
  [296, 542], [262, 518], [138, 392], [94, 246], [136, 110],
]
const CENTER: [number, number] = [300, 300]
// Outer (deep navy) to inner (bright cyan), as in a layered gem.
const COLORS = ['#0f2745', '#123763', '#154a82', '#175ea0', '#1873bb', '#178bcf', '#16a9dd', '#19c9ea', '#34e4f2']

const layers = COLORS.map((color, i) => {
  const scale = 1 - i * 0.068
  const [dx, dy] = [-i * 7, -i * 4] // brighter layers drift up and to the left
  const points = SHIELD.map(([x, y]) => [
    CENTER[0] + (x - CENTER[0]) * scale + dx,
    CENTER[1] + (y - CENTER[1]) * scale + dy,
  ].map((v) => v.toFixed(1)).join(',')).join(' ')
  return { color, points }
})

const words = [
  { word: 'Guard', sub: 'Mask · label · block', link: '/packs/', pos: 'top' },
  { word: 'Pause', sub: 'A human decides', link: '/guide/approvals', pos: 'right' },
  { word: 'Prove', sub: 'Hash-chained evidence', link: '/guide/audit', pos: 'bottom' },
]
</script>

<style scoped>
.aegis-stage {
  --ink: #e8f1f8;
  --muted: #9fb3c8;
  --cyan: #2fe0f0;
  position: relative;
  overflow: hidden;
  background: #071722;
  color: var(--ink);
  padding: 72px 24px 96px;
  margin-bottom: 48px; /* room before the feature cards */
}
.blobs { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.blobs path { fill: rgba(255, 255, 255, 0.028); }

.inner {
  position: relative;
  max-width: 1152px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: 24px;
  align-items: center;
}

.eyebrow {
  margin: 0 0 14px;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.32em;
  color: #ff9a57;
}
h1 {
  margin: 0;
  font-size: clamp(2.1rem, 4.2vw, 3.4rem);
  line-height: 1.08;
  font-weight: 250;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.tagline { margin: 20px 0 0; max-width: 34rem; font-size: 1.05rem; line-height: 1.6; color: var(--muted); }

.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 30px; }
.btn {
  display: inline-block;
  padding: 9px 18px;
  border-radius: 999px;
  border: 1px solid rgba(232, 241, 248, 0.28);
  color: var(--ink);
  font-size: 0.92rem;
  font-weight: 600;
  text-decoration: none;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}
.btn:hover { border-color: var(--cyan); color: var(--cyan); }
.btn.primary { background: #f26b21; border-color: #f26b21; color: #fff; }
.btn.primary:hover { background: #e2561b; border-color: #e2561b; color: #fff; }

.gem-wrap { position: relative; aspect-ratio: 1 / 0.92; }
.gem { position: absolute; inset: 4% 8%; width: 84%; height: 92%; }
.layer {
  opacity: 0.92;
  transform-box: fill-box;
  transform-origin: 50% 50%;
  animation: drift ease-in-out infinite alternate;
}
@keyframes drift {
  from { transform: rotate(-2.2deg) translate(-3px, 2px); }
  to { transform: rotate(2.2deg) translate(3px, -2px); }
}

.word { position: absolute; display: flex; flex-direction: column; text-decoration: none; color: var(--ink); }
.word .big {
  position: relative;
  font-size: clamp(2.6rem, 5.4vw, 4.4rem);
  font-weight: 200;
  line-height: 1;
  letter-spacing: -0.01em;
  transition: color 0.2s;
}
.word .plus {
  position: absolute;
  top: -0.1em;
  right: -0.72em;
  width: 26px;
  height: 26px;
  border: 1.5px solid var(--cyan);
  border-radius: 50%;
  color: var(--cyan);
  font-size: 20px;
  font-weight: 300;
  line-height: 22px;
  text-align: center;
  transition: transform 0.25s;
}
.word .sub { margin-top: 10px; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: #cbd5e1; }
.word:hover .big { color: var(--cyan); }
.word:hover .plus { transform: rotate(90deg); }
.word.top { top: 8%; left: 2%; }
.word.right { top: 44%; right: 0; }
.word.bottom { bottom: 6%; left: 18%; }

.side {
  position: absolute;
  top: 50%;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
  text-decoration: none;
  writing-mode: vertical-rl;
}
.side:hover { color: var(--cyan); }
.side-left { left: 18px; transform: translateY(-50%) rotate(180deg); }
.side-right { right: 18px; transform: translateY(-50%); }

.scroll {
  position: absolute;
  left: 50%;
  bottom: 22px;
  transform: translateX(-50%);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ink);
  text-decoration: none;
  padding-bottom: 30px;
}
.scroll::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 1px;
  height: 22px;
  background: rgba(232, 241, 248, 0.45);
}
.scroll:hover { color: var(--cyan); }

@media (max-width: 960px) {
  .inner { grid-template-columns: 1fr; }
  .gem-wrap { max-width: 560px; width: 100%; margin: 12px auto 0; }
  .side { display: none; }
}
@media (max-width: 520px) {
  .aegis-stage { padding: 48px 20px 88px; }
  .word .big { font-size: 2.3rem; }
  .word .plus { width: 20px; height: 20px; font-size: 16px; line-height: 17px; }
  .word .sub { font-size: 0.66rem; }
  .word.right { right: 9%; }
}
@media (prefers-reduced-motion: reduce) {
  .layer { animation: none; }
  .word .plus, .btn, .word .big { transition: none; }
}
</style>
