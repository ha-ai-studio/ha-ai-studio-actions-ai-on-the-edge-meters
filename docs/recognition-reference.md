# Recognition and runtime reference

[Back to the getting-started guide](../README.md)

## Input

For execution with an explicit image, provide an HTTP(S) URL in the request, or an existing private asset ID from this Action. No URL allowlist is required; legacy `image_url` settings are ignored. Redirects and embedded URL credentials are rejected. Omit `image` to use configured Home Assistant camera acquisition.

```json
{"request_id":"meter-001","data":{"image":{"url":"https://example.invalid/meter.jpg"},"previous":{"main":{"value":123.4,"elapsed_seconds":60}}}}
```

Studio schedules independent measurements for explicitly configured Devices. Home Assistant owns automation triggers, conditions and follow-up actions. The caller supplies previous-reading history when using the checks below. The optional `previous` map enables decreasing-value, maximum-change and maximum-rate checks; no hidden previous value is persisted by this Action. Meter IDs are shown in the editor. Studio wraps the output in its standard result envelope.

## Runtime and verification

Supported runtime: Linux amd64, Python 3.12. Dependencies are pinned with hashes in `requirements.lock`. Two upstream models are bundled; revisions and hashes are recorded in [`models/PROVENANCE.json`](../actions/analog-meter-reading/models/PROVENANCE.json). Runtime limits include 8 MiB / 16 MP images, 32 regions, eight meters, 15 significant reading positions, Studio's 30-second runner timeout and 64 KiB output limit. Preview images expire after one hour. Discard unused test images to release private storage.

Run `python -m unittest discover -s tests -v` in an environment installed from the Action's dependency lock. Tests cover upstream correction vectors, alignment, actual model invocation with synthetic images, invalid images and plausibility rejection. Studio separately tests private storage and preview isolation. Trusted Python Actions and browser editors are not security sandboxes.

## Printed number blocks

Choose **Number block** in Region properties to read a complete printed digit sequence with one rectangle. Select the frame to set **Expected digits (optional)** (1–32) and **Expected value (optional)**. Add that frame as the only pill in a meter/value, without a comma. `value` and `raw_value` are strings for this type, preserving leading zeros; existing digit/dial readings remain numeric. Numeric previous-reading checks and extended resolution are not applicable. Remove any existing numeric checks when changing a value to a number block.

Recognition extends the original local watermeter App: estimate and normalize background illumination to reduce shadows, enlarge the crop (bounded to 2048 × 512), use two thresholds around the image-derived Otsu threshold, and run Tesseract in single-line digits-only mode. Illumination estimation is bounded to 1024 × 256 pixels. This improves dark and unevenly lit crops but cannot recover detail lost to blur, reflections or severe underexposure. Both variants must agree; optional length/comparison checks must pass. Agreement is not a calibrated confidence score. Failure returns an unreadable value with a reason, never the configured comparison value. OCR shares a 20-second budget across all blocks, with at most eight seconds per invocation.

The Studio container build includes `tesseract-ocr` and English trained data; no separate OCR installation is needed. If an older container reports missing OCR, rebuild/update Studio as well as reloading the inactive Action source. Recognition runs locally without cloud services. Arbitrary text, decimal marks within a block, and combining blocks with individual digit/dial pills are not supported in this first version.

## Optional recognition quality checks

Under **Recognition settings** beside **Run recognition**, enable **Check frame stability** to evaluate each digit/dial at its original position and at ±2 pixels on both axes. Every variant must pass its type-specific fit threshold, stay within 0.25 digit positions of the original (circular distance), and produce the same complete value after upstream transition correction. Rejected frames are marked red with a reason after preview. Leave a two-pixel margin inside the image crop. Number blocks keep their separate two-threshold OCR check.

**Minimum digit fit** and **Minimum dial fit** are independent. Existing settings fall back to `recognition_threshold` (or 0.5). **Digit/Dial image preparation** offers original colors, auto contrast or grayscale plus auto contrast. These options are off by default for compatibility; compare representative real images before enabling them. Old dial-model thresholds are not automatically transferred to the current model.

**Require two matching captures** requires `confirmation_image` alongside `image` during execution. Both use the same `{ "asset_id": "…" }` or `{ "url": "…" }` format and the same image source restrictions. For explicit image requests, the caller supplies distinct captures. URL inputs are fetched sequentially; they do not require a configured source URL. Alternatively, configure automatic camera acquisition below. Distinct uploaded assets provide explicit capture selection. Identical decoded images are rejected. Every value must agree exactly across both captures, otherwise that value is unreadable. Exact agreement can reject a moving meter. Different pixels alone are not proof of freshness; acquisition timing remains Home Assistant's responsibility.

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

In **Camera settings**, use Studio's entity picker for a camera and optional `light.*` or `switch.*` illumination. Configure wait-before-capture (0–20 seconds), one/two images, and inter-image delay (0–20 seconds). Send `{"request_id":"meter-read-001","data":{}}` to request a fresh reading. Supplied `image` requests still bypass acquisition. Both captured images must produce the same value; identical decoded images are rejected as independent confirmation. Selecting **Require two matching captures** forces two images for acquisition.

The Action turns on illumination only when it was off, waits, obtains camera images via HA, restores the original off state, then runs recognition. Already-on lights are not modified. Studio keeps a private restoration journal and retries after failures or restart; restoration cannot happen while HA/Studio is offline. Entity access is limited to the execution's configured IDs. Uploaded reference-image previews never receive the device client and never switch illumination. No vendor-specific camera URL, script or HA token is needed in the Action settings.

**Capture & recognize** in the image toolbar runs the configured camera/illumination acquisition using draft settings, including two-image confirmation. This explicitly controls real devices. The aligned camera image, values and diagnostic report appear below the editor without replacing reference images, publishing MQTT or updating saved readings. **Run recognition** remains reference-only.

Enable **Discard first camera image** for cameras that initially return a stale or dark frame. After the initial illumination delay, the Action fetches and discards one warm-up image, waits the configured inter-image delay, then acquires the selected one or two images. This applies to reference capture and automatic recognition. It is disabled by default and does not guarantee image freshness or brightness. Capture failures still fail the run and restore illumination.
