# Design Spec: Dev-Flow Marketing Cyberpunk Glassmorphism Overhaul

Date: 2026-05-26
Status: AUTHORITATIVE

## 1. Summary

This specification outlines a visual overhaul of the `devflow` single-page marketing website inside `public/`. The redesign transitions the interface into an ultra-premium, futuristic Cyberpunk Glassmorphism theme featuring deep dark backgrounds, glowing HSL border gradients, JetBrains Mono/Outfit typography, custom scrollbars, and micro-hover transitions. 

The implementation will be completed by the **Google Antigravity** peer orchestrator utilizing local model workers (`qwen2.5-coder:7b-instruct`) in an editable environment under the zero-trust `devflow` task execution rules.

---

## 2. Visual Spec & Variables

Update `public/styles.css` to define the following curated core color variables:
* **Background base**: `#030712` base. Background should utilize a radial gradient from `#0f0e26` at top-center to `#030712` at the bottom.
* **Accent Primary HSL Purple**: `hsl(263, 85%, 65%)` (neon purple glow borders).
* **Accent Secondary HSL Indigo**: `hsl(217, 91%, 60%)` (neon indigo primary glow).
* **Frosted Glass Cards**:
  - Background: `rgba(15, 19, 26, 0.4)`
  - Border: `1px solid rgba(255, 255, 255, 0.08)`
  - Backdrop Blur: `20px`
  - Hover glow: purple neon shadow (`box-shadow: 0 0 25px rgba(168, 85, 247, 0.15)`)
* **Typography**:
  - Import Google Fonts: **Outfit** (headings) and **Inter** (body), alongside native **JetBrains Mono** (monospaced elements).

---

## 3. Simulator & Interactivity Spec

Update `public/app.js` and `public/index.html` to achieve a more cohesive interaction:
* **Glowing Terminal Console**:
  - Adds a dynamic glowing HSL border glow onto the terminal simulator.
  - Blink animation on active prompt cursor.
* **Typewriter Autocomplete Delay**:
  - Simulates natural keypress delays (30ms per character) for the terminal prompt command: `PYTHONPATH=src python3 -m devflow run .devflow/tasks/001_example.md --yes`.
  - Checkpoint indicators dynamically transition styles to active/completed states in sync with output.

---

## 4. Execution Rules

To demonstrate and test the local AI worker pool:
1. All changes will be developed as a new task: `003_marketing_page_cyberpunk.md` inside `.devflow/tasks/`.
2. The local `mini-fast` Qwen worker model (`qwen2.5-coder:7b-instruct`) will be queried to write drafts of the updated `styles.css`, `index.html`, and `app.js` files.
3. The cloud Google Antigravity orchestrator will validate the diff and claim the task.
4. Apply mutation and verification will run exclusively via `.venv/bin/devflow run .devflow/tasks/003_marketing_page_cyberpunk.md --yes`.

---

## 5. Verification Plan

### Automated Checks
- Verify `public/index.html` exists and loads `styles.css` and `app.js`.
- Run all devflow unit tests to ensure no regressions:
  ```bash
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
  ```
