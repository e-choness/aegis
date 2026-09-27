<!--
  Home-page hero: a dark stage with the animated Aegis shield at its centre and the three
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
        <div class="glow" aria-hidden="true"></div>
        <!-- The Aegis logo animates itself (scan line + pulsing core). -->
        <img class="logo" :src="withBase('/logo.svg')" alt="Aegis shield" />


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

const words = [
  { word: 'Guard', sub: 'Mask · label · block', link: '/packs/', pos: 'top' },
  { word: 'Pause', sub: 'A human decides', link: '/guide/approvals', pos: 'right' },
  { word: 'Prove', sub: 'Hash-chained evidence', link: '/guide/audit', pos: 'bottom' },
]
</script>

<style scoped>
.aegis-stage {
  /* The site's own palette (custom.css): follows light and dark mode. */
  --ink: var(--vp-c-text-1);
  --muted: var(--vp-c-text-2);
  --accent: var(--vp-c-brand-1);
  position: relative;
  overflow: hidden;
  background: var(--vp-c-bg);
  color: var(--ink);
  padding: 72px 24px 96px;
  margin-bottom: 48px; /* room before the feature cards */
}
.blobs { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.blobs path { fill: var(--vp-c-bg-soft); }

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
  background: var(--vp-home-hero-name-background);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
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
  border: 1px solid var(--vp-c-divider);
  color: var(--ink);
  font-size: 0.92rem;
  font-weight: 600;
  text-decoration: none;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}
.btn:hover { border-color: var(--accent); color: var(--accent); }
.btn.primary { background: var(--vp-button-brand-bg); border-color: var(--vp-button-brand-bg); color: #fff; }
.btn.primary:hover { background: var(--vp-button-brand-hover-bg); border-color: var(--vp-button-brand-hover-bg); color: #fff; }

.gem-wrap { position: relative; aspect-ratio: 1 / 0.92; }
.glow {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 72%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  /* The original home hero's blue glow. */
  background: var(--vp-home-hero-image-background-image);
  filter: var(--vp-home-hero-image-filter);
}
.logo {
  position: absolute;
  left: 50%;
  top: 50%;
  height: 54%;
  transform: translate(-50%, -50%);
  filter: drop-shadow(0 18px 40px rgba(37, 99, 235, 0.3));
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
  border: 1.5px solid var(--accent);
  border-radius: 50%;
  color: var(--accent);
  font-size: 20px;
  font-weight: 300;
  line-height: 22px;
  text-align: center;
  transition: transform 0.25s;
}
.word .sub { margin-top: 10px; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted); }
.word:hover .big { color: var(--accent); }
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
.side:hover { color: var(--accent); }
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
  background: var(--vp-c-divider);
}
.scroll:hover { color: var(--accent); }

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
  /* Too narrow to float words around the shield: logo on top, words in a row. */
  .gem-wrap {
    aspect-ratio: auto;
    display: grid;
    grid-template-columns: repeat(3, auto);
    justify-content: space-between;
    row-gap: 8px;
    padding-top: 250px;
  }
  .glow { top: 125px; width: 300px; }
  .logo { top: 125px; height: 220px; }
  .word { position: static; align-items: flex-start; }
  .word .big { font-size: 1.9rem; }
  .word .plus { right: -0.9em; }
  .word .sub { max-width: 7.5rem; line-height: 1.4; }
}
@media (prefers-reduced-motion: reduce) {
  .word .plus, .btn, .word .big { transition: none; }
}
</style>
