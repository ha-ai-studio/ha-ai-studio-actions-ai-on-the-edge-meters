## 0.4.1

- Add Digital Watermeter Device templates with serial number, cumulative reading and derived flow rate, with an optional leak-status sensor and separate Execute function.
- Include both templates in release ZIPs through an explicit file allowlist.
- Document Action assignments, reading IDs and Home Assistant history requirements; imported Devices remain inactive and unpublished.

## 0.4.0

- Add Leak detection as an independent Action using cumulative water sensor history from Home Assistant.
- Provide configurable consumption thresholds, interval coverage checks, status and reason readings, and an Execute function.
- Use the shared sensor entity picker and numeric defaults in HA AI Studio 0.0.19 or newer.
- Include both Actions in the release ZIP with explicit file allowlists. History analysis is deterministic and local; no external AI provider is used.

## 0.3.2

- Generate English AI release summaries using the organization secret, with the maintained changelog as fallback.

## 0.3.1

- Build and test the configuration editor in CI for tagged releases.
- Publish a ready-to-install Action ZIP and SHA256 checksum for HA AI Studio release sources.
- Exclude generated JavaScript and CSS from Git while preserving local editor builds.
