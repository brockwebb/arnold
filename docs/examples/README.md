# Examples

Reusable patterns, automation templates, and analyzed use cases for Arnold.

## Contents

| File | Description |
|------|-------------|
| [macos-launchagent-sync.md](./macos-launchagent-sync.md) | Automated daily data sync using macOS LaunchAgents |

## HRR Use Cases

Documented edge cases showing how quality gates handle real-world recovery patterns.

| File | Pattern | Outcome |
|------|---------|---------|
| [hrr-use-case-activity-resumed.md](./hrr-use-case-activity-resumed.md) | Activity resumed mid-recovery (S23:I9) | Correctly rejected via `r2_30_60` |

## Contributing Examples

When adding examples:
1. **No PII or credentials** — Use placeholders like `/path/to/arnold`
2. **Document all options** — Explain configuration choices
3. **Include troubleshooting** — Common issues and fixes
4. **Security notes** — Warn about credential handling
