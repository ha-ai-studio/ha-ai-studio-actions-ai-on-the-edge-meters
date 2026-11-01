# Analog Meter Reader

An HA AI Studio Action for mechanical digits and decade dials, adapted from [jomjol/AI-on-the-edge-device](https://github.com/jomjol/AI-on-the-edge-device). It includes local model inference, image alignment, reading correction and a reference-image editor. Arbitrary pressure-gauge scales and the upstream ESP32 firmware/hardware services are not implemented.

## Develop the editor

The editable frontend sources are **TypeScript and SCSS** in `editor/src/`. Do not edit the generated `actions/analog-meter-reading/ui/editor.js` or `editor.css` directly.

```sh
cd editor
npm ci
npm run build
```

The build runs strict TypeScript checking, bundles the ES module and compiles SCSS. Generated assets are included in the Action package; Studio needs no Node.js toolchain at runtime. Python handles image processing and inference.

Studio's development Compose configuration mounts this repository read-only at `/local-actions`. Refresh the local source in Settings → Action repositories. Create an Analog Meter Reader, or save/discard changes, deactivate an existing instance and select **Reload from source**. Running instances remain pinned to their installed source. Identity, routes and request history are preserved.

## Configure and test

1. Upload a PNG/JPEG reference image. Studio stores images privately per Action, outside this repository.
2. Choose **Crop image** to show a frame with eight corner/edge grips immediately. Drag the grips to resize and drag inside to move the crop, or enter exact pixel bounds. The outside area is dimmed. Select **Apply crop** (Enter on the canvas) to confirm or **Cancel crop** (Escape) to discard. The same crop is applied after orientation to reference and input images. Keep a margin for alignment. **Reset crop** restores the full image; **Undo** restores the previous crop. Crops excluding existing regions are rejected. In **Select / move**, drag on empty image space to create unassigned frames. Select a frame and choose its type in **Region properties**. Delete the selected frame with the toolbar trash icon; **Undo** restores it. Create exactly two small, distinctive alignment regions around fixed visual features, away from moving digits and pointers.
3. Add a meter and draw one region per mechanical digit or decade dial. Under **Meters & values**, add a meter and build its value using **+ Add frame** pills from left to right. Type a comma after a frame or use the comma button; add further frames for decimal places. Each frame can belong to one value. Use the left-arrow and remove controls to adjust the sequence. Mechanical digits must precede analog dials for transition correction.
4. Drag inside frames to move them, resize from any of their four corners, or enter exact pixel coordinates. Clicks without dragging do not create frames. Crop, fit-area, Move view, rotate and Undo support setup. Move view shows magenta horizontal/vertical guides when the visible image area is centered, with a six-pixel snap range per axis. Replacing the reference clears the frames; Undo restores the prior configuration and image.
5. Configure the unit. The comma in the pill sequence determines decimal places automatically; without a comma, all selected frames form the integer value. Optional extended resolution and plausibility limits are under Reading checks. Counter-clockwise is configured per dial. Existing settings retain their behavior until the pill layout is edited. Unused frames do not participate in explicit value layouts.
6. Select **Run recognition** at the top of the image editor to test the loaded reference image with the current draft configuration. Inspect aligned images, crops, raw values and model fit. Preview uses uploaded images only and does not publish MQTT, activate the Action or update saved readings.
7. Save the configuration. Activate only after validating representative real meter images.

Synthetic tests verify the pipeline, not recognition accuracy on your meter. Model fit is not calibrated confidence. Lighting, framing, focus and transition positions require validation with real images. Unreadable or implausible readings return `null`; inspect `data.status` and each reading's reason rather than treating successful execution as successful recognition.

## Input

For normal execution, configure the exact allowed image URL and provide it in the request. Redirects, URL credentials and other URLs are rejected. Alternatively provide an existing private asset ID from this Action.

```json
{"request_id":"meter-001","data":{"image":{"url":"https://example.invalid/meter.jpg"},"previous":{"main":{"value":123.4,"elapsed_seconds":60}}}}
```

Home Assistant owns schedules, triggers and previous-reading history. The optional `previous` map enables decreasing-value, maximum-change and maximum-rate checks; no hidden previous value is persisted by this Action. Meter IDs are shown in the editor. Studio wraps the output in its standard result envelope.

## Runtime and verification

Supported runtime: Linux amd64, Python 3.12. Dependencies are pinned with hashes in `requirements.lock`. Two upstream models are bundled; revisions and hashes are recorded in `models/PROVENANCE.json`. Runtime limits include 8 MiB / 16 MP images, 32 regions, eight meters, 15 significant reading positions, Studio's 30-second runner timeout and 64 KiB output limit. Preview images expire after one hour. Discard unused test images to release private storage.

Run `python -m unittest discover -s tests -v` in an environment installed from the Action's dependency lock. Tests cover upstream correction vectors, alignment, actual model invocation with synthetic images, invalid images and plausibility rejection. Studio separately tests private storage and preview isolation. Trusted Python Actions and browser editors are not security sandboxes.

## License and attribution

This repository uses the unchanged **Dual Use License for AI-on-the-Edge Device**, version 1.0 (2025-01-05), in [LICENSE.md](LICENSE.md). Credit goes to **jomjol and all contributors**. This is an independent adaptation, not an official upstream release. See [THIRD_PARTY.md](THIRD_PARTY.md) for incorporated code and model provenance. HA AI Studio is a separate repository and retains its own license. Do not add private images, addresses or credentials to source control.

## Printed number blocks

Choose **Number block** in Region properties to read a complete printed digit sequence with one rectangle. Select the frame to set **Expected digits (optional)** (1–32) and **Expected value (optional)**. Add that frame as the only pill in a meter/value, without a comma. `value` and `raw_value` are strings for this type, preserving leading zeros; existing digit/dial readings remain numeric. Numeric previous-reading checks and extended resolution are not applicable. Remove any existing numeric checks when changing a value to a number block.

Recognition extends the original local watermeter App: estimate and normalize background illumination to reduce shadows, enlarge the crop (bounded to 2048 × 512), use two thresholds around the image-derived Otsu threshold, and run Tesseract in single-line digits-only mode. Illumination estimation is bounded to 1024 × 256 pixels. This improves dark and unevenly lit crops but cannot recover detail lost to blur, reflections or severe underexposure. Both variants must agree; optional length/comparison checks must pass. Agreement is not a calibrated confidence score. Failure returns an unreadable value with a reason, never the configured comparison value. OCR shares a 20-second budget across all blocks, with at most eight seconds per invocation.

The Studio container must include `tesseract-ocr` and English trained data; rebuild/update Studio as well as reloading the inactive Action source. Recognition runs locally without cloud services. Arbitrary text, decimal marks within a block, and combining blocks with individual digit/dial pills are not supported in this first version.

## Optional recognition quality checks

Under **Recognition settings** beside **Run recognition**, enable **Check frame stability** to evaluate each digit/dial at its original position and at ±2 pixels on both axes. Every variant must pass its type-specific fit threshold, stay within 0.25 digit positions of the original (circular distance), and produce the same complete value after upstream transition correction. Rejected frames are marked red with a reason after preview. Leave a two-pixel margin inside the image crop. Number blocks keep their separate two-threshold OCR check.

**Minimum digit fit** and **Minimum dial fit** are independent. Existing settings fall back to `recognition_threshold` (or 0.5). **Digit/Dial image preparation** offers original colors, auto contrast or grayscale plus auto contrast. These options are off by default for compatibility; compare representative real images before enabling them. Old dial-model thresholds are not automatically transferred to the current model.

**Require two matching captures** requires `confirmation_image` alongside `image` during execution. Both use the same `{ "asset_id": "…" }` or `{ "url": "…" }` format and existing image source restrictions. Home Assistant supplies distinct captures; the Action does not schedule or control a camera. URL inputs are fetched sequentially and must exactly match the configured source URL. Distinct uploaded assets provide explicit capture selection. Identical decoded images are rejected. Every value must agree exactly across both captures, otherwise that value is unreadable. Exact agreement can reject a moving meter. Different pixels alone are not proof of freshness; acquisition timing remains Home Assistant's responsibility.

Reference-only preview still shows region diagnostics when confirmation is required, but reports `unreadable` and `confirmation: "not_tested"`, with no confirmed numeric value. A request providing two images checks them even when the requirement is disabled. Preview never downloads remote images. The shared 20-second processing budget and Studio's 30-second runner timeout still apply; large sets of regions with all checks enabled may exceed them.

The optional per-meter **Rate tolerance** adds a fixed allowance to the rate-based maximum change: `abs(change) <= max_rate × elapsed_seconds / 60 + rate_tolerance`. Units are the configured meter units; a maximum rate must also be configured. Existing maximum-change and decreasing-reading checks continue to apply independently. No private images, captured values or schedules are stored by these checks.

## Straightening with a reference line

Select **Straighten image** beside **Rotate 90°**, then drag between two points that should be level. Releasing applies the smallest correction to make the line horizontal, regardless of drawing direction. Short gestures are ignored; Escape cancels. The inspector shows the saved angle and offers **Reset straightening**.

`straighten_angle` stores a clockwise angle in degrees. Processing order is EXIF orientation, quarter-turn rotation, straightening, crop, two-anchor alignment, then recognition. The same correction is applied to reference, request and confirmation images. Output dimensions stay fixed; regions that overlap empty rotated corners are rejected, including matched alignment anchors and shifted stability samples.

Existing regions and crop follow the rotation as enclosing axis-aligned rectangles. Inspect their bounds afterward: repeated corrections or Reset can enlarge these rectangles. Undo restores the exact prior settings. A correction moving a region outside the image is rejected without changing the draft. For best results, straighten before drawing reading regions. Original uploaded image bytes remain unchanged.

## Multiple reference images

Use **Add reference image** in the toolbar. Once there is more than one image, Previous/Next and an image counter appear. Up to 16 distinct images are saved in the gallery; the selected image remains the active `reference` for recognition and execution after saving. Existing single-image configurations work unchanged.

All images share one set of frames, meter layouts, crop, quarter rotation and straightening. Additional images must have the same dimensions after orientation normalization; uploading one never clears the shared settings. Browsing and adding images preserve the current editor zoom and pan, which remain view-only and are not saved. Old recognition results are cleared when the selected image changes. Apply or cancel a pending crop before changing images. Use images from the same camera framing; image switching does not independently recalibrate each image.

### Recognition image report

Preview shows reading values and JPG report download links instead of an image gallery. The private report captures input, rotation, straightening, crop, alignment scores, reference crops, reading crops, model inputs and fit thresholds (including enabled stability offsets), and number-block illumination correction and OCR thresholds. Region decisions and final corrected values include rejection reasons and confirmation state. Large reports are split into numbered image pages within Studio's preview image limits. Reports use the existing private, temporary preview storage and are never published to MQTT. Errors that abort processing before a result is produced still appear as a diagnostic message rather than a completed report.

Value mapping uses one table row per value (name, frame sequence and actions). **Add value** creates a row; **Rules** expands grouped reading direction, change limit and rate/tolerance settings. Standard frame names are displayed as F1, F2, etc.; custom names and frame IDs are preserved. Sequences stay on one line, with horizontal scrolling on narrow screens.

Explicit value layouts determine all output positions. Saved `extended_resolution` flags are ignored for these layouts; the editor no longer offers that option. Legacy configurations without a layout retain compatibility behavior.

Editor settings are grouped by task: select an alignment reference to edit the shared search radius and match threshold in its inspector. **Recognition settings** beside Run recognition contains quality, preparation, stability and confirmation. **Test options** contains temporary previous-reading JSON and value IDs. Execution image URLs come directly from `image.url` in the request; reference uploads stay in the toolbar.

Image execution requests do not require a separately configured URL allowlist. Legacy `image_url` settings are ignored. HTTP(S), no embedded credentials, no redirects, bounded downloads and preview network isolation remain enforced.

### Automatic camera acquisition

In **Camera settings**, Use Studio's entity picker for a camera and optional `light.*` or `switch.*` illumination. Configure wait-before-capture (0–20 seconds), one/two images, and inter-image delay (0–20 seconds). Send `{"request_id":"meter-read-001","data":{}}` to request a fresh reading. Supplied `image` requests still bypass acquisition. Both captured images must produce the same value; identical decoded images are rejected as independent confirmation. Selecting **Require two matching captures** forces two images for acquisition.

The Action turns on illumination only when it was off, waits, obtains camera images via HA, restores the original off state, then runs recognition. Already-on lights are not modified. Studio keeps a private restoration journal and retries after failures or restart; restoration cannot happen while HA/Studio is offline. Entity access is limited to the execution's configured IDs. Uploaded reference-image previews never receive the device client and never switch illumination. No vendor-specific camera URL, script or HA token is needed in the Action settings.

**Capture & recognize** in the image toolbar runs the configured camera/illumination acquisition using draft settings, including two-image confirmation. This explicitly controls real devices. The aligned camera image, values and diagnostic report appear below the editor without replacing reference images, publishing MQTT or updating saved readings. **Run recognition** remains reference-only.

Enable **Discard first camera image** for cameras that initially return a stale or dark frame. After the initial illumination delay, the Action fetches and discards one warm-up image, waits the configured inter-image delay, then acquires the selected one or two images. This applies to reference capture and automatic recognition. It is disabled by default and does not guarantee image freshness or brightness. Capture failures still fail the run and restore illumination.

## Release packages

Generated JS and CSS are build outputs and are not tracked in Git. Build locally
before refreshing a local development source. Production installation uses the
built GitHub Release asset, rather than the source archive or a Git branch.

In Studio Settings → Action repositories, choose **GitHub Release**, enter this
repository's public HTTPS URL and use `latest` (latest published stable release)
or an explicit stable release tag. Refresh updates the creation catalog only;
existing Actions remain pinned to their installed snapshot, including after restart.

To prepare a release, set `actions/analog-meter-reading/action.json` to the desired
version, commit the sources and push the matching `v<version>` tag. The release
workflow installs locked editor dependencies, runs editor tests and the build,
checks packaging, and publishes `ha-ai-studio-actions.zip` with
`ha-ai-studio-actions.zip.sha256`. Tags containing a hyphen publish prereleases,
which Studio does not install. PRs and manual workflow runs validate and upload a
CI artifact without publishing a release. A release is published only after all
build checks pass. Existing release assets are never overwritten by this workflow.

The archive preserves `actions/analog-meter-reading/`, includes the Python runtime,
models, notices, manifest, lockfile and compiled editor, and uses an explicit file
allowlist. Add new runtime files to `scripts/package_release.py`. Never add private
images, settings, credentials or development data to that allowlist.

### AI release notes

Maintain a non-empty `## <version>` section in `CHANGELOG.md` for every release,
matching the Action manifest and tag. Tagged releases generate an English AI
summary and highlights using the organization's `OPENAI_API_KEY` Actions secret;
its repository access policy must include this repository. Optionally set the
`OPENAI_RELEASE_MODEL` Actions variable (default: `gpt-4o-mini`). The key is only
provided to the release-notes step, never PR builds or the distributed Action.

Only the versioned changelog and bounded commit subjects are sent to the API,
with response storage disabled. The maintained changelog and installation notes
are always included. Missing credentials, API failures or invalid AI output fall
back to the changelog with a generic workflow notice; missing release changelog
entries fail publication. PR checks test generation with mocked API responses.

## Leak detection

The repository also includes [Leak detection](actions/water-leak-detection/README.md), an independent Action that assesses the Home Assistant history of a cumulative water sensor. It exposes an Execute function and status/reason readings. It requires Studio sensor-history support and uses deterministic local analysis without an external AI service.

## Device template

`device_templates/watermeter-serial-reading-flowrate.json` provides a **Digital
Watermeter** Device with serial number, cumulative reading in m³, derived flow
rate in L/min and a Read Now function. The measurement interval is 15 minutes.

In HA AI Studio, refresh this repository, choose **Create Device**, select the
template below the Device name and assign your meter-reading Action. The template
references reading IDs `meter-5e9d7126` (serial number) and `meter-c2a19895`
(cumulative reading). Match these to the meter IDs in your Action, or edit the
Device reading IDs before activation. The derived flow rate uses the cumulative
reading and converts m³/min to L/min with factor 1000.

New Devices are inactive and unpublished. The template is included in Git/local
sources and release ZIPs; it contains no images, credentials or measured values.

### Water meter with leak checks

`device_templates/watermeter-serial-reading-flowrate-leaks.json` adds a
**Leak Detection** text sensor and a **Check for Leaks** Execute function to the
water-meter template. It contains four sensors and two functions, with a
15-minute measurement interval and publication disabled. Assign `action-1` to
your meter-reading Action and `action-2` to a separate **Leak detection** Action.
The `leak-status` reading matches that Action's output; its values are `normal`,
`suspected_leak` and `insufficient_data`.

Configure the Leak detection Action's cumulative Home Assistant sensor entity
and history settings separately. Use the cumulative water reading, not the flow
rate or serial-number sensor. A newly created, unpublished Device has no Home
Assistant history of its own; publish the intended sensor and allow enough
Recorder history to accumulate, or select an existing cumulative sensor. See
the [Leak detection requirements](actions/water-leak-detection/README.md).

Read Now updates only meter-reading sensors; Check for Leaks updates only the
leak sensor. Scheduled measurements include both Actions independently. The
leak check reads Home Assistant history, not the instantaneous flow-rate value,
and this template does not configure notifications or follow-up actions.
