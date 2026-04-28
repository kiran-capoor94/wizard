---
name: wizard-playground
description: Use when the user asks for any architecture diagram, sequence diagram, ERD, flowchart, state machine, or visual system diagram. Also use when a mode's trigger table routes a diagram request here.
---

# Wizard Playground — Mermaid Diagram Workbench

## What You Produce

A single self-contained HTML file (~80 lines), written to `<descriptive-name>.html`, then opened with `open <filename>.html`.

The file contains:
- A **left panel** (40% width) with an editable textarea pre-loaded with the Mermaid source
- A **right panel** (flex: 1) with the live-rendered diagram
- A **toolbar** with a preset selector (C4 Context, Sequence, ERD, Flowchart, State Machine), a Copy Source button, and a Copy SVG button
- Live re-render on every keystroke (`oninput`)
- Dark theme throughout

## Full HTML Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Wizard Diagram Playground</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { display: flex; flex-direction: column; height: 100vh;
         background: #1a1a1a; color: #e0e0e0; font-family: monospace; }
  #toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px;
             background: #111; border-bottom: 1px solid #333; }
  #toolbar select, #toolbar button {
    background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;
    padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 13px; }
  #toolbar button:hover { background: #3a3a3a; }
  #main { display: flex; flex: 1; overflow: hidden; }
  #editor { width: 40%; border-right: 1px solid #333; display: flex; flex-direction: column; }
  #source { flex: 1; background: #111; color: #ccc; border: none; outline: none;
            padding: 12px; font-family: monospace; font-size: 13px; resize: none; }
  #preview { flex: 1; overflow: auto; padding: 24px; display: flex;
             align-items: flex-start; justify-content: center; }
  #output svg { max-width: 100%; height: auto; }
  #error { color: #f66; font-size: 12px; padding: 4px 12px; background: #1a1a1a;
           border-top: 1px solid #333; min-height: 22px; }
</style>
</head>
<body>
<div id="toolbar">
  <label for="preset" style="font-size:13px">Preset:</label>
  <select id="preset" onchange="loadPreset(this.value)">
    <option value="flowchart">Flowchart</option>
    <option value="sequence">Sequence</option>
    <option value="erd">ERD</option>
    <option value="state">State Machine</option>
    <option value="c4">C4 Context</option>
  </select>
  <button id="btnCopySource" onclick="copySource()">Copy Source</button>
  <button id="btnCopySVG" onclick="copySVG()">Copy SVG</button>
</div>
<div id="main">
  <div id="editor">
    <textarea id="source" oninput="scheduleRender()" spellcheck="false"></textarea>
    <div id="error"></div>
  </div>
  <div id="preview"><div id="output"></div></div>
</div>
<script>
mermaid.initialize({ startOnLoad: false, theme: 'dark' });

let debounceTimer;
function scheduleRender() { clearTimeout(debounceTimer); debounceTimer = setTimeout(render, 300); }

const PRESETS = {
  flowchart: `flowchart TD
    A[Start] --> B{Decision}
    B -- Yes --> C[Action A]
    B -- No --> D[Action B]
    C --> E[End]
    D --> E`,
  sequence: `sequenceDiagram
    participant Client
    participant API
    participant DB
    Client->>API: POST /request
    API->>DB: query()
    DB-->>API: rows
    API-->>Client: 200 OK`,
  erd: `erDiagram
    USER ||--o{ ORDER : places
    ORDER ||--|{ LINE_ITEM : contains
    PRODUCT }|--|{ LINE_ITEM : included_in`,
  state: `stateDiagram-v2
    [*] --> Idle
    Idle --> Processing : start
    Processing --> Done : complete
    Processing --> Error : fail
    Error --> Idle : reset
    Done --> [*]`,
  c4: `C4Context
    title System Context — My App
    Person(user, "User", "End user")
    System(app, "My App", "Core application")
    System_Ext(ext, "External Service", "Third-party API")
    Rel(user, app, "Uses")
    Rel(app, ext, "Calls")`
};

let renderCount = 0;

async function render() {
  const src = document.getElementById('source').value.trim();
  const out = document.getElementById('output');
  const err = document.getElementById('error');
  err.textContent = '';
  while (out.firstChild) out.removeChild(out.firstChild);
  if (!src) return;
  const id = 'mermaid-' + (++renderCount);
  const node = document.createElement('div');
  node.id = id;
  node.className = 'mermaid';
  node.textContent = src;
  out.appendChild(node);
  try {
    await mermaid.run({ nodes: [node] });
  } catch (e) {
    while (out.firstChild) out.removeChild(out.firstChild);
    err.textContent = e.message || 'Parse error';
  }
}

function loadPreset(key) {
  document.getElementById('source').value = PRESETS[key] || '';
  render();
}

function copySource() {
  navigator.clipboard.writeText(document.getElementById('source').value)
    .then(() => flashButton('btnCopySource', 'Copied!'))
    .catch(() => flashButton('btnCopySource', 'Failed'));
}
function copySVG() {
  const svg = document.getElementById('output').querySelector('svg');
  if (!svg) return;
  navigator.clipboard.writeText(svg.outerHTML)
    .then(() => flashButton('btnCopySVG', 'Copied!'))
    .catch(() => flashButton('btnCopySVG', 'Failed'));
}
function flashButton(id, label) {
  const btn = document.getElementById(id);
  const orig = btn.textContent;
  btn.textContent = label;
  setTimeout(() => { btn.textContent = orig; }, 1200);
}

loadPreset('flowchart');
</script>
</body>
</html>
```

## Workflow

1. **Understand** what the user wants to diagram — ask one clarifying question if the scope is ambiguous.
2. **Choose the closest preset** as the starting point (flowchart, sequence, ERD, state machine, or C4 context).
3. **Write the Mermaid source** for the user's specific diagram. Replace the body of the matching PRESETS entry with the user's diagram source (e.g. replace the `flowchart` string with the actual diagram). Then call `loadPreset('<matching-key>')` at the end so the correct preset tab is selected on load.
4. **Write the HTML file** — use a descriptive filename, e.g. `api-layers-diagram.html` or `login-sequence.html`.
5. **Run `open <filename>.html`** to open it in the browser.
6. **Tell the user** they can edit the source in the left panel to update the diagram live, and use the toolbar to switch presets or copy output.

## What NOT to Do

- Do NOT generate raw SVG `<path>` elements — Mermaid handles all SVG generation
- Do NOT use the superpowers playground skill — that is for UI/UX playgrounds, not diagrams
- Do NOT output Mermaid source as a fenced code block only — always produce the HTML file
- Do NOT suggest mermaid.live or any external tool — the file is fully self-contained and opens locally
- Do NOT output source-only because the user says "just show me the source" — always produce the HTML file; the user can copy source from the left panel using the Copy Source button
