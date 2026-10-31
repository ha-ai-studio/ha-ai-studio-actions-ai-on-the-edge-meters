// src/references.ts
function referenceImages(settings) {
	const images = [...settings.references ?? []];
	if (settings.reference && !images.some((r) => r.asset_id === settings.reference.asset_id)) images.unshift(settings.reference);
	return images.filter((r, i) => images.findIndex((other) => other.asset_id === r.asset_id) === i);
}
function addReference(settings, image) {
	const images = referenceImages(settings);
	if (images.some((r) => r.width !== image.width || r.height !== image.height)) throw new Error("Additional reference images must have the same dimensions to preserve frames and crop.");
	if (images.some((r) => r.asset_id === image.asset_id)) return images;
	if (images.length >= 16) throw new Error("Use at most 16 reference images.");
	return [...images, image];
}
// src/straighten.ts
function lineCorrection(a, b) {
	let angle = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
	if (angle > 90) angle -= 180;
	if (angle < -90) angle += 180;
	return -angle;
}
function rotateBounds(r, width, height, degrees) {
	const angle = degrees * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
	const points = [
		[r.x, r.y],
		[r.x + r.width, r.y],
		[r.x, r.y + r.height],
		[r.x + r.width, r.y + r.height]
	].map(([x, y]) => ({
		x: width / 2 + c * (x - width / 2) - s * (y - height / 2),
		y: height / 2 + s * (x - width / 2) + c * (y - height / 2)
	}));
	const x = Math.floor(Math.min(...points.map((p) => p.x)) + 1e-8), y = Math.floor(Math.min(...points.map((p) => p.y)) + 1e-8);
	return {
		x,
		y,
		width: Math.ceil(Math.max(...points.map((p) => p.x)) - 1e-8) - x,
		height: Math.ceil(Math.max(...points.map((p) => p.y)) - 1e-8) - y
	};
}
function rotatePoint(p, width, height, degrees) {
	const angle = degrees * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
	return {
		x: width / 2 + c * (p.x - width / 2) - s * (p.y - height / 2),
		y: height / 2 + s * (p.x - width / 2) + c * (p.y - height / 2)
	};
}
// src/crop.ts
var cropHandles = (r) => [
	[
		"nw",
		r.x,
		r.y
	],
	[
		"n",
		r.x + r.width / 2,
		r.y
	],
	[
		"ne",
		r.x + r.width,
		r.y
	],
	[
		"e",
		r.x + r.width,
		r.y + r.height / 2
	],
	[
		"se",
		r.x + r.width,
		r.y + r.height
	],
	[
		"s",
		r.x + r.width / 2,
		r.y + r.height
	],
	[
		"sw",
		r.x,
		r.y + r.height
	],
	[
		"w",
		r.x,
		r.y + r.height / 2
	]
];
var clamp$1 = (n, min, max) => Math.max(min, Math.min(max, n));
function hitCrop(r, x, y, tolerance) {
	for (const [handle, hx, hy] of cropHandles(r)) if (Math.abs(x - hx) <= tolerance && Math.abs(y - hy) <= tolerance) return handle;
	return x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.height ? "move" : null;
}
function adjustCrop(r, handle, dx, dy, width, height) {
	dx = Math.round(dx);
	dy = Math.round(dy);
	if (handle === "move") return {
		...r,
		x: clamp$1(r.x + dx, 0, width - r.width),
		y: clamp$1(r.y + dy, 0, height - r.height)
	};
	let left = r.x, top = r.y, right = r.x + r.width, bottom = r.y + r.height;
	if (handle.includes("w")) left = clamp$1(left + dx, 0, right - 4);
	if (handle.includes("e")) right = clamp$1(right + dx, left + 4, width);
	if (handle.includes("n")) top = clamp$1(top + dy, 0, bottom - 4);
	if (handle.includes("s")) bottom = clamp$1(bottom + dy, top + 4, height);
	return {
		x: left,
		y: top,
		width: right - left,
		height: bottom - top
	};
}
// src/editor.ts
var colors = {
	unassigned: "#90a4ae",
	alignment: "#ffca28",
	digit: "#4dd0e1",
	analog: "#b388ff",
	number_block: "#81c784"
};
var make = (tag, text, cls) => {
	const node = document.createElement(tag);
	if (text) node.textContent = text;
	if (cls) node.className = cls;
	return node;
};
var uid = (prefix) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
var clamp = (v, min, max) => Math.min(max, Math.max(min, v));
function render(host, settings, context) {
	const draft = structuredClone(settings);
	let alive = true, image = null, selected = null, tool = "select";
	let revision = 0, imageGeneration = 0;
	let zoom = 1, pan = {
		x: 0,
		y: 0
	}, busy = false;
	let drag = null;
	let straightenLine = null;
	let provisional = null;
	let cropDraft = null;
	const history = [];
	const rejectedFrames = /* @__PURE__ */ new Map();
	const recognizedFrames = /* @__PURE__ */ new Map();
	const root = make("section", void 0, "amr-editor");
	host.append(root);
	const style = make("link");
	style.rel = "stylesheet";
	style.href = new URL("./editor.css", "" + import.meta.url).href;
	root.append(style);
	const intro = make("div", void 0, "amr-intro");
	intro.append(make("h3", "Reference image & reading regions"), make("span", "Local recognition · AI-on-the-edge", "amr-badge"));
	root.append(intro);
	root.append(make("p", "Upload a reference, crop the area to use, mark two distinctive alignment features, then frame each digit, decade dial or complete printed number block. Coordinates are stored in image pixels.", "amr-help"));
	const status = make("div", void 0, "amr-status");
	status.setAttribute("role", "status");
	function say(message, error = false) {
		if (!alive) return;
		status.textContent = message;
		status.classList.toggle("amr-error", error);
	}
	function button(parent, text, fn, primary = false) {
		const b = make("button", text, primary ? "amr-primary" : void 0);
		b.type = "button";
		b.addEventListener("click", fn);
		parent.append(b);
		return b;
	}
	function changed() {
		revision++;
		context.changed();
		results.replaceChildren();
		rejectedFrames.clear();
		recognizedFrames.clear();
		refreshTools();
		draw();
		say("Draft changed. Save the Action to keep this configuration.");
	}
	function checkpoint() {
		history.push(structuredClone(draft));
		if (history.length > 30) history.shift();
	}
	function frameLabel(r) {
		return r.name.replace(/^Frame\s+(\d+)$/, "F$1");
	}
	function newFrameName() {
		const used = new Set(regions().map(frameLabel));
		let n = 1;
		while (used.has(`F${n}`)) n++;
		return `F${n}`;
	}
	function regions() {
		return draft.regions ?? [];
	}
	function meters() {
		return draft.meters ?? [];
	}
	function selectedRegion() {
		return regions().find((r) => r.id === selected);
	}
	function dims() {
		if (!image) return {
			x: 1,
			y: 1
		};
		return (draft.rotation ?? 0) % 180 ? {
			x: image.naturalHeight,
			y: image.naturalWidth
		} : {
			x: image.naturalWidth,
			y: image.naturalHeight
		};
	}
	const referenceInput = make("input");
	referenceInput.type = "file";
	referenceInput.accept = "image/png,image/jpeg";
	referenceInput.hidden = true;
	referenceInput.setAttribute("aria-label", "Upload reference image");
	root.append(referenceInput);
	const imageTools = make("div", void 0, "amr-toolstrip");
	imageTools.setAttribute("role", "group");
	imageTools.setAttribute("aria-label", "Reference images");
	function imageButton(label, path, action, parent = imageTools) {
		const b = button(parent, label, action);
		b.classList.add("amr-icon-tool");
		b.setAttribute("aria-label", label);
		const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
		svg.setAttribute("viewBox", "0 0 24 24");
		svg.setAttribute("aria-hidden", "true");
		svg.setAttribute("fill", "none");
		svg.setAttribute("stroke", "currentColor");
		svg.setAttribute("stroke-width", "1.8");
		svg.setAttribute("stroke-linecap", "round");
		svg.setAttribute("stroke-linejoin", "round");
		const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
		line.setAttribute("d", path);
		svg.append(line);
		const tip = make("span", label, "amr-tool-tooltip");
		tip.setAttribute("aria-hidden", "true");
		b.replaceChildren(svg, tip);
		return b;
	}
	const uploadButton = imageButton("Add reference image", "M12 16V3M7 8l5-5 5 5M4 15v6h16v-6", () => {
		if (!canChangeImage()) return;
		referenceInput.click();
	});
	const previousImage = imageButton("Previous reference image", "M15 5l-7 7 7 7", () => {
		browseReference(-1);
	});
	const imageCounter = make("span", "0 / 0", "amr-image-counter");
	imageCounter.setAttribute("role", "status");
	imageCounter.setAttribute("aria-label", "Reference image position");
	imageTools.append(imageCounter);
	const nextImage = imageButton("Next reference image", "M9 5l7 7-7 7", () => {
		browseReference(1);
	});
	function refreshImages() {
		const images = referenceImages(draft), index = images.findIndex((r) => r.asset_id === draft.reference?.asset_id);
		imageCounter.textContent = images.length ? `${index + 1} / ${images.length}` : "0 / 0";
		previousImage.hidden = nextImage.hidden = images.length < 2;
		imageCounter.hidden = images.length < 2;
		previousImage.disabled = busy || index <= 0;
		nextImage.disabled = busy || index >= images.length - 1;
		uploadButton.disabled = busy || images.length >= 16;
	}
	function canChangeImage() {
		if (busy || drag) return false;
		if (tool === "crop" && cropDraft && JSON.stringify(cropDraft) !== JSON.stringify(area())) {
			say("Apply or cancel the crop before changing images.", true);
			return false;
		}
		return true;
	}
	async function browseReference(direction) {
		if (!canChangeImage()) return;
		const images = referenceImages(draft), next = images[images.findIndex((r) => r.asset_id === draft.reference?.asset_id) + direction];
		if (!next) return;
		checkpoint();
		draft.references = images;
		draft.reference = { ...next };
		selected = null;
		cropDraft = null;
		changed();
		await loadReference(true);
	}
	const recognitionTools = make("div", void 0, "amr-toolstrip amr-recognition-tools");
	recognitionTools.setAttribute("role", "group");
	recognitionTools.setAttribute("aria-label", "Recognition");
	const runButton = button(recognitionTools, "Run recognition", () => {
		runPreview();
	}, true);
	runButton.title = "Read the loaded reference image using the current configuration. No MQTT publication.";
	runButton.disabled = !draft.reference;
	const results = make("div", void 0, "amr-results");
	results.setAttribute("aria-label", "Reference image recognition results");
	const workspace = make("div", void 0, "amr-workspace");
	const viewport = make("div", void 0, "amr-viewport");
	const canvas = make("canvas");
	canvas.tabIndex = 0;
	canvas.setAttribute("aria-label", "Reference image region editor. Drag on empty image space to draw a frame. Drag inside to move; drag any corner to resize. Arrow keys move the selected region; Shift plus arrows resizes it.");
	viewport.append(canvas);
	const inspector = make("aside", void 0, "amr-inspector");
	workspace.append(viewport, inspector);
	const primaryTools = make("div", void 0, "amr-toolstrip");
	primaryTools.setAttribute("role", "group");
	primaryTools.setAttribute("aria-label", "Image tools");
	const rotationTools = make("div", void 0, "amr-toolstrip");
	rotationTools.setAttribute("role", "group");
	rotationTools.setAttribute("aria-label", "Image rotation");
	const toolbar = make("div", void 0, "amr-toolbar-groups");
	toolbar.setAttribute("aria-label", "Image editor toolbar");
	toolbar.append(imageTools, primaryTools, rotationTools, recognitionTools);
	root.append(toolbar);
	const toolButtons = /* @__PURE__ */ new Map();
	const toolIcons = {
		select: "M5 3l14 10-7 1-3 7z",
		pan: "M12 3v18M3 12h18M8 7l4-4 4 4M8 17l4 4 4-4M7 8l-4 4 4 4M17 8l4 4-4 4",
		crop: "M6 3v15h15M3 6h15v15",
		fit: "M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M7 8h10v8H7z",
		"zoom-in": "M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0M6 10h8M10 6v8",
		"zoom-out": "M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0M6 10h8",
		undo: "M9 5L4 10l5 5M4 10h10a6 6 0 0 1 0 12",
		rotate: "M20 3v6h-6M20 9a8 8 0 1 0 0 6",
		straighten: "M3 20h18M5 14L19 6M3 12l4 4M17 4l4 4"
	};
	for (const [key, label] of [
		["select", "Select / move"],
		["pan", "Move view"],
		["crop", "Crop image"],
		["fit", "Fit area"],
		["zoom-in", "Zoom in"],
		["zoom-out", "Zoom out"],
		["undo", "Undo"],
		["rotate", "Rotate 90°"],
		["straighten", "Straighten image"]
	]) {
		const icon = toolIcons[key];
		const b = button(key === "rotate" || key === "straighten" ? rotationTools : primaryTools, label, () => {
			if (key === "fit") {
				fit();
				return;
			}
			if (key === "zoom-in" || key === "zoom-out") {
				zoomView(key === "zoom-in" ? 1.25 : 1 / 1.25);
				return;
			}
			if (key === "undo") {
				undo();
				return;
			}
			if (key === "rotate") {
				rotate();
				return;
			}
			const refit = tool === "crop" || key === "crop";
			tool = key;
			cropDraft = key === "crop" ? { ...area() } : null;
			selected = null;
			if (refit) fit();
			else draw();
			inspect();
			refreshTools();
		});
		if (key !== "fit" && key !== "undo" && key !== "rotate" && key !== "zoom-in" && key !== "zoom-out") toolButtons.set(key, b);
		if (icon) {
			b.classList.add("amr-icon-tool");
			b.setAttribute("aria-label", label);
			const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
			svg.setAttribute("viewBox", "0 0 24 24");
			svg.setAttribute("aria-hidden", "true");
			svg.setAttribute("fill", "none");
			svg.setAttribute("stroke", "currentColor");
			svg.setAttribute("stroke-width", "1.8");
			svg.setAttribute("stroke-linecap", "round");
			svg.setAttribute("stroke-linejoin", "round");
			const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
			path.setAttribute("d", icon);
			svg.append(path);
			const tip = make("span", label, "amr-tool-tooltip");
			tip.setAttribute("aria-hidden", "true");
			b.replaceChildren(svg, tip);
		}
	}
	const deleteButton = imageButton("Delete region", "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7", removeSelected, primaryTools);
	deleteButton.hidden = true;
	function refreshTools() {
		deleteButton.hidden = !selectedRegion();
		deleteButton.disabled = busy;
		for (const [key, b] of toolButtons) b.setAttribute("aria-pressed", String(key === tool));
	}
	function undo() {
		if (busy) return;
		const previous = history.pop();
		if (previous) {
			for (const key of Object.keys(draft)) delete draft[key];
			Object.assign(draft, previous);
			straightenLine = null;
			selected = null;
			cropDraft = null;
			tool = "select";
			changed();
			loadReference();
			refresh();
		}
	}
	function rotate() {
		if (!image) return;
		checkpoint();
		straightenLine = null;
		const size = dims();
		for (const r of [...regions(), ...draft.crop ? [draft.crop] : []]) {
			const { x, y, width, height } = r;
			r.x = size.y - y - height;
			r.y = x;
			r.width = height;
			r.height = width;
		}
		draft.rotation = ((draft.rotation ?? 0) + 90) % 360;
		cropDraft = tool === "crop" ? { ...area() } : null;
		changed();
		fit();
		refresh();
	}
	root.append(workspace, status, results);
	const meterHeader = make("div", void 0, "amr-intro");
	meterHeader.append(make("h3", "Value mapping"));
	button(meterHeader, "Add value", () => {
		checkpoint();
		(draft.meters ??= []).push({
			id: uid("meter"),
			name: `Meter ${meters().length + 1}`,
			unit: draft.unit ?? "",
			layout: []
		});
		changed();
		renderMeters();
		inspect();
	});
	root.append(meterHeader);
	const meterCards = make("div", void 0, "amr-value-table-wrap");
	root.append(meterCards);
	const optionsPanel = make("section", void 0, "amr-settings-panel");
	optionsPanel.hidden = true;
	optionsPanel.append(make("h3", "Recognition settings"));
	const options = make("div", void 0, "amr-settings-grid");
	optionsPanel.append(options);
	const testPanel = make("section", void 0, "amr-settings-panel");
	testPanel.hidden = true;
	testPanel.append(make("h3", "Test options"), make("p", "Run recognition uses the selected reference image. These previous values are used only for this test and are not saved or sent to MQTT.", "amr-help"));
	const previousLabel = make("label", "Previous readings (optional JSON, keyed by value ID)");
	const previousInput = make("textarea");
	previousInput.rows = 4;
	previousInput.value = "{}";
	previousInput.setAttribute("aria-label", "Previous readings JSON");
	previousLabel.append(previousInput);
	testPanel.append(previousLabel);
	const valueIds = make("div", void 0, "amr-help");
	testPanel.append(valueIds);
	root.insertBefore(optionsPanel, workspace);
	root.insertBefore(testPanel, workspace);
	const settingsButton = imageButton("Recognition settings", "M9.5 3h5l.5 3 2 1 2.5-1 2 4-2.5 2v2l2 2-2 4-3-1-2 1-.5 2h-4l-.5-2-2-1-3 1-2-4 2-2v-2l-2.5-2 2-4 2.5 1 2-1z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0", () => togglePanel(optionsPanel), recognitionTools);
	const testButton = imageButton("Test options", "M9 3h6M10 3v7l-6 9a1.3 1.3 0 0 0 1 2h14a1.3 1.3 0 0 0 1-2l-6-9V3M7 15h10", () => togglePanel(testPanel), recognitionTools);
	settingsButton.setAttribute("aria-expanded", "false");
	testButton.setAttribute("aria-expanded", "false");
	function togglePanel(panel) {
		const open = panel.hidden;
		optionsPanel.hidden = testPanel.hidden = true;
		panel.hidden = !open;
		settingsButton.setAttribute("aria-expanded", String(!optionsPanel.hidden));
		testButton.setAttribute("aria-expanded", String(!testPanel.hidden));
	}
	root.append(make("p", "Recognition models and correction logic adapted from jomjol/AI-on-the-edge-device. Dual Use License. Decade dials and mechanical digits are supported; arbitrary gauge scales are not.", "amr-help"));
	function input(parent, label, value, change, type = "text") {
		const wrap = make("label", label);
		const field = make("input");
		field.type = type;
		field.value = String(value);
		field.addEventListener(type === "number" ? "change" : "input", () => change(field.value));
		wrap.append(field);
		parent.append(wrap);
		return field;
	}
	function check(parent, label, value, change) {
		const wrap = make("label", void 0, "amr-check");
		const field = make("input");
		field.type = "checkbox";
		field.checked = value;
		field.addEventListener("change", () => change(field.checked));
		wrap.append(field, make("span", label));
		parent.append(wrap);
	}
	function optionNumber(key, label, fallback, min, max, step, parent = options) {
		const field = input(parent, label, draft[key] ?? fallback, (v) => {
			const n = Number(v);
			if (!Number.isFinite(n) || n < min || n > max) {
				say("Value is outside the allowed range.", true);
				field.value = String(draft[key] ?? fallback);
				return;
			}
			checkpoint();
			draft[key] = n;
			changed();
		}, "number");
		field.min = String(min);
		field.max = String(max);
		field.step = step;
	}
	function settingsGroup(title) {
		const group = make("fieldset", void 0, "amr-settings-group");
		group.append(make("legend", title));
		options.append(group);
		return group;
	}
	function alignmentOptions() {
		const group = make("div", void 0, "amr-alignment-settings");
		group.append(make("h3", "Alignment settings"), make("p", "Shared by both alignment references. These settings apply to every input image.", "amr-help"));
		inspector.append(group);
		optionNumber("search_radius", "Search radius (pixels)", 40, 0, 200, "1", group);
		optionNumber("alignment_threshold", "Minimum alignment score", .7, .1, 1, ".05", group);
	}
	function renderOptions() {
		options.replaceChildren();
		const quality = settingsGroup("Recognition quality");
		optionNumber("digit_threshold", "Minimum digit fit", draft.recognition_threshold ?? .5, 0, 1, ".05", quality);
		optionNumber("analog_threshold", "Minimum dial fit", draft.recognition_threshold ?? .5, 0, 1, ".05", quality);
		quality.append(make("p", "Higher thresholds reject more uncertain results. Number blocks use OCR agreement instead of a model fit score.", "amr-help"));
		const preparation = settingsGroup("Image preparation");
		for (const [key, label] of [["digit_preprocessing", "Digits"], ["analog_preprocessing", "Analog dials"]]) {
			const wrap = make("label", label), select = make("select");
			for (const [value, text] of [
				["none", "Original colors"],
				["autocontrast", "Auto contrast"],
				["grayscale_autocontrast", "Grayscale + auto contrast"]
			]) {
				const option = make("option", text);
				option.value = value;
				select.append(option);
			}
			select.value = draft[key] ?? "none";
			select.addEventListener("change", () => {
				checkpoint();
				draft[key] = select.value;
				changed();
			});
			wrap.append(select);
			preparation.append(wrap);
		}
		const stability = settingsGroup("Frame stability");
		check(stability, "Check five crop positions", !!draft.stability_check, (v) => {
			checkpoint();
			draft.stability_check = v;
			changed();
		});
		stability.append(make("p", "Checks digit and dial crops at ±2 pixels. All variants must pass the fit threshold and agree after correction. Leave a two-pixel margin around frames inside the crop.", "amr-help"));
		const confirmation = settingsGroup("Capture confirmation");
		check(confirmation, "Require two matching captures", !!draft.require_confirmation, (v) => {
			checkpoint();
			draft.require_confirmation = v;
			changed();
		});
		confirmation.append(make("p", "Home Assistant must supply image and confirmation_image from distinct captures. Reference-only tests cannot confirm a value. Exact agreement can reject a moving meter.", "amr-help"));
		valueIds.textContent = meters().map((m) => `${m.name}: ${m.id}`).join(" · ");
	}
	async function loadReference(preserveView = false) {
		const generation = ++imageGeneration;
		image = null;
		draw();
		refreshImages();
		if (!draft.reference) {
			refresh();
			return false;
		}
		const assetId = draft.reference.asset_id;
		try {
			const candidate = await new Promise((resolve, reject) => {
				const value = new Image();
				value.onload = () => resolve(value);
				value.onerror = () => reject(/* @__PURE__ */ new Error("Reference image could not be loaded."));
				value.src = context.assetUrl(assetId);
			});
			if (!alive || generation !== imageGeneration) return false;
			image = candidate;
			if (tool === "crop") cropDraft = { ...area() };
			if (viewport.clientWidth > 0 && viewport.clientHeight > 0) {
				if (!preserveView) fit();
				initialFit = true;
			}
			refresh();
			return true;
		} catch (error) {
			if (alive && generation === imageGeneration) say(error instanceof Error ? error.message : "Reference load failed.", true);
			return false;
		}
	}
	async function upload(file) {
		if (!canChangeImage()) return;
		busy = true;
		refreshImages();
		runButton.disabled = true;
		say("Uploading private image…");
		try {
			if (file.size > 8388608) throw new Error("Image must be at most 8 MiB.");
			const bitmap = await createImageBitmap(file);
			if (bitmap.width * bitmap.height > 16e6 || Math.max(bitmap.width, bitmap.height) > 8192) {
				bitmap.close();
				throw new Error("Image must be at most 16 megapixels and 8192 pixels per side.");
			}
			const current = draft.reference;
			if (current && (bitmap.width !== current.width || bitmap.height !== current.height)) {
				bitmap.close();
				throw new Error("Additional reference images must have the same dimensions to preserve frames and crop.");
			}
			const normalized = document.createElement("canvas");
			normalized.width = bitmap.width;
			normalized.height = bitmap.height;
			normalized.getContext("2d").drawImage(bitmap, 0, 0);
			bitmap.close();
			const blob = await new Promise((resolve, reject) => normalized.toBlob((b) => b ? resolve(b) : reject(/* @__PURE__ */ new Error("Image conversion failed.")), "image/jpeg", .95));
			const asset = await context.uploadImage(new File([blob], "image.jpg", { type: "image/jpeg" }));
			if (!alive) return;
			const reference = {
				asset_id: asset.id,
				width: asset.width,
				height: asset.height
			};
			const images = addReference(draft, reference);
			checkpoint();
			draft.references = images;
			draft.reference = reference;
			cropDraft = null;
			selected = null;
			changed();
			if (await loadReference(!!current)) say("Reference image added. Frames, crop and rotation are shared across images. Save to keep the selected reference.");
		} catch (error) {
			say(error instanceof Error ? error.message : "Upload failed.", true);
		} finally {
			busy = false;
			if (alive) {
				runButton.disabled = !draft.reference;
				refreshImages();
				refreshTools();
			}
		}
	}
	referenceInput.addEventListener("change", () => {
		const f = referenceInput.files?.[0];
		referenceInput.value = "";
		if (f) upload(f);
	});
	function area() {
		const size = dims();
		return draft.crop ?? {
			x: 0,
			y: 0,
			width: size.x,
			height: size.y
		};
	}
	function fits(r, b) {
		return r.x >= b.x && r.y >= b.y && r.x + r.width <= b.x + b.width && r.y + r.height <= b.y + b.height;
	}
	function applyCrop(value) {
		const size = dims();
		if (value.width < 4 || value.height < 4 || !fits(value, {
			x: 0,
			y: 0,
			width: size.x,
			height: size.y
		})) {
			say("Crop must stay inside the image and be at least 4 × 4 pixels.", true);
			return false;
		}
		if (regions().some((r) => !fits(r, value))) {
			say("Crop must include all alignment and reading regions. Move or remove regions outside the crop first.", true);
			return false;
		}
		checkpoint();
		draft.crop = { ...value };
		selected = null;
		cropDraft = null;
		tool = "select";
		changed();
		fit();
		refresh();
		return true;
	}
	function applyStraighten(delta) {
		if (!image || busy) return false;
		const size = dims();
		const normalized = (((draft.straighten_angle ?? 0) + delta + 180) % 360 + 360) % 360 - 180;
		const nextAngle = Math.round(normalized * 1e6) / 1e6;
		delta = nextAngle - (draft.straighten_angle ?? 0);
		if (Math.abs(delta) < 1e-6) {
			draw();
			return true;
		}
		const nextRegions = regions().map((r) => ({
			...r,
			...rotateBounds(r, size.x, size.y, delta)
		}));
		const bounds = {
			x: 0,
			y: 0,
			width: size.x,
			height: size.y
		};
		if (nextRegions.some((r) => !fits(r, bounds))) {
			say("Rotation would move a frame outside the image. Move that frame inward or use a smaller correction.", true);
			draw();
			return false;
		}
		let nextCrop;
		if (draft.crop) {
			const r = rotateBounds(draft.crop, size.x, size.y, delta);
			const x = Math.max(0, r.x), y = Math.max(0, r.y);
			nextCrop = {
				x,
				y,
				width: Math.min(size.x, r.x + r.width) - x,
				height: Math.min(size.y, r.y + r.height) - y
			};
			if (nextCrop.width < 4 || nextCrop.height < 4 || nextRegions.some((r) => !fits(r, nextCrop))) {
				say("Rotation would exclude a frame from the crop. Reset or expand the crop first.", true);
				draw();
				return false;
			}
		}
		checkpoint();
		draft.straighten_angle = nextAngle;
		draft.regions = nextRegions;
		if (nextCrop) draft.crop = nextCrop;
		cropDraft = null;
		selected = null;
		changed();
		refresh();
		return true;
	}
	function zoomView(factor) {
		if (!image || drag) return;
		const next = clamp(zoom * factor, .01, 32), ratio = next / zoom;
		const center = {
			x: viewport.clientWidth / 2,
			y: viewport.clientHeight / 2
		};
		pan = {
			x: center.x - (center.x - pan.x) * ratio,
			y: center.y - (center.y - pan.y) * ratio
		};
		zoom = next;
		draw();
	}
	function fit() {
		if (!image) return;
		const size = dims();
		const a = tool === "crop" ? {
			x: 0,
			y: 0,
			width: size.x,
			height: size.y
		} : area();
		zoom = Math.max(.01, Math.min(viewport.clientWidth / a.width, viewport.clientHeight / a.height) * .94);
		pan = {
			x: (viewport.clientWidth - a.width * zoom) / 2 - a.x * zoom,
			y: (viewport.clientHeight - a.height * zoom) / 2 - a.y * zoom
		};
		draw();
	}
	function draw() {
		const ratio = window.devicePixelRatio || 1;
		canvas.width = Math.round(viewport.clientWidth * ratio);
		canvas.height = Math.round(viewport.clientHeight * ratio);
		const c = canvas.getContext("2d");
		c.scale(ratio, ratio);
		c.clearRect(0, 0, viewport.clientWidth, viewport.clientHeight);
		if (!image) {
			c.fillStyle = "#cad8e2";
			c.font = "16px sans-serif";
			c.textAlign = "center";
			c.fillText("Upload a reference image to begin", viewport.clientWidth / 2, viewport.clientHeight / 2);
			return;
		}
		c.save();
		c.translate(pan.x, pan.y);
		c.scale(zoom, zoom);
		const size = dims();
		{
			const a = tool === "crop" ? {
				x: 0,
				y: 0,
				width: size.x,
				height: size.y
			} : area();
			c.beginPath();
			c.rect(a.x, a.y, a.width, a.height);
			c.clip();
		}
		c.save();
		c.translate(size.x / 2, size.y / 2);
		c.rotate(((draft.rotation ?? 0) + (draft.straighten_angle ?? 0)) * Math.PI / 180);
		c.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
		c.restore();
		if (tool !== "straighten") for (const r of [...regions(), ...provisional ? [provisional] : []]) {
			c.strokeStyle = rejectedFrames.has(r.id) ? "#ef5350" : colors[r.kind];
			c.lineWidth = (r.id === selected ? 3 : 2) / zoom;
			c.strokeRect(r.x, r.y, r.width, r.height);
			c.fillStyle = colors[r.kind];
			c.font = `${12 / zoom}px sans-serif`;
			const label = frameLabel(r);
			c.fillRect(r.x, r.y - 18 / zoom, c.measureText(label).width + 8 / zoom, 18 / zoom);
			c.fillStyle = "#10202a";
			c.fillText(label, r.x + 4 / zoom, r.y - 5 / zoom);
			if (r.id === selected) {
				c.fillStyle = "#fff";
				for (const [, x, y] of cropHandles(r).filter(([h]) => h.length === 2)) c.fillRect(x - 5 / zoom, y - 5 / zoom, 10 / zoom, 10 / zoom);
			}
		}
		if (tool !== "straighten" && !drag) for (const r of regions()) {
			const result = recognizedFrames.get(r.id);
			if (!result) continue;
			const text = !result.accepted || result.raw === null ? "Unreadable" : typeof result.raw === "number" ? r.kind === "digit" ? String(Math.floor(result.raw)) : result.raw.toFixed(2) : result.raw;
			const height = Math.min(22 / zoom, r.height), padding = Math.min(4 / zoom, r.width / 8);
			c.save();
			c.beginPath();
			c.rect(r.x, r.y, r.width, r.height);
			c.clip();
			c.fillStyle = result.accepted ? "rgba(0,45,35,.9)" : "rgba(125,20,20,.92)";
			c.fillRect(r.x, r.y + r.height - height, r.width, height);
			c.fillStyle = "#fff";
			c.font = `600 ${Math.min(14 / zoom, height * .7)}px sans-serif`;
			c.textAlign = "center";
			c.textBaseline = "middle";
			c.fillText(text, r.x + r.width / 2, r.y + r.height - height / 2, r.width - 2 * padding);
			c.restore();
		}
		const guide = tool === "straighten" ? drag?.mode === "straighten" ? drag : straightenLine : null;
		if (guide) {
			c.strokeStyle = "#00e5ff";
			c.lineWidth = 2 / zoom;
			c.beginPath();
			c.moveTo(guide.start.x, guide.start.y);
			c.lineTo(guide.last.x, guide.last.y);
			c.stroke();
			for (const p of [guide.start, guide.last]) {
				c.beginPath();
				c.arc(p.x, p.y, 5 / zoom, 0, 2 * Math.PI);
				c.fillStyle = "#fff";
				c.fill();
			}
			c.font = `${14 / zoom}px sans-serif`;
			c.fillText(`${lineCorrection(guide.start, guide.last).toFixed(2)}°`, guide.last.x + 10 / zoom, guide.last.y - 10 / zoom);
		}
		const crop = cropDraft ?? area();
		if (tool === "crop" && image) {
			c.fillStyle = "rgba(0,0,0,.55)";
			c.beginPath();
			c.rect(0, 0, size.x, size.y);
			c.rect(crop.x, crop.y, crop.width, crop.height);
			c.fill("evenodd");
			c.strokeStyle = "#fff";
			c.lineWidth = 2 / zoom;
			c.setLineDash([8 / zoom, 4 / zoom]);
			c.strokeRect(crop.x, crop.y, crop.width, crop.height);
			c.setLineDash([]);
			for (const [handle, x, y] of cropHandles(crop)) {
				const corner = handle.length === 2;
				const length = 14 / zoom;
				c.beginPath();
				if (corner) {
					const sx = handle.includes("w") ? 1 : -1, sy = handle.includes("n") ? 1 : -1;
					c.moveTo(x + sx * length, y);
					c.lineTo(x, y);
					c.lineTo(x, y + sy * length);
				} else if (handle === "n" || handle === "s") {
					c.moveTo(x - length / 2, y);
					c.lineTo(x + length / 2, y);
				} else {
					c.moveTo(x, y - length / 2);
					c.lineTo(x, y + length / 2);
				}
				c.strokeStyle = "#fff";
				c.lineWidth = 7 / zoom;
				c.stroke();
				c.strokeStyle = "#17232c";
				c.lineWidth = 4 / zoom;
				c.stroke();
			}
		}
		c.restore();
		if (tool === "pan") {
			const a = area(), width = viewport.clientWidth, height = viewport.clientHeight;
			const centeredX = Math.abs(pan.x + (a.x + a.width / 2) * zoom - width / 2) < .5;
			const centeredY = Math.abs(pan.y + (a.y + a.height / 2) * zoom - height / 2) < .5;
			c.save();
			c.strokeStyle = "#e040fb";
			c.lineWidth = 1.5;
			c.setLineDash([6, 4]);
			c.beginPath();
			if (centeredX) {
				c.moveTo(width / 2, 0);
				c.lineTo(width / 2, height);
			}
			if (centeredY) {
				c.moveTo(0, height / 2);
				c.lineTo(width, height / 2);
			}
			c.stroke();
			c.restore();
		}
	}
	function regionHit(p) {
		const ordered = [...regions()].reverse();
		const active = selectedRegion();
		if (active) {
			const index = ordered.indexOf(active);
			ordered.splice(index, 1);
			ordered.unshift(active);
		}
		for (const r of ordered) {
			const corners = cropHandles(r).filter(([h]) => h.length === 2).sort((a, b) => Math.hypot(a[1] - p.x, a[2] - p.y) - Math.hypot(b[1] - p.x, b[2] - p.y));
			for (const [handle, x, y] of corners) if (Math.abs(p.x - x) <= 9 / zoom && Math.abs(p.y - y) <= 9 / zoom) return {
				region: r,
				handle
			};
		}
		const region = ordered.find((r) => p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height);
		return region ? {
			region,
			handle: "move"
		} : null;
	}
	function point(event) {
		const rect = canvas.getBoundingClientRect();
		return {
			x: (event.clientX - rect.left - pan.x) / zoom,
			y: (event.clientY - rect.top - pan.y) / zoom
		};
	}
	canvas.addEventListener("pointerdown", (event) => {
		if (!image || busy) return;
		canvas.focus();
		const p = point(event), size = dims();
		canvas.setPointerCapture(event.pointerId);
		if (tool === "straighten") {
			if (p.x < 0 || p.y < 0 || p.x > size.x || p.y > size.y) return;
			drag = {
				start: p,
				last: p,
				mode: "straighten"
			};
			draw();
			return;
		}
		if (tool === "pan") {
			drag = {
				start: {
					x: event.clientX,
					y: event.clientY
				},
				last: p,
				panOriginal: { ...pan },
				mode: "pan"
			};
			canvas.style.cursor = "grabbing";
			return;
		}
		if (tool === "crop") {
			const original = { ...cropDraft ?? area() }, handle = hitCrop(original, p.x, p.y, 12 / zoom);
			if (!handle) return;
			drag = {
				start: p,
				last: p,
				mode: "crop",
				cropOriginal: original,
				handle
			};
			cropDraft = original;
			draw();
			return;
		}
		const hit = regionHit(p);
		selected = hit?.region.id ?? null;
		refreshTools();
		if (!hit) {
			inspect();
			draw();
		}
		if (hit) {
			checkpoint();
			drag = {
				start: p,
				last: p,
				original: { ...hit.region },
				handle: hit.handle,
				mode: hit.handle === "move" ? "move" : "resize"
			};
			inspect();
			draw();
			refreshTools();
			return;
		}
		const bounds = area();
		if (!fits({
			x: p.x,
			y: p.y,
			width: 0,
			height: 0
		}, bounds)) return;
		if (regions().length >= 32) {
			say("Maximum of 32 regions.", true);
			return;
		}
		checkpoint();
		drag = {
			start: p,
			last: p,
			mode: "draw"
		};
		provisional = {
			id: uid("roi"),
			name: newFrameName(),
			kind: "unassigned",
			x: Math.round(p.x),
			y: Math.round(p.y),
			width: 0,
			height: 0,
			order: 0
		};
		draw();
	});
	canvas.addEventListener("pointermove", (event) => {
		const p = point(event), size = dims();
		if (!drag) {
			const handle = image ? tool === "crop" ? hitCrop(cropDraft ?? area(), p.x, p.y, 12 / zoom) : tool === "select" ? regionHit(p)?.handle : null : null;
			const cursors = {
				nw: "nwse-resize",
				se: "nwse-resize",
				ne: "nesw-resize",
				sw: "nesw-resize",
				n: "ns-resize",
				s: "ns-resize",
				w: "ew-resize",
				e: "ew-resize",
				move: "move"
			};
			canvas.style.cursor = handle ? cursors[handle] : tool === "pan" ? "grab" : tool === "select" || tool === "straighten" ? "crosshair" : "default";
			return;
		}
		if (drag.mode === "pan" && drag.panOriginal) {
			const a = area(), center = {
				x: viewport.clientWidth / 2 - (a.x + a.width / 2) * zoom,
				y: viewport.clientHeight / 2 - (a.y + a.height / 2) * zoom
			};
			const raw = {
				x: drag.panOriginal.x + event.clientX - drag.start.x,
				y: drag.panOriginal.y + event.clientY - drag.start.y
			};
			pan = {
				x: Math.abs(raw.x - center.x) <= 6 ? center.x : raw.x,
				y: Math.abs(raw.y - center.y) <= 6 ? center.y : raw.y
			};
			draw();
			return;
		}
		if (drag.mode === "straighten") {
			drag.last = {
				x: clamp(p.x, 0, size.x),
				y: clamp(p.y, 0, size.y)
			};
			draw();
			return;
		}
		if (drag.mode === "crop" && drag.cropOriginal && drag.handle) {
			cropDraft = adjustCrop(drag.cropOriginal, drag.handle, p.x - drag.start.x, p.y - drag.start.y, size.x, size.y);
			draw();
			return;
		}
		if (drag.mode === "draw" && provisional) {
			const a = area();
			const end = {
				x: clamp(p.x, a.x, a.x + a.width),
				y: clamp(p.y, a.y, a.y + a.height)
			};
			provisional.x = Math.round(Math.min(drag.start.x, end.x));
			provisional.y = Math.round(Math.min(drag.start.y, end.y));
			provisional.width = Math.round(Math.abs(end.x - drag.start.x));
			provisional.height = Math.round(Math.abs(end.y - drag.start.y));
		} else if (drag.original) {
			const r = selectedRegion();
			if (r) {
				const o = drag.original, a = area();
				if (drag.mode === "move") {
					r.x = clamp(Math.round(o.x + p.x - drag.start.x), a.x, a.x + a.width - o.width);
					r.y = clamp(Math.round(o.y + p.y - drag.start.y), a.y, a.y + a.height - o.height);
				} else {
					const resized = adjustCrop({
						...o,
						x: o.x - a.x,
						y: o.y - a.y
					}, drag.handle ?? "se", p.x - drag.start.x, p.y - drag.start.y, a.width, a.height);
					Object.assign(r, {
						...resized,
						x: resized.x + a.x,
						y: resized.y + a.y
					});
				}
			}
		}
		draw();
	});
	function finish() {
		if (!drag) return;
		const mode = drag.mode;
		if (mode === "straighten") {
			const line = drag;
			drag = null;
			if (Math.hypot(line.last.x - line.start.x, line.last.y - line.start.y) * zoom < 12) {
				say("Draw a longer line between two points.", true);
				draw();
				return;
			}
			const before = draft.straighten_angle ?? 0;
			if (applyStraighten(lineCorrection(line.start, line.last))) {
				const size = dims(), delta = (draft.straighten_angle ?? 0) - before;
				straightenLine = {
					start: rotatePoint(line.start, size.x, size.y, delta),
					last: rotatePoint(line.last, size.x, size.y, delta)
				};
				draw();
			}
			return;
		}
		if (mode === "pan") canvas.style.cursor = "grab";
		if (mode === "crop") {
			drag = null;
			inspect();
			draw();
			return;
		}
		if (provisional) {
			const a = area();
			provisional.width = Math.min(provisional.width, a.x + a.width - provisional.x);
			provisional.height = Math.min(provisional.height, a.y + a.height - provisional.y);
			if (provisional.width >= 4 && provisional.height >= 4) {
				(draft.regions ??= []).push(provisional);
				selected = provisional.id;
			}
			provisional = null;
		}
		drag = null;
		if (mode !== "pan") {
			changed();
			refresh();
		}
	}
	canvas.addEventListener("pointerup", finish);
	canvas.addEventListener("pointercancel", () => {
		if (drag?.mode === "straighten") {
			drag = null;
			draw();
			return;
		}
		if (drag?.mode === "crop") {
			cropDraft = drag.cropOriginal ?? null;
			drag = null;
			inspect();
			draw();
		} else finish();
	});
	canvas.addEventListener("keydown", (event) => {
		if (tool === "straighten") {
			if (event.key === "Escape") {
				event.preventDefault();
				drag = null;
				tool = "select";
				refresh();
			}
			return;
		}
		if (tool === "crop") {
			if (event.key === "Enter") {
				event.preventDefault();
				applyCrop(cropDraft ?? area());
			} else if (event.key === "Escape") {
				event.preventDefault();
				cropDraft = null;
				tool = "select";
				fit();
				refresh();
			}
			return;
		}
		const r = selectedRegion();
		if (!r) return;
		if (event.key === "Delete" || event.key === "Backspace") {
			event.preventDefault();
			removeSelected();
			return;
		}
		const step = {
			ArrowLeft: {
				x: -1,
				y: 0
			},
			ArrowRight: {
				x: 1,
				y: 0
			},
			ArrowUp: {
				x: 0,
				y: -1
			},
			ArrowDown: {
				x: 0,
				y: 1
			}
		}[event.key];
		if (!step) return;
		event.preventDefault();
		checkpoint();
		const a = area();
		if (event.shiftKey) {
			r.width = clamp(r.width + step.x, 4, a.x + a.width - r.x);
			r.height = clamp(r.height + step.y, 4, a.y + a.height - r.y);
		} else {
			r.x = clamp(r.x + step.x, a.x, a.x + a.width - r.width);
			r.y = clamp(r.y + step.y, a.y, a.y + a.height - r.height);
		}
		changed();
		refresh();
	});
	function nextOrder(kind, meter, exclude) {
		const used = new Set(regions().filter((r) => r.id !== exclude && r.kind === kind && r.meter === meter).map((r) => r.order));
		for (let i = 0; i < 32; i++) if (!used.has(i)) return i;
		return 31;
	}
	function removeSelected() {
		if (busy || !selectedRegion()) return;
		checkpoint();
		for (const m of meters()) if (m.layout) m.layout = m.layout.filter((id) => id !== selected);
		draft.regions = regions().filter((r) => r.id !== selected);
		selected = null;
		changed();
		refresh();
	}
	function regionType(r) {
		const label = make("label", "Type");
		const type = make("select");
		type.setAttribute("aria-label", `Type for ${r.name}`);
		for (const [value, text] of [
			["unassigned", "Choose type…"],
			["alignment", "Alignment reference"],
			["digit", "Digit"],
			["analog", "Analog dial"],
			["number_block", "Number block"]
		]) {
			const option = make("option", text);
			option.value = value;
			type.append(option);
		}
		type.value = r.kind;
		type.addEventListener("change", () => {
			const kind = type.value;
			if (kind === "alignment" && regions().filter((other) => other !== r && other.kind === "alignment").length >= 2) {
				type.value = r.kind;
				say("Exactly two alignment references are supported.", true);
				return;
			}
			checkpoint();
			r.order = nextOrder(kind, r.meter, r.id);
			r.kind = kind;
			if (kind === "alignment" || kind === "unassigned") {
				delete r.meter;
				delete r.ccw;
			}
			if (kind !== "analog") delete r.ccw;
			selected = r.id;
			changed();
			inspect();
			draw();
			refreshTools();
			renderMeters();
		});
		label.append(type);
		inspector.append(label);
		const rejection = rejectedFrames.get(r.id);
		if (rejection) inspector.append(make("p", rejection, "amr-frame-error"));
	}
	function inspect() {
		inspector.replaceChildren();
		if (tool === "straighten") {
			inspector.append(make("h3", "Straighten image"), make("p", "Drag a line between two points that should be horizontal. Release to rotate. The line stays visible in this inspector until you draw a new line or reset straightening. The angle is applied to all future images before crop and alignment. Escape cancels the line.", "amr-help"), make("p", `Saved correction: ${(draft.straighten_angle ?? 0).toFixed(2)}°`, "amr-help"), make("p", "Existing frames follow the rotation as enclosing rectangles. Check their bounds afterward. Undo restores the previous angle and frames.", "amr-help"));
			button(inspector, "Reset straightening", () => {
				if (applyStraighten(-(draft.straighten_angle ?? 0))) {
					straightenLine = null;
					draw();
				}
			});
			return;
		}
		if (tool === "pan") {
			inspector.append(make("h3", "Move view"), make("p", "Drag to move the image view. Magenta guides appear when the visible image area is centered horizontally or vertically. The view snaps gently to each center line.", "amr-help"));
			return;
		}
		if (tool === "crop") {
			inspector.append(make("h3", "Crop image"), make("p", "Drag the corner or edge grips to crop. Drag inside the frame to move it. Apply crop to confirm, or Cancel to keep the current area. Keep all alignment and reading regions inside.", "amr-help"));
			const value = { ...cropDraft ?? area() };
			for (const [key, label] of [
				["x", "Crop X"],
				["y", "Crop Y"],
				["width", "Crop width"],
				["height", "Crop height"]
			]) input(inspector, label, value[key], (v) => {
				const n = Number(v);
				const candidate = {
					...value,
					[key]: n
				}, size = dims();
				if (Number.isInteger(n) && candidate.width >= 4 && candidate.height >= 4 && fits(candidate, {
					x: 0,
					y: 0,
					width: size.x,
					height: size.y
				})) {
					value[key] = n;
					cropDraft = { ...value };
					draw();
				} else {
					say("Enter crop bounds inside the image, at least 4 × 4 pixels.", true);
					inspect();
				}
			}, "number");
			const cropActions = make("div", void 0, "amr-inspector-actions");
			inspector.append(cropActions);
			button(cropActions, "Apply crop", () => {
				applyCrop(cropDraft ?? value);
			}, true);
			button(cropActions, "Cancel crop", () => {
				cropDraft = null;
				tool = "select";
				fit();
				refresh();
			});
			button(cropActions, "Reset crop", () => {
				if (!draft.crop) return;
				checkpoint();
				delete draft.crop;
				cropDraft = tool === "crop" ? { ...area() } : null;
				changed();
				fit();
				refresh();
			});
			return;
		}
		const r = selectedRegion();
		inspector.append(make("h3", r ? "Region properties" : "Region inspector"));
		if (!r) {
			inspector.append(make("p", "Drag on empty image space to add a frame. Drag inside a frame to move it, or drag any corner to resize. Select a frame to set its type and properties here.", "amr-help"));
			return;
		}
		input(inspector, "Region name", frameLabel(r), (v) => {
			checkpoint();
			r.name = v;
			changed();
			refreshTools();
			renderMeters();
			draw();
		});
		regionType(r);
		if (r.kind === "alignment") alignmentOptions();
		const coords = make("div", void 0, "amr-coordinate-grid");
		inspector.append(coords);
		for (const [key, label] of [
			["x", "X"],
			["y", "Y"],
			["width", "Width"],
			["height", "Height"]
		]) {
			const f = input(coords, label, r[key], (v) => {
				const value = Number(v);
				dims();
				if (!Number.isInteger(value) || value < (key === "width" || key === "height" ? 4 : 0)) {
					say("Enter a valid whole-pixel coordinate.", true);
					inspect();
					return;
				}
				if (!fits({
					...r,
					[key]: value
				}, area())) {
					say("Region must stay inside the crop.", true);
					inspect();
					return;
				}
				checkpoint();
				r[key] = value;
				changed();
				draw();
			}, "number");
			f.step = "1";
		}
		if (r.kind === "number_block") {
			inspector.append(make("p", "Read one complete printed number. Both OCR variants must agree. Leading zeros are preserved.", "amr-help"));
			const length = input(inspector, "Expected digits (optional)", r.expected_length ?? "", (v) => {
				const n = Number(v);
				if (v !== "" && (!Number.isInteger(n) || n < 1 || n > 32)) {
					say("Expected digits must be between 1 and 32.", true);
					inspect();
					return;
				}
				checkpoint();
				if (v === "") delete r.expected_length;
				else r.expected_length = n;
				changed();
			}, "number");
			length.min = "1";
			length.max = "32";
			length.step = "1";
			const expected = input(inspector, "Expected value (optional)", r.expected_value ?? "", (v) => {
				if (v !== "" && !/^[0-9]{1,32}$/.test(v)) {
					say("Expected value must contain 1 to 32 digits.", true);
					inspect();
					return;
				}
				checkpoint();
				if (v === "") delete r.expected_value;
				else r.expected_value = v;
				changed();
			});
			expected.inputMode = "numeric";
			expected.maxLength = 32;
		}
		if (r.kind === "analog") check(inspector, "Counter-clockwise dial", !!r.ccw, (v) => {
			checkpoint();
			r.ccw = v;
			changed();
		});
		const crop = make("canvas");
		const size = dims();
		if (image) {
			const oriented = make("canvas");
			oriented.width = size.x;
			oriented.height = size.y;
			const c = oriented.getContext("2d");
			c.translate(size.x / 2, size.y / 2);
			c.rotate(((draft.rotation ?? 0) + (draft.straighten_angle ?? 0)) * Math.PI / 180);
			c.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
			crop.width = r.width;
			crop.height = r.height;
			crop.getContext("2d").drawImage(oriented, r.x, r.y, r.width, r.height, 0, 0, r.width, r.height);
			const img = make("img");
			img.src = crop.toDataURL("image/png");
			img.alt = `Reference crop: ${r.name}`;
			img.width = Math.min(230, r.width);
			const preview = make("figure", void 0, "amr-region-preview");
			preview.append(make("figcaption", "Region preview"), img);
			inspector.append(preview);
		}
	}
	function meterLayout(m) {
		if (m.layout) return [...m.layout];
		const assigned = regions().filter((r) => r.meter === m.id && r.kind !== "alignment");
		const digits = assigned.filter((r) => r.kind === "digit").sort((a, b) => a.order - b.order), analog = assigned.filter((r) => r.kind === "analog").sort((a, b) => a.order - b.order);
		const blocks = assigned.filter((r) => r.kind === "number_block");
		if (blocks.length) return [
			...digits,
			...analog,
			...blocks
		].map((r) => r.id);
		const ids = [...digits, ...analog].map((r) => r.id), point = digits.length + (m.decimal_shift ?? 0);
		if (point >= 0 && point < ids.length) ids.splice(point, 0, ",");
		return ids;
	}
	function setLayout(m, tokens) {
		if (tokens.length > 16) {
			say("Use at most 15 frames and one comma.", true);
			renderMeters();
			return;
		}
		if (tokens.filter((id) => id === ",").length > 1) {
			say("A value can contain only one decimal comma.", true);
			renderMeters();
			return;
		}
		const frameIds = tokens.filter((id) => id !== ",");
		const otherUsed = new Set(meters().filter((other) => other.id !== m.id).flatMap((other) => meterLayout(other)));
		if (frameIds.some((id) => otherUsed.has(id))) {
			say("A frame can belong to only one value.", true);
			renderMeters();
			return;
		}
		if (new Set(frameIds).size !== frameIds.length) {
			say("Use each frame only once per value.", true);
			renderMeters();
			return;
		}
		if (frameIds.some((id) => regions().find((r) => r.id === id)?.kind === "number_block") && tokens.length !== 1) {
			say("A Number block is a complete text value. Use it alone, without a comma.", true);
			renderMeters();
			return;
		}
		let analogSeen = false;
		for (const id of frameIds) {
			const r = regions().find((r) => r.id === id);
			if (!r || ![
				"digit",
				"analog",
				"number_block"
			].includes(r.kind)) {
				say("Choose Digit, Analog dial or Number block for each selected frame first.", true);
				renderMeters();
				return;
			}
			if (r.kind === "analog") analogSeen = true;
			else if (analogSeen) {
				say("Place mechanical digits before analog dials for transition correction.", true);
				renderMeters();
				return;
			}
		}
		checkpoint();
		m.layout = [...tokens];
		changed();
		renderMeters();
		draw();
	}
	function renderMeters() {
		valueIds.textContent = meters().map((m) => `${m.name}: ${m.id}`).join(" · ");
		meterCards.replaceChildren();
		const table = make("table", void 0, "amr-value-table");
		const head = make("thead"), header = make("tr");
		for (const title of [
			"Name",
			"Frames in reading order",
			"Actions"
		]) {
			const th = make("th", title);
			th.scope = "col";
			header.append(th);
		}
		head.append(header);
		const body = make("tbody");
		table.append(head, body);
		meterCards.append(table);
		if (!meters().length) {
			const row = make("tr"), cell = make("td", "Add a value, then select its frames from left to right.", "amr-help");
			cell.colSpan = 3;
			row.append(cell);
			body.append(row);
		}
		for (const m of meters()) {
			const row = make("tr"), nameCell = make("td"), card = make("td"), actions = make("td");
			row.append(nameCell, card, actions);
			body.append(row);
			input(nameCell, `Name for ${m.name}`, m.name, (v) => {
				checkpoint();
				m.name = v;
				changed();
			});
			const tokens = meterLayout(m), line = make("div", void 0, "amr-value-builder");
			line.setAttribute("aria-label", `Value layout for ${m.name}`);
			line.tabIndex = 0;
			line.addEventListener("keydown", (event) => {
				if (event.target === line && event.key === ",") {
					event.preventDefault();
					setLayout(m, [...tokens, ","]);
				}
			});
			tokens.forEach((id, index) => {
				const pill = make("div", void 0, id === "," ? "amr-value-pill amr-comma-pill" : "amr-value-pill");
				const r = regions().find((r) => r.id === id);
				if (id === ",") pill.append(make("strong", ","));
				else {
					const select = make("select");
					select.setAttribute("aria-label", `Frame ${index + 1} for ${m.name}`);
					for (const frame of regions().filter((r) => r.kind === "digit" || r.kind === "analog" || r.kind === "number_block")) {
						const option = make("option", frameLabel(frame));
						option.value = frame.id;
						option.title = frame.name;
						select.append(option);
					}
					if (!r || ![
						"digit",
						"analog",
						"number_block"
					].includes(r.kind)) {
						const option = make("option", r ? `${r.name} — choose type` : "Missing frame");
						option.value = id;
						select.append(option);
					}
					select.value = id;
					select.title = r?.name ?? "Missing frame";
					select.addEventListener("change", () => {
						const next = [...tokens];
						next[index] = select.value;
						setLayout(m, next);
					});
					select.addEventListener("keydown", (event) => {
						if (event.key === ",") {
							event.preventDefault();
							const next = [...tokens];
							next.splice(index + 1, 0, ",");
							setLayout(m, next);
						}
					});
					pill.append(select);
				}
				button(pill, "×", () => setLayout(m, tokens.filter((_, i) => i !== index))).setAttribute("aria-label", `Remove item ${index + 1} from ${m.name}`);
				line.append(pill);
			});
			const add = make("select", void 0, "amr-add-pill");
			add.setAttribute("aria-label", `Add frame to ${m.name}`);
			add.title = "Add frame";
			const placeholder = make("option", "+");
			placeholder.value = "";
			add.append(placeholder);
			for (const r of regions().filter((r) => (r.kind === "digit" || r.kind === "analog" || r.kind === "number_block") && !tokens.includes(r.id))) {
				const option = make("option", frameLabel(r));
				option.value = r.id;
				add.append(option);
			}
			add.addEventListener("change", () => {
				if (add.value) setLayout(m, [...tokens, add.value]);
			});
			add.addEventListener("keydown", (event) => {
				if (event.key === ",") {
					event.preventDefault();
					setLayout(m, [...tokens, ","]);
				}
			});
			line.append(add);
			const hasBlock = tokens.some((id) => regions().find((r) => r.id === id)?.kind === "number_block");
			add.disabled = hasBlock;
			const comma = button(line, ",", () => setLayout(m, [...tokens, ","]));
			comma.disabled = hasBlock || tokens.includes(",");
			comma.setAttribute("aria-label", `Add decimal comma to ${m.name}`);
			line.title = hasBlock ? "Number block: complete text value, including leading zeros." : "Select frames in reading order. Type , after a frame or use the comma button.";
			card.append(line);
			if (!m.layout && (m.decimal_shift ?? 0) !== 0) {
				const point = regions().filter((r) => r.meter === m.id && r.kind === "digit").length + (m.decimal_shift ?? 0), length = tokens.filter((t) => t !== ",").length;
				if (point < 0 || point > length) card.append(make("p", `Existing decimal shift ${m.decimal_shift} is preserved until you edit this layout.`, "amr-help"));
			}
			const checksRow = make("tr"), checksCell = make("td");
			checksCell.colSpan = 3;
			checksRow.hidden = true;
			checksRow.append(checksCell);
			body.append(checksRow);
			const rules = make("div", void 0, "amr-rules");
			checksCell.append(rules);
			const checksButton = button(actions, "Rules", () => {
				checksRow.hidden = !checksRow.hidden;
				checksButton.setAttribute("aria-expanded", String(!checksRow.hidden));
			});
			checksButton.setAttribute("aria-label", `Rules for ${m.name}`);
			checksButton.setAttribute("aria-expanded", "false");
			rules.append(make("p", hasBlock ? "Numeric rules do not apply to number blocks. Clear any saved numeric rules before recognition." : "Compare each reading with the supplied previous value. Leave optional limits empty to disable them.", "amr-help"));
			function rule(title, description) {
				const row = make("section", void 0, "amr-rule");
				const info = make("div", void 0, "amr-rule-description");
				info.append(make("strong", title), make("p", description, "amr-help"));
				const fields = make("div", void 0, "amr-rule-fields");
				row.append(info, fields);
				rules.append(row);
				return fields;
			}
			check(rule("Reading direction", "Usually leave off for water and electricity meters. Without a previous value, this rule is not checked."), "Allow lower readings than the previous value", !!m.allow_negative, (v) => {
				checkpoint();
				m.allow_negative = v;
				changed();
			});
			const change = rule("Change between readings", "Reject readings when the absolute change exceeds this limit. Requires a previous value.");
			const rate = rule("Change over time", "Reject changes above the per-minute limit × elapsed minutes, plus tolerance. Requires a previous value and elapsed time. Tolerance requires a rate limit.");
			for (const [parent, key, label] of [
				[
					change,
					"max_change",
					"Maximum change (optional)"
				],
				[
					rate,
					"max_rate",
					"Maximum rate per minute (optional)"
				],
				[
					rate,
					"rate_tolerance",
					"Rate tolerance (optional)"
				]
			]) {
				const field = input(parent, label, m[key] ?? "", (v) => {
					if (v !== "" && (!Number.isFinite(Number(v)) || Number(v) < 0 || Number(v) > 0x38d7ea4c68000)) {
						say("Enter a non-negative value up to 1000000000000000.", true);
						field.value = String(m[key] ?? "");
						return;
					}
					checkpoint();
					if (v === "") delete m[key];
					else m[key] = Number(v);
					changed();
				}, "number");
				field.min = "0";
				field.max = "1000000000000000";
				field.step = "any";
				field.placeholder = key === "rate_tolerance" ? "No extra tolerance" : "No limit";
			}
			const removeMeter = button(actions, "×", () => {
				checkpoint();
				for (const r of regions()) if (r.meter === m.id) delete r.meter;
				draft.meters = meters().filter((other) => other.id !== m.id);
				changed();
				renderMeters();
			});
			removeMeter.setAttribute("aria-label", `Remove value ${m.name}`);
			removeMeter.title = "Remove value";
		}
	}
	async function runPreview() {
		if (busy) return;
		if (tool === "crop" && cropDraft && JSON.stringify(cropDraft) !== JSON.stringify(area())) {
			say("Apply or cancel the crop before running recognition.", true);
			return;
		}
		const referenceId = draft.reference?.asset_id;
		if (!referenceId) {
			say("Upload a reference image first.", true);
			return;
		}
		busy = true;
		refreshImages();
		refreshTools();
		results.replaceChildren();
		rejectedFrames.clear();
		recognizedFrames.clear();
		refreshTools();
		draw();
		const startedRevision = revision;
		runButton.disabled = true;
		say("Aligning image and recognizing regions…");
		try {
			const previous = JSON.parse(previousInput.value || "{}");
			const response = await context.preview({
				image: { asset_id: referenceId },
				previous
			}, structuredClone(draft));
			if (!alive) return;
			if (startedRevision !== revision) {
				say("Configuration changed during preview. Run recognition again.", true);
				return;
			}
			showResults(response);
			say(response.result.status === "read" ? "Preview complete. No MQTT messages were published." : response.result.message ?? "Preview completed with unreadable regions.", response.result.status !== "read");
		} catch (error) {
			say(error instanceof Error ? error.message : "Preview failed.", true);
		} finally {
			busy = false;
			if (alive) {
				runButton.disabled = !draft.reference;
				refreshImages();
				refreshTools();
			}
		}
	}
	function showResults(response) {
		results.replaceChildren();
		rejectedFrames.clear();
		recognizedFrames.clear();
		for (const r of response.result.regions) {
			recognizedFrames.set(r.id, r);
			if (!r.accepted) rejectedFrames.set(r.id, r.reason ?? "Recognition rejected.");
		}
		inspect();
		refreshTools();
		draw();
		for (const reading of response.result.readings) results.append(make("div", reading.value === null ? `${reading.name}: unreadable — ${reading.reason ?? ""}` : `${reading.name}: ${reading.value} ${reading.unit}`, "amr-pill"));
		const reports = response.images.filter((i) => /^recognition-report-\d+\.jpg$/.test(i.name)).sort((a, b) => a.name.localeCompare(b.name));
		for (const [index, file] of reports.entries()) {
			const link = make("a", reports.length === 1 ? "Download recognition report (JPG)" : `Download report page ${index + 1} / ${reports.length} (JPG)`, "amr-report-link");
			link.href = context.previewImageUrl(response.run, file.name);
			link.download = file.name;
			results.append(link);
		}
	}
	function refresh() {
		refreshImages();
		runButton.disabled = busy || !draft.reference;
		refreshTools();
		renderMeters();
		renderOptions();
		inspect();
		draw();
		refreshTools();
	}
	let initialFit = false;
	const resize = new ResizeObserver(() => {
		if (image && !initialFit && viewport.clientWidth > 0 && viewport.clientHeight > 0) {
			initialFit = true;
			fit();
		} else draw();
	});
	resize.observe(viewport);
	refresh();
	loadReference();
	return {
		read: () => {
			if (tool === "crop" && cropDraft && JSON.stringify(cropDraft) !== JSON.stringify(area())) throw new Error("Apply or cancel the crop before saving.");
			if (busy) throw new Error("Wait for the current image operation.");
			return structuredClone(draft);
		},
		dispose: () => {
			alive = false;
			resize.disconnect();
			image = null;
		}
	};
}
export { render };
