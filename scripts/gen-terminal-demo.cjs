// Usage: node scripts/gen-terminal-demo.cjs images/terminal-demo.svg
// Generates images/terminal-demo.svg — an animated, looping terminal replay of
// examples/02_approval_flow.py. Pure SVG + CSS (no script) so it
// animates inside a GitHub README <img>.
const fs = require('fs');

const CYCLE = 18; // seconds
const W = 1000, PAD = 24, TOP = 64, LH = 24, CW = 8.45; // char width @ 14px mono

const C = { cmd: '#e6edf3', prompt: '#ff7a2e', out: '#9fb0c8', dim: '#5f7190', amber: '#fbbf24', red: '#f87171', green: '#4ade80', rule: '#2a3a55' };

// [kind, text, color, startSeconds, typeSeconds]
const lines = [
  ['cmd', 'aegis runs create "Applicant SIN is 046-454-286, assess risk" --route underwriting', C.cmd, 0.4, 1.6],
  ['out', 'run_id: 13cdfd49', C.out, 2.3],
  ['out', 'status: paused', C.amber, 2.5],
  ['cmd', 'AEGIS_API_KEY=$JANE_KEY aegis runs deny 13cdfd49', C.cmd, 3.4, 1.1],
  ['out', 'Run 13cdfd49 denied: status=denied', C.out, 4.8],
  ['cmd', 'aegis explain 13cdfd49', C.cmd, 5.8, 0.6],
  ['out', 'run 13cdfd49  route=underwriting  principal=svc-underwriting  status=denied', C.cmd, 6.8],
  ['rule', '', C.rule, 6.9],
  ['out', '  guard     residency_ca   REQUIRE_APPROVAL  region \'us-east-1\' not in allowed [\'ca-central-1\']', C.amber, 7.1],
  ['out', '  ingress   residency_ca   DENIED            run denied by reviewer', C.red, 7.3],
  ['rule', '', C.rule, 7.4],
  ['out', '  short-circuited at ingress/residency_ca · provider never called', C.dim, 7.6],
  ['cmd', 'aegis audit export -o ledger.jsonl && aegis audit verify ledger.jsonl', C.cmd, 8.8, 1.7],
  ['out', 'OK  7 record(s) verified — chain is intact.', C.green, 11.0],
];

const H = TOP + lines.length * LH + 30;
const pct = (s) => ((s / CYCLE) * 100).toFixed(2) + '%';
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const HOLD_END = 16.6, FADE_END = 17.4;

let css = '';
let body = '';
lines.forEach(([kind, text, color, start, typeFor], i) => {
  const y = TOP + i * LH;
  css += `.l${i}{animation:l${i} ${CYCLE}s linear infinite}` +
    `@keyframes l${i}{0%,${pct(start)}{opacity:0}${pct(start + 0.01)},${pct(HOLD_END)}{opacity:1}${pct(FADE_END)},100%{opacity:0}}\n`;
  if (kind === 'rule') {
    body += `<line class="l${i}" x1="${PAD}" x2="${W - PAD}" y1="${y - 5}" y2="${y - 5}" stroke="${color}" stroke-dasharray="2 3"/>\n`;
    return;
  }
  if (kind === 'cmd') {
    const width = (text.length + 2) * CW + 12;
    const chars = text.length;
    body += `<g class="l${i}"><text x="${PAD}" y="${y}" fill="${C.prompt}">$</text>` +
      `<text x="${PAD + 2 * CW}" y="${y}" fill="${color}">${esc(text)}</text>` +
      `<rect class="t${i}" transform="translate(${width} 0)" x="${PAD + 2 * CW}" y="${y - 16}" width="${width}" height="22" fill="#0b1220"/></g>\n`;
    // Typing: a background-coloured cover slides right in character-sized steps.
    css += `.t${i}{animation:t${i} ${CYCLE}s infinite}` +
      `@keyframes t${i}{0%,${pct(start)}{transform:translateX(0);animation-timing-function:steps(${chars},end)}` +
      `${pct(start + typeFor)},100%{transform:translateX(${width}px)}}\n`;
    return;
  }
  body += `<text class="l${i}" x="${PAD}" y="${y}" fill="${color}" xml:space="preserve">${esc(text)}</text>\n`;
});

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="t d">
<title id="t">Aegis approval-flow replay</title>
<desc id="d">A loan-underwriting request carrying a Canadian SIN is routed to a US-region model. The residency guardrail pauses it for approval, reviewer jane denies it, aegis explain shows the verdict trail, and the exported audit ledger verifies offline.</desc>
<style>
text{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:14px}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
.cursor{animation:blink 1s steps(1) infinite}@keyframes blink{50%{opacity:0}}
${css}</style>
<rect width="${W}" height="${H}" rx="12" fill="#0b1220" stroke="#1e2d45"/>
<rect width="${W}" height="36" rx="12" fill="#111b2e"/><rect y="24" width="${W}" height="12" fill="#111b2e"/>
<circle cx="22" cy="18" r="6" fill="#ff5f57"/><circle cx="42" cy="18" r="6" fill="#febc2e"/><circle cx="62" cy="18" r="6" fill="#28c840"/>
<text x="${W / 2}" y="23" fill="#6f86ab" text-anchor="middle" style="font-size:13px">aegis — examples/02_approval_flow.py</text>
${body}<text x="${PAD}" y="${TOP + lines.length * LH}" fill="${C.prompt}">$ <tspan class="cursor" fill="${C.cmd}">▍</tspan></text>
</svg>
`;
fs.writeFileSync(process.argv[2], svg);
console.log('wrote', process.argv[2], `${W}x${H}`);
