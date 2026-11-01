# Leak detection

Requires HA AI Studio 0.0.19 or newer for sensor history, entity search and numeric draft defaults.

Mount the repository root read-only through `LOCAL_ACTIONS_DIR` and set
`HA_AI_STUDIO_LOCAL_ACTIONS=/local-actions` on the development server. Add a
**Local directory** source in Settings with path `.` and refresh it. Create an
Action of type **Leak detection**. Studio uses an immutable snapshot and its own
per-instance runner. These sources are not automatically installed or activated.

Configure the cumulative water meter `sensor.*` entity, history period (1–168
hours), minimum interval consumption in L/h, minimum suspicion duration, and
maximum allowed gap between recorded readings. The sensor must use L or m³ and
state class `total` or `total_increasing`. The existing private server-owned HA
connection supplies authentication; never put a token in Action settings.

On the existing Device, add Action-backed text sensors with reading IDs
`leak-status` and optionally `leak-reason`. Add an Execute function named
**Check for leaks** bound to this Action. Functions update only this Action's
sensors without changing the Device's measurement schedule. An Action-backed
sensor also participates in scheduled Device measurements.

The status is `normal`, `suspected_leak`, or `insufficient_data`. This is a
transparent deterministic interval-pattern assessment, not a trained AI model.
Three or more consecutive intervals must exceed the configured rate for the
minimum duration to raise suspicion. Missing, stale, nonnumeric, out-of-order,
reset, or unit-changing data makes the entire assessment insufficient. API
failures also return insufficient data; unexpected execution failures retain
Studio's existing unavailable behavior. No notification or valve operation runs.

Home Assistant history records state changes, not necessarily every measurement.
Unchanged readings may not be recorded. Sparse history is deliberately not
interpreted as zero consumption; choose the gap limit for the sensor's actual
recording behavior. The synthetic initial history state is excluded. This
conservative approach may return insufficient data for a quiet meter. Recorder
retention limits the available history; long-term statistics are not queried.
Interval averages cannot prove uninterrupted flow, and a normal result cannot
rule out a leak. Notifications and follow-up actions belong in Home Assistant.

History access is limited to configured sensor entities and seven days, with at
most 10000 records and bounded response sizes. Arbitrary HA attributes and
credentials are never forwarded to the Action. History is processed locally and
is not written to public files or sent to a model provider.
