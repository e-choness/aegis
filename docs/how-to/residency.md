# How-to: Residency enforcement

The residency pack ensures that governed requests only reach providers
declared compliant for the required region. See the
[residency model explanation](../explanation/residency-model.md) for the
underlying design philosophy.

## Decision flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'background': 'transparent', 'primaryColor': '#3f51b5', 'primaryTextColor': '#ffffff', 'primaryBorderColor': '#283593', 'lineColor': '#7986cb', 'secondaryColor': '#3949ab', 'tertiaryColor': '#5c6bc0', 'clusterBkg': '#e8eaf6', 'clusterBorder': '#7986cb', 'edgeLabelBackground': '#e8eaf6', 'titleColor': '#1a237e', 'nodeTextColor': '#ffffff'}}}%%
flowchart TD
    REQ([Request]) --> POLICY{residency policy active?}
    POLICY -- no --> PASS([allow — any provider])
    POLICY -- yes --> FILTER[Filter provider set by declared region]
    FILTER --> NONE{any compliant provider?}
    NONE -- no --> BLOCK([block + audit — no compliant route])
    NONE -- yes --> CHECK{endpoint region encodes region?}
    CHECK -- mismatch --> LINT([aegis policy lint flags mismatch])
    CHECK -- consistent --> SELECT([select provider + audit declared region])
```

## Configure

Declare residency on every provider profile:

```yaml
providers:
  eu_main:
    type: openai_compatible
    base_url: https://eu-west.api.example.com/v1
    api_key: secret://env/EU_API_KEY
    residency:
      region: eu-west
      jurisdiction: GDPR
      source_url: https://example.com/privacy/eu

routes:
  default:
    provider: eu_main
```

To activate fail-closed routing, add the residency pack to ingress:

```yaml
guardrails:
  residency:
    pack: aegis.residency

pipeline:
  ingress: [residency]
```

## Lint endpoint validation

```bash
aegis policy lint
```

For Azure OpenAI, Bedrock, Vertex, and OpenAI regional endpoints, Aegis
parses the declared region from the URL and flags any mismatch with the
`residency.region` field. This is the only verifiable signal — see the
[residency model](../explanation/residency-model.md) for why.

## Runtime audit

Every request records the declared region of the selected provider in the
audit log. Query with:

```bash
curl "http://localhost:8000/v1/audit?route=default"
```

## Network enforcement

Hard enforcement lives at the network layer. Pair the residency pack with
egress allowlisting at your gateway or DNS. Aegis enforces policy faithfully
inside the boundary it can see.
