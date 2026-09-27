# aegis.yaml

One file configures a gateway. It is parsed by `aegis_core.config.load_config`
in four steps: **YAML → `secret://` resolution → `AEGIS__*` env overrides →
Pydantic validation**. Top-level keys other than the six below are
rejected, so typos surface as errors.

```bash
aegis config validate aegis.yaml   # schema + cross-reference checks
aegis config show aegis.yaml       # resolved config, secrets **REDACTED**
aegis policy lint aegis.yaml       # packs installed? refs valid? streaming downgrades?
```

## Complete example

```yaml
providers:
  primary:
    type: openai_compatible
    base_url: https://api.example.com/v1
    model: example-large
    api_key: secret://env/EXAMPLE_API_KEY#value
    residency:
      region: ca-central-1
      jurisdiction: CA
      source_url: https://example.com/trust/residency
  dev:
    type: fake
    complete_response: "[dev] canned reply"

guardrails:
  pii:
    pack: aegis.pii
    mode: mask
  classify:
    pack: aegis.classification
  budget:
    pack: aegis.budgets
    default_cap: 50.0

pipeline:
  ingress: [budget, classify, pii]
  egress: [pii]

routes:
  default:
    provider: primary
    owner: platform@example.com
    risk_rating: medium
    review_interval_days: 365
  sandbox:
    provider: dev
    pipeline:
      ingress: [pii]
      egress: [pii]

auth:
  type: api_key
```

## `providers`

Map of name → provider profile. Extra keys are allowed and passed through.

| Field | Type | Notes |
|---|---|---|
| `type` | string, **required** | `fake`, `anthropic`, `openai_compatible`, or the name of an installed `aegis.providers` plugin. |
| `api_key` | secret | Use a `secret://` URI. Stored as `SecretStr`. |
| `base_url` | string | Endpoint; required for `openai_compatible`. |
| `model` | string | Required for `anthropic` and `openai_compatible`. For `anthropic`, a LiteLLM model string such as `anthropic/claude-sonnet-5`. |
| `residency` | `{region, jurisdiction?, source_url?}` | Declared location of the endpoint. |
| `complete_response` | string | `fake` only — the canned reply. |
| `cost_per_request` | float | `fake` only — cost reported for each completion, so [budgets](/packs/budgets) can be exercised. Default `0`. |
| `tool_calls` | list of turns | `fake` only — tool calls to request, one list per turn (`[[{name: search, arguments: {q: x}}], …]`). Turn *N* is used once the conversation holds *N* tool results; then `complete_response`. See [route `tools`](#routes). |

## `guardrails`

Map of name → pack instance. The name is what you list in `pipeline`.
Extra keys are passed to the pack's factory.

| Field | Type | Notes |
|---|---|---|
| `pack` | string, **required** | An `aegis.packs` entry point, e.g. `aegis.pii`. |
| `mode` | string | Pack-specific (`aegis.pii`: `mask` \| `detect`). |
| `threshold` | float | Pack-specific (`aegis.pii`, `aegis.content`). |
| *other* | any | See each [pack's page](/packs/). |

## `pipeline`

The default stage lists for every route. Each entry must name a guardrail
declared above (a dotted suffix such as `pii.unmask` is allowed).

| Field | Type | Notes |
|---|---|---|
| `ingress` | list | Runs before the provider call. |
| `egress` | list | Runs on the response. |
| `tool_call` | list | Reserved — `aegis serve` refuses to start if set (`AEG-POL-004`). Govern tools with a route's `tools` and `tool_guards`. |
| `tool_result` | list | Reserved — as `tool_call`. |

## `routes`

Map of route name → route. Clients select a route with `route` (native API)
or `model` (OpenAI-compatible API). Extra keys are allowed.

| Field | Type | Notes |
|---|---|---|
| `provider` | string, **required** | Must name a declared provider. |
| `model` | string | Model override for this route. |
| `pipeline` | pipeline object | Replaces the top-level `pipeline` for this route. |
| `owner` | string | Recorded in the ledger's `model_inventory`. |
| `risk_rating` | `low` \| `medium` \| `high` | Recorded in `model_inventory`. |
| `review_interval_days` | int | Sets the inventory's next review date. |
| `tools` | map of name → tool | Tools the model may call on this route; declaring any turns on the [governed tool loop](/guide/tool-governance#tools-in-aegis-yaml). |
| `showcase` | map | Puts the route on a tab of the `/showcase` page: `tab`, `title`, `order`, `blurb`, `label`, `presets` (list of `{label, prompt}`). See [Public demos](/guide/deployment#public-demos). |
| `tool_guards` | list | Built-in tool guards: `exfiltration` (blocks masked PII in tool arguments), `injection` (blocks tool results carrying instructions). |

Each entry under `tools`:

| Field | Type | Notes |
|---|---|---|
| `description` | string | What the model is told the tool does. |
| `result` | string | What calling the tool returns — a static stand-in for a tool server. |
| `parameters` | JSON Schema | The tool's arguments. Default: an object with no declared properties. |
| `require_approval` | bool | Pause the run for a reviewer before the call; approving runs the call and continues. |
| `deny` | bool | Any call to the tool blocks the run. |

## `auth`

| Field | Type | Notes |
|---|---|---|
| `type` | `none` \| `api_key` | Default `none`. `aegis serve` itself uses API-key auth unless started with `--no-auth`. |

## `exporters`

Map of name → destination for evidence-ledger records. Extra keys are passed
to the exporter.

| Field | Type | Notes |
|---|---|---|
| `type` | string, **required** | `jsonl`, `webhook`, or an installed `aegis.exporters` plugin. |
| `path` | string | `jsonl`: file to append to. |
| `url`, `headers`, `timeout` | | `webhook`: endpoint, extra headers (may be `secret://` refs), seconds (default 10). |

See [Forward evidence to other systems](/guide/audit#forward-evidence-to-other-systems).

## Secret references

```text
secret://<backend>/<path>#<key>
```

The `#<key>` fragment is **required**. `aegis serve` resolves the `env`
backend (`<path>` is the variable name; `<key>` is ignored). Unresolvable
references fail start-up with `AEG-CFG-010`; unknown backends with
`AEG-CFG-011`.

## Environment overrides

`AEGIS__<SECTION>__<KEY>=value` overrides nested keys after secrets are
resolved:

```bash
AEGIS__ROUTES__DEFAULT__MODEL=example-small aegis serve
```

## Config digest

`config_digest(cfg)` is a SHA-256 over the canonical JSON of the config with
secrets redacted. It is exposed at `/v1/health`, shown by `aegis explain`,
and stamped on every ledger record as `model_version`.
