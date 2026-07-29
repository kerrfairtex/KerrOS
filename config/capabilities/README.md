# Capability Manifests

YAML files in this directory are loaded at kernel boot by
`CapabilityRegistry.load_manifest_dir()`.

| File | Kind | Purpose |
|------|------|---------|
| `core_tools.yaml` | tool | Claw core + skills tools |
| `agents.yaml` | agent | Userspace agents |
| `devops_tools.yaml` | tool | Deploy pipeline (scope_gate DEPLOY_TOOLS) |
| `llm_providers.yaml` | provider | Groq/cloud/local LLM adapters |
| `omniroute.yaml` | provider | **Single** OmniRoute meta-provider |

## Schema

```yaml
version: 1
capabilities:
  - name: "kind:identifier"   # [a-z0-9_.:-]{2,80}
    kind: "tool|agent|provider|..."
    permissions: ["standard"|"elevated"|"deploy"]
    dependencies: ["env:FOO", "cli:bar", "port:llm"]
    setup_required: true|false
    setup_state: "ready"|"needs_setup"|"unknown"
    metadata: {}
```

CLI: `/capabilities` or `/capabilities provider`
