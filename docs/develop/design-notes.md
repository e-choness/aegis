# Design notes

Decisions we've deferred on purpose, with enough context to pick them up
later. Each note says what would make it worth revisiting.

## Restore masked values at the server edge

*Recorded 2026-09-27 · status: deferred*

**Today.** Masked values are restored inside the pipeline: the PII and
content packs each put an unmask step in egress (`pii.redact` →
`pii.unmask`). Egress checks listed before the unmask step see placeholders;
anything after it sees the real values. Routes can keep placeholders with
`unmask_response: false`.

**The alternative.** The pipeline would never restore anything: its final
state keeps the masked reply, and the server restores values only while
writing the HTTP response to the client.

| | Restore in egress (today) | Restore at the edge |
|---|---|---|
| Egress checks | see placeholders only if listed before the unmask step | always see placeholders |
| Events, traces, exporters | hold whatever egress nodes put in them | masked by construction |
| A future "store responses" feature | must remember to store the masked text | safe by default |
| Python API (`executor.run`) | returns the restored reply | returns the masked reply; callers restore with a helper |
| True streaming | unchanged (these egress steps already buffer) | must restore placeholders split across chunks |
| Plugins | unchanged | egress plugins that expect real text break |

**Why not now.** It changes what `executor.run()` returns and what egress
plugins see — a breaking change for anyone embedding Aegis — to protect
against mistakes the current ordering already lets a config avoid.

**Revisit when** replies need to be stored or exported in full, a compliance
review asks for "no personal data in any Aegis-held record by construction",
or egress plugins that call external services become common.
