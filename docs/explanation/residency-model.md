# The residency model: declared, verified where possible, fail-closed

An honest statement first: **you cannot reliably detect where inference
happens.** Geolocating an API endpoint finds the nearest edge node, not the
GPUs; providers route internally however they want. Any product claiming to
"detect" processing location is overclaiming. Aegis instead enforces what is
declared, verifies what is verifiable, and says exactly which is which.

## Four layers

1. **Declared metadata.** Every provider profile carries
   `residency: {region, jurisdiction, source_url}`, sourced from the
   provider's own documentation. Unset means `unknown`.
2. **Endpoint validation.** Some providers encode region verifiably in the
   endpoint itself — Azure OpenAI hostnames, Bedrock regions, Vertex
   locations, OpenAI's regional endpoints. `aegis policy lint` parses these
   and flags any mismatch between declared and endpoint-encoded region. This
   is the only verifiable signal, so it is used everywhere it exists.
3. **Fail-closed routing.** With a residency policy active, the router filters
   the candidate set before selection. `unknown` is treated as non-compliant.
   A blocked route is an auditable event, never a silent fallback.
4. **Advisory runtime checks.** Optional DNS/IP geolocation of endpoints is
   reported as telemetry labeled *advisory only — not proof of processing
   location*. Per-request audit records the declared region actually used.

## The last line is not application code

Hard enforcement of "data never leaves jurisdiction X" ultimately lives at the
network layer. Deployments with strict requirements should pair the residency
pack with egress allowlisting at their gateway or DNS — the deployment guide
shows how. Aegis enforces policy faithfully inside the boundary it can see and
is explicit about where that boundary ends.
