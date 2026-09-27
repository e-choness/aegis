// Usage: node scripts/gen-terminal-demo.cjs images/terminal-demo.svg
// Generates images/terminal-demo.svg — an animated, looping terminal replay of
// scripts/cli-tour.sh (config: examples/cli-tour.yaml). Pure SVG + CSS (no
// script) so it animates inside a GitHub README <img>. The lines below are that
// script's real output; long lines wrap the way a 100-column terminal would.
const fs = require('fs');

const W = 1100, PAD = 24, TOP = 64, LH = 23, CW = 8.45; // char width @ 14px mono
const C = { cmd: '#e6edf3', prompt: '#ff7a2e', out: '#9fb0c8', dim: '#5f7190', amber: '#fbbf24', red: '#f87171', green: '#4ade80', cyan: '#67e8f9', rule: '#2a3a55' };

const RUN = '83a0c623-103a-4e8e-8177-9ae2a5cc5175';
// [kind, text, color]; kinds: cmd (typed), out, rule, gap (blank line)
const script = [
  ['cmd', 'aegis plugin list --group aegis.packs'],
  ['out', '  Name                  Package                                Version', C.dim],
  ['out', '  aegis.budgets         aegis-gateway-pack-budgets             2.0.0a5', C.out],
  ['out', '  aegis.classification  aegis-gateway-pack-classification      2.0.0a5', C.out],
  ['out', '  aegis.content         aegis-gateway-pack-content             2.0.0a5', C.cyan],
  ['out', '  aegis.pii             aegis-gateway-pack-pii                 2.0.0a5', C.out],
  ['out', '  aegis.policy          aegis-gateway-pack-classification      2.0.0a5', C.cyan],
  ['out', '  aegis.residency       aegis-gateway-pack-residency           2.0.0a5', C.out],
  ['gap'],
  ['cmd', 'aegis runs create "Why is api_key: 8f14e45fceea167a5a36dedd4bea2543 rejected?" --route default'],
  ['out', 'run_id: 19b3e7e5-7017-4c7e-9732-497a378831ce', C.out],
  ['out', 'status: blocked', C.red],
  ['cmd', 'aegis runs create "What is our refund policy?" --route underwriting'],
  ['out', 'status: completed   response: Risk: low.', C.green],
  ['cmd', 'aegis runs create "Applicant SIN 046-454-286, assess risk" --route underwriting --approver jane'],
  ['out', `run_id: ${RUN}`, C.out],
  ['out', 'status: paused', C.amber],
  ['cmd', `AEGIS_API_KEY=$JANE_KEY aegis runs deny ${RUN}`],
  ['out', `Run ${RUN} denied: status=denied`, C.out],
  ['gap'],
  ['cmd', `aegis explain ${RUN}`],
  ['out', 'run 83a0c623  route=underwriting  principal=svc-underwriting  status=denied', C.cmd],
  ['out', 'config=sha256:3fc4c49815668ae0b7364b246258f4904762966ea2ff5a24f56ff12efde7a521', C.dim],
  ['rule'],
  ['out', '  guard         no_secrets                ALLOW', C.green],
  ['out', '  ingress       pii.mask                  SANITIZE  reason=masked 1 CA_SIN — the model sees placeholders, never the values', C.cyan],
  ['out', "  guard         residency_ca              REQUIRE_APPROVAL  reason=residency: region 'us-east-1' for route", C.amber],
  ['out', "                                          'underwriting' is not in the allowed set ['ca-central-1']", C.amber],
  ['out', '  ingress       residency_ca              DENIED  reason=run denied by reviewer', C.red],
  ['rule'],
  ['out', '  short-circuited at ingress/residency_ca · provider never called', C.dim],
  ['gap'],
  ['cmd', 'aegis audit export -o ledger.jsonl && aegis audit verify ledger.jsonl'],
  ['out', 'Exported 6 record(s) to ledger.jsonl', C.out],
  ['out', 'OK  6 record(s) verified — chain is intact.', C.green],
];

// Timeline: commands type at a steady pace, output appears line by line.
let t = 0.4;
const lines = script.map(([kind, text = '', color]) => {
  let start = t, typeFor = 0;
  if (kind === 'cmd') {
    t += 0.5;
    start = t;
    typeFor = Math.min(1.6, Math.max(0.5, text.length * 0.018));
    t += typeFor + 0.45;
  } else {
    t += kind === 'gap' ? 0.1 : 0.14;
  }
  return [kind, text, color ?? (kind === 'rule' ? C.rule : C.cmd), start, typeFor];
});
const HOLD_END = t + 4.5, FADE_END = HOLD_END + 0.8, CYCLE = FADE_END + 0.6;

const H = TOP + lines.length * LH + 30;
const pct = (s) => ((s / CYCLE) * 100).toFixed(2) + '%';
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

let css = '';
let body = '';
lines.forEach(([kind, text, color, start, typeFor], i) => {
  const y = TOP + i * LH;
  if (kind === 'gap') return;
  css += `.l${i}{animation:l${i} ${CYCLE.toFixed(2)}s linear infinite}` +
    `@keyframes l${i}{0%,${pct(start)}{opacity:0}${pct(start + 0.01)},${pct(HOLD_END)}{opacity:1}${pct(FADE_END)},100%{opacity:0}}\n`;
  if (kind === 'rule') {
    body += `<line class="l${i}" x1="${PAD}" x2="${W - PAD}" y1="${y - 5}" y2="${y - 5}" stroke="${color}" stroke-dasharray="2 3"/>\n`;
    return;
  }
  if (kind === 'cmd') {
    const width = (text.length + 2) * CW + 12;
    body += `<g class="l${i}"><text x="${PAD}" y="${y}" fill="${C.prompt}">$</text>` +
      `<text x="${PAD + 2 * CW}" y="${y}" fill="${color}" xml:space="preserve">${esc(text)}</text>` +
      `<rect class="t${i}" transform="translate(${width} 0)" x="${PAD + 2 * CW}" y="${y - 16}" width="${width}" height="22" fill="#0b1220"/></g>\n`;
    // Typing: a background-coloured cover slides right in character-sized steps.
    css += `.t${i}{animation:t${i} ${CYCLE.toFixed(2)}s infinite}` +
      `@keyframes t${i}{0%,${pct(start)}{transform:translateX(0);animation-timing-function:steps(${text.length},end)}` +
      `${pct(start + typeFor)},100%{transform:translateX(${width}px)}}\n`;
    return;
  }
  body += `<text class="l${i}" x="${PAD}" y="${y}" fill="${color}" xml:space="preserve">${esc(text)}</text>\n`;
});

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="t d">
<title id="t">Aegis CLI tour</title>
<desc id="d">aegis plugin list shows the installed policy packs. A prompt containing an API key is blocked; a clean question to the underwriting route is answered; one carrying a Canadian SIN pauses for approval because the route's model is in us-east-1. Reviewer jane denies it, aegis explain shows the verdict trail, and the exported evidence ledger verifies offline.</desc>
<style>
text{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:14px}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
.cursor{animation:blink 1s steps(1) infinite}@keyframes blink{50%{opacity:0}}
${css}</style>
<rect width="${W}" height="${H}" rx="12" fill="#0b1220" stroke="#1e2d45"/>
<rect width="${W}" height="36" rx="12" fill="#111b2e"/><rect y="24" width="${W}" height="12" fill="#111b2e"/>
<circle cx="22" cy="18" r="6" fill="#ff5f57"/><circle cx="42" cy="18" r="6" fill="#febc2e"/><circle cx="62" cy="18" r="6" fill="#28c840"/>
<text x="${W / 2}" y="23" fill="#6f86ab" text-anchor="middle" style="font-size:13px">aegis — scripts/cli-tour.sh</text>
${body}<text x="${PAD}" y="${TOP + lines.length * LH}" fill="${C.prompt}">$ <tspan class="cursor" fill="${C.cmd}">▍</tspan></text>
</svg>
`;
fs.writeFileSync(process.argv[2], svg);
console.log('wrote', process.argv[2], `${W}x${H}`, `cycle ${CYCLE.toFixed(1)}s`);
