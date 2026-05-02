# Configuration

Wizard reads its configuration from `~/.wizard/config.json`. The file is created with defaults by `wizard setup`. All fields are optional — if you don't set something, wizard uses a sensible default.

To use a different config file location, set the `WIZARD_CONFIG_FILE` environment variable to an absolute path.

## Common recipes

### Enable synthesis with a local Ollama model

Synthesis is enabled by default, but it needs a running LLM to do anything. The easiest setup is a local [Ollama](https://ollama.com/) instance:

```json
{
  "synthesis": {
    "enabled": true,
    "model": "ollama/gemma4:latest-64k",
    "base_url": "http://localhost:11434"
  }
}
```

The model string must include the provider prefix (`ollama/`). Wizard uses this to route the request correctly.

### Add a synthesis fallback backend

If you have more than one LLM available, you can define a priority-ordered list of backends. Wizard tries each in order and uses the first one that responds to a health check:

```json
{
  "synthesis": {
    "enabled": true,
    "model": "ollama/gemma4:latest-64k",
    "base_url": "http://localhost:11434",
    "backends": [
      {
        "model": "ollama/gemma4:latest-64k",
        "base_url": "http://localhost:11434",
        "description": "Local Ollama (primary)"
      },
      {
        "model": "openai/gpt-4o-mini",
        "api_key": "sk-...",
        "description": "OpenAI fallback"
      }
    ]
  }
}
```

Use `wizard configure synthesis` to manage backends interactively instead of editing JSON by hand.

### Disable PII scrubbing

Wizard scrubs personal data from everything it writes to the database. To disable this entirely:

```json
{
  "scrubbing": {
    "enabled": false
  }
}
```

See [pii-scrubbing.md](pii-scrubbing.md) for what gets scrubbed and why you might want to allow specific values through instead of disabling scrubbing completely.

### Allow specific values through the scrubber

If wizard is replacing something it shouldn't — your company name, a product name, a colleague's handle — add a Python regex to the allowlist:

```json
{
  "scrubbing": {
    "enabled": true,
    "allowlist": ["Acme Corp", "ProductName", "Dr\\.? Smith"]
  }
}
```

Each entry is a Python regex matched against the original text before scrubbing. Matching spans are left untouched.

### Enable Sentry telemetry

Wizard can report errors to a Sentry project. This is off by default:

```json
{
  "sentry": {
    "enabled": true,
    "dsn": "https://...@sentry.io/..."
  }
}
```

## Full field reference

| Field | Default | Description |
|---|---|---|
| `synthesis.enabled` | `true` | Whether to run LLM synthesis at session end and mid-session |
| `synthesis.model` | `"ollama/gemma4:latest-64k"` | LiteLLM model string; must include provider prefix |
| `synthesis.base_url` | `"http://localhost:11434"` | Base URL for local LLM backends |
| `synthesis.api_key` | `""` | API key for cloud models |
| `synthesis.context_chars` | `200000` | Max characters to send per synthesis chunk; increase for larger local models |
| `synthesis.backends` | `[]` | Ordered list of fallback backends; first healthy one wins |
| `scrubbing.enabled` | `true` | Whether to scrub PII before writing to the database |
| `scrubbing.allowlist` | `[]` | Python regexes for values that should pass through unscrubbed |
| `sentry.enabled` | `false` | Whether to send error reports to Sentry |
| `sentry.dsn` | `""` | Your Sentry DSN |
| `modes.default` | `null` | Default skill mode for new sessions |
| `modes.allowed` | `["architect", "ideation", "product-owner", "caveman"]` | Which modes are available |
