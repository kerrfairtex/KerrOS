# Capability Manifests

YAML files in this directory are loaded at kernel boot by
`CapabilityRegistry.load_manifest_dir()`.

| File | Kind | Purpose |
|------|------|---------|
| `core_tools.yaml` | tool | Full claw TOOL_DEFINITIONS set (FS + exec + skills) |
| `router_tools.yaml` | tool | scope_policy offensive tools + key passive router tools |
| `devops_tools.yaml` | tool | Deploy pipeline + DevOpsAgent extras |
| `agents.yaml` | agent | Userspace agents (+ DevOpsAgent) |
| `llm_providers.yaml` | provider | Composite + multi_api chain + local adapters |
| `omniroute.yaml` | provider | **Single** OmniRoute meta-provider |
| `ports.yaml` | port | Kernel DI ports (llm/memory/tool/…) |
| `adaptive_integrations.yaml` | integration | Soft catalog / coding tiers (ADR-055) |

## Schema

```yaml
version: 1
capabilities:
  - name: "kind:identifier"   # [a-z0-9_.:-]{2,80}
    kind: "tool|agent|provider|port|..."
    permissions: ["standard"|"elevated"|"deploy"]
    dependencies: ["env:FOO", "cli:bar", "port:llm"]
    setup_required: true|false
    setup_state: "ready"|"needs_setup"|"unknown"
    metadata: {}
```

CLI: `/capabilities` or `/capabilities provider`  
Integrations catalog: `/integrations` / `/integrations coding` (ADR-055)

## Generated docs

```bash
python3 scripts/render_capabilities.py          # writes docs/CAPABILITIES.md
python3 scripts/render_capabilities.py --check  # CI drift check
```

Or in chat: `/capabilities export`
