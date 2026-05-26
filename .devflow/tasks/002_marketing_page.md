# Task: 002 - Build devflow marketing landing page
Status: PREVIEWED
Goal: devflow_marketing_launch
Plan: 002_marketing_page.plan.json
Assigned Agent: antigravity
Owner Lock: antigravity-session-002
Risk: LOW
Branch: devflow/task-002-antigravity
Touched Files:
- public/index.html
- public/styles.css
- public/app.js

## 1. Objective

Build a beautiful, modern, single-page marketing website for `devflow` inside `public/` that explains its value proposition and features an interactive terminal simulator of the safety contract pipeline.

## 2. Allowed Files

- public/index.html
- public/styles.css
- public/app.js

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Use Vanilla CSS and core HTML + JS (no frameworks or Tailwind CSS).
- Styling should be extremely premium (dark mode, glassmorphism, HSL custom neon colors, micro-animations, Inter font).
- The pipeline simulator should dynamically cycle active states and output log texts.

## 5. Implementation Instructions

Create index.html, styles.css, and app.js inside `public/`.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- test -f public/index.html
- test -f public/styles.css
- test -f public/app.js

## 8. Failure Handling

- Rollback on failure.

## 9. Execution Results

```diff
diff --git a/public/app.js b/public/app.js
new file mode 100644
index 0000000..f101fe4
--- /dev/null
+++ b/public/app.js
@@ -0,0 +1,105 @@
+document.addEventListener("DOMContentLoaded", () => {
+    const simulateBtn = document.getElementById("simulate-btn");
+    const termBody = document.getElementById("terminal-stdout");
+    const steps = [
+        document.getElementById("step-0"),
+        document.getElementById("step-1"),
+        document.getElementById("step-2"),
+        document.getElementById("step-3"),
+        document.getElementById("step-4"),
+        document.getElementById("step-5")
+    ];
+
+    let running = false;
+
+    const logLines = [
+        { text: "devflow task claim .devflow/tasks/001_example.md --agent antigravity --lock antigravity-session\n", delay: 800, stepIdx: 0 },
+        { text: "🔒 Task claimed by antigravity under lock antigravity-session.\n", delay: 600, stepIdx: 0, completedIdx: 0 },
+        { text: "🔍 Checking git status for clean worktree...\n", delay: 800, stepIdx: 1 },
+        { text: "📂 Git worktree: [CLEAN] - 0 dirty files detected.\n", delay: 600, stepIdx: 1, completedIdx: 1 },
+        { text: "🌿 Creating safe git checkpoint branch: devflow/task-001...\n", delay: 800, stepIdx: 2 },
+        { text: "🌿 Checkpoint branch created. Base branch: main.\n", delay: 600, stepIdx: 2, completedIdx: 2 },
+        { text: "📝 Extracting and validating unified diff block from task markdown...\n", delay: 1000, stepIdx: 3 },
+        { text: "✅ Patch dry-run passed: 1 file parsed, 0 protected paths touched.\n", delay: 600, stepIdx: 3, completedIdx: 3 },
+        { text: "🚀 Applying unified diff and running verification...\n", delay: 1200, stepIdx: 4 },
+        { text: "🛠️  Running verification command: PYTHONPATH=src python3 -m unittest discover -s tests -q\n", delay: 1000, stepIdx: 4 },
+        { text: "   Ran 35 tests in 4.721s -> OK\n", delay: 800, stepIdx: 4, completedIdx: 4 },
+        { text: "📝 Writing final audit report to .devflow/reports/001.report.md...\n", delay: 800, stepIdx: 5 },
+        { text: "🎉 Task completed successfully! Status transitioned: RUNNING -> COMPLETED.\n", delay: 500, stepIdx: 5, completedIdx: 5 }
+    ];
+
+    simulateBtn.addEventListener("click", async () => {
+        if (running) return;
+        running = true;
+        simulateBtn.disabled = true;
+        simulateBtn.innerText = "Simulating...";
+
+        // Reset Terminal
+        termBody.innerHTML = '<span class="term-prompt">devflow$</span> ';
+        steps.forEach(step => {
+            step.classList.remove("active", "completed");
+        });
+        steps[0].classList.add("active");
+
+        // Typewriter prompt output
+        const promptCmd = "PYTHONPATH=src python3 -m devflow run .devflow/tasks/001_example.md --yes\n";
+        await typeText(promptCmd, "term-command");
+
+        // Run through log logs
+        for (const log of logLines) {
+            await sleep(log.delay);
+            
+            // Manage Steps classes
+            if (log.stepIdx !== undefined) {
+                steps.forEach((s, idx) => {
+                    if (idx === log.stepIdx) s.classList.add("active");
+                    else s.classList.remove("active");
+                });
+            }
+            if (log.completedIdx !== undefined) {
+                steps[log.completedIdx].classList.add("completed");
+            }
+
+            // Append Output Line
+            const lineSpan = document.createElement("span");
+            lineSpan.innerText = log.text;
+            if (log.text.includes("OK") || log.text.includes("success") || log.text.includes("passed")) {
+                lineSpan.style.color = "#10b981"; // green
+            } else if (log.text.includes("claim") || log.text.includes("Creating")) {
+                lineSpan.style.color = "#6366f1"; // indigo
+            }
+            termBody.appendChild(lineSpan);
+            termBody.scrollTop = termBody.scrollHeight;
+        }
+
+        // Complete state
+        steps.forEach(s => s.classList.remove("active"));
+        simulateBtn.disabled = false;
+        simulateBtn.innerText = "Run Another Simulation";
+        running = false;
+    });
+
+    function sleep(ms) {
+        return new Promise(resolve => setTimeout(resolve, ms));
+    }
+
+    function typeText(text, className) {
+        return new Promise(resolve => {
+            let i = 0;
+            const container = document.createElement("span");
+            if (className) container.className = className;
+            termBody.appendChild(container);
+
+            const interval = setInterval(() => {
+                if (i < text.length) {
+                    container.innerText += text[i];
+                    termBody.scrollTop = termBody.scrollHeight;
+                    i++;
+                } else {
+                    clearInterval(interval);
+                    resolve();
+                }
+            }, 30);
+        });
+    });
+});
diff --git a/public/index.html b/public/index.html
new file mode 100644
index 0000000..84c7659
--- /dev/null
+++ b/public/index.html
@@ -0,0 +1,100 @@
+<!DOCTYPE html>
+<html lang="en">
+<head>
+    <meta charset="UTF-8">
+    <meta name="viewport" content="width=device-width, initial-scale=1.0">
+    <title>devflow | Safe Multi-Agent Workflows</title>
+    <meta name="description" content="A safe, vendor-neutral execution and coordination engine for AI-generated unified diffs. Prevent collisions across Codex, Cline, and Antigravity automatically.">
+    <link rel="preconnect" href="https://fonts.googleapis.com">
+    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
+    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
+    <link rel="stylesheet" href="styles.css">
+</head>
+<body>
+    <header class="header">
+        <div class="logo">
+            <span class="logo-icon">🌿</span> devflow
+        </div>
+        <nav class="nav">
+            <a href="#features">Features</a>
+            <a href="#simulator">Simulator</a>
+            <a href="#docs" class="cta-nav">Docs</a>
+        </nav>
+    </header>
+
+    <main class="container">
+        <!-- Hero Section -->
+        <section class="hero">
+            <div class="hero-glow"></div>
+            <h1 class="hero-title">Safe, Collaborative<br><span class="gradient-text">Multi-Agent Development</span></h1>
+            <p class="hero-subtitle">The vendor-neutral orchestration plane that executes AI patches safely using git-native unified diffs, auto-rollbacks, and explicit safety checkpoints.</p>
+            <div class="hero-actions">
+                <a href="#simulator" class="btn btn-primary" id="btn-hero-simulate">Start Simulation</a>
+                <a href="#features" class="btn btn-secondary">Learn More</a>
+            </div>
+        </section>
+
+        <!-- Features Grid -->
+        <section id="features" class="features">
+            <h2 class="section-title">Built for the Autonomous Era</h2>
+            <div class="grid">
+                <div class="card glass">
+                    <div class="card-icon">🔒</div>
+                    <h3>Zero-Trust Gated Apply</h3>
+                    <p>Previews patches by default to generate detailed safety audits. Explicit approval via <code>--yes</code> is required to mutate any codebase files.</p>
+                </div>
+                <div class="card glass">
+                    <div class="card-icon">🌿</div>
+                    <h3>Automated Git Checkpoints</h3>
+                    <p>Creates automatic recovery branches before applying any edit. Automatically rolls back to the clean checkpoint if any unit test, linter, or typecheck fails.</p>
+                </div>
+                <div class="card glass">
+                    <div class="card-icon">⚔️</div>
+                    <h3>Multi-Orchestrator Lock</h3>
+                    <p>Allows Codex Desktop, VS Code/Cline, and Google Antigravity to act as peer dev teams coordinating seamlessly without stepping on each other's code.</p>
+                </div>
+            </div>
+        </section>
+
+        <!-- Simulator Section -->
+        <section id="simulator" class="simulator-section">
+            <h2 class="section-title">See the Safety Loop in Action</h2>
+            <p class="section-subtitle">Experience how devflow's execution pipeline behaves when a peer orchestrator claims a task and applies an edit.</p>
+            
+            <div class="terminal-layout glass">
+                <div class="terminal-sidebar">
+                    <div class="sidebar-header">Safety Pipeline</div>
+                    <ul class="pipeline-steps">
+                        <li class="step active" id="step-0">Claim & Lock Task</li>
+                        <li class="step" id="step-1">Verify Clean Worktree</li>
+                        <li class="step" id="step-2">Create Git Checkpoint</li>
+                        <li class="step" id="step-3">Validate Patch Structure</li>
+                        <li class="step" id="step-4">Apply & Verify Tests</li>
+                        <li class="step" id="step-5">Save Audit Report</li>
+                    </ul>
+                </div>
+                <div class="terminal-main">
+                    <div class="terminal-header">
+                        <div class="terminal-buttons">
+                            <span></span><span></span><span></span>
+                        </div>
+                        <div class="terminal-title">bash - devflow run --yes</div>
+                    </div>
+                    <div class="terminal-body" id="terminal-stdout">
+                        <span class="term-prompt">devflow$</span> <span class="term-cursor"></span>
+                    </div>
+                    <div class="terminal-footer">
+                        <button class="btn btn-primary" id="simulate-btn">Run Task Simulation</button>
+                    </div>
+                </div>
+            </div>
+        </section>
+    </main>
+
+    <footer class="footer">
+        <p>&copy; 2026 devflow open-source protocol. Coordinated by peer AI orchestrators.</p>
+    </footer>
+
+    <script src="app.js"></script>
+</body>
+</html>
diff --git a/public/styles.css b/public/styles.css
new file mode 100644
index 0000000..7d4df6f
--- /dev/null
+++ b/public/styles.css
@@ -0,0 +1,402 @@
+/* Core Styling Variables */
+:root {
+    --bg-dark: #07090e;
+    --bg-card: #0f131a;
+    --border-color: rgba(255, 255, 255, 0.08);
+    --text-primary: #f8fafc;
+    --text-secondary: #94a3b8;
+    --accent-indigo: #6366f1;
+    --accent-violet: #a855f7;
+    --accent-green: #10b981;
+    --accent-red: #ef4444;
+    --font-sans: 'Inter', sans-serif;
+    --font-mono: 'JetBrains Mono', monospace;
+}
+
+/* Reset */
+* {
+    margin: 0;
+    padding: 0;
+    box-sizing: border-box;
+}
+
+html {
+    scroll-behavior: smooth;
+}
+
+body {
+    background-color: var(--bg-dark);
+    color: var(--text-primary);
+    font-family: var(--font-sans);
+    line-height: 1.6;
+    overflow-x: hidden;
+    background: radial-gradient(circle at 50% 0%, #171635 0%, #030712 60%);
+}
+
+/* Header */
+.header {
+    display: flex;
+    justify-content: space-between;
+    align-items: center;
+    padding: 1.5rem 2rem;
+    border-bottom: 1px solid var(--border-color);
+    background: rgba(7, 9, 14, 0.6);
+    backdrop-filter: blur(10px);
+    position: sticky;
+    top: 0;
+    z-index: 100;
+}
+
+.logo {
+    font-size: 1.4rem;
+    font-weight: 800;
+    display: flex;
+    align-items: center;
+    gap: 0.5rem;
+    letter-spacing: -0.5px;
+}
+
+.nav {
+    display: flex;
+    align-items: center;
+    gap: 2rem;
+}
+
+.nav a {
+    color: var(--text-secondary);
+    text-decoration: none;
+    font-size: 0.95rem;
+    transition: color 0.2s ease;
+}
+
+.nav a:hover {
+    color: var(--text-primary);
+}
+
+.cta-nav {
+    background: var(--accent-indigo);
+    color: var(--text-primary) !important;
+    padding: 0.5rem 1.2rem;
+    border-radius: 6px;
+    font-weight: 600;
+    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
+}
+
+/* Grid & Layout */
+.container {
+    max-width: 1100px;
+    margin: 0 auto;
+    padding: 2rem;
+}
+
+/* Hero Section */
+.hero {
+    position: relative;
+    text-align: center;
+    padding: 8rem 1rem 6rem 1rem;
+    display: flex;
+    flex-direction: column;
+    align-items: center;
+}
+
+.hero-glow {
+    position: absolute;
+    top: -10%;
+    width: 600px;
+    height: 300px;
+    background: radial-gradient(ellipse at center, rgba(168, 85, 247, 0.15) 0%, rgba(0,0,0,0) 70%);
+    filter: blur(40px);
+    z-index: -1;
+}
+
+.hero-title {
+    font-size: 3.5rem;
+    font-weight: 800;
+    line-height: 1.15;
+    margin-bottom: 1.5rem;
+    letter-spacing: -1.5px;
+}
+
+.gradient-text {
+    background: linear-gradient(135deg, var(--accent-indigo) 0%, var(--accent-violet) 100%);
+    -webkit-background-clip: text;
+    -webkit-text-fill-color: transparent;
+}
+
+.hero-subtitle {
+    font-size: 1.25rem;
+    color: var(--text-secondary);
+    max-width: 720px;
+    margin-bottom: 2.5rem;
+}
+
+.hero-actions {
+    display: flex;
+    gap: 1rem;
+}
+
+/* Buttons */
+.btn {
+    padding: 0.75rem 1.8rem;
+    border-radius: 8px;
+    font-weight: 600;
+    text-decoration: none;
+    transition: all 0.2s ease;
+    cursor: pointer;
+    font-size: 1rem;
+    display: inline-block;
+    border: none;
+}
+
+.btn-primary {
+    background: linear-gradient(135deg, var(--accent-indigo) 0%, #4f46e5 100%);
+    color: var(--text-primary);
+    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
+}
+
+.btn-primary:hover {
+    transform: translateY(-2px);
+    box-shadow: 0 6px 24px rgba(99, 102, 241, 0.5);
+}
+
+.btn-secondary {
+    background: rgba(255, 255, 255, 0.05);
+    border: 1px solid var(--border-color);
+    color: var(--text-primary);
+}
+
+.btn-secondary:hover {
+    background: rgba(255, 255, 255, 0.08);
+}
+
+/* Glassmorphism Cards */
+.glass {
+    background: rgba(15, 19, 26, 0.4);
+    backdrop-filter: blur(12px);
+    -webkit-backdrop-filter: blur(12px);
+    border: 1px solid var(--border-color);
+    border-radius: 12px;
+}
+
+.features {
+    padding: 4rem 0;
+}
+
+.section-title {
+    font-size: 2.2rem;
+    font-weight: 800;
+    text-align: center;
+    margin-bottom: 3rem;
+    letter-spacing: -0.5px;
+}
+
+.section-subtitle {
+    font-size: 1.1rem;
+    color: var(--text-secondary);
+    text-align: center;
+    max-width: 600px;
+    margin: -2rem auto 3rem auto;
+}
+
+.grid {
+    display: grid;
+    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
+    gap: 2rem;
+}
+
+.card {
+    padding: 2.5rem;
+    transition: all 0.3s ease;
+}
+
+.card:hover {
+    transform: translateY(-5px);
+    border-color: rgba(99, 102, 241, 0.3);
+    box-shadow: 0 10px 30px rgba(99, 102, 241, 0.1);
+}
+
+.card-icon {
+    font-size: 2rem;
+    margin-bottom: 1.25rem;
+}
+
+.card h3 {
+    font-size: 1.3rem;
+    margin-bottom: 0.75rem;
+}
+
+.card p {
+    color: var(--text-secondary);
+    font-size: 0.95rem;
+}
+
+/* Terminal Simulator */
+.simulator-section {
+    padding: 6rem 0;
+}
+
+.terminal-layout {
+    display: grid;
+    grid-template-columns: 280px 1fr;
+    min-height: 400px;
+    overflow: hidden;
+    box-shadow: 0 20px 50px rgba(0,0,0,0.5);
+}
+
+.terminal-sidebar {
+    background: rgba(10, 12, 18, 0.8);
+    border-right: 1px solid var(--border-color);
+    padding: 2rem;
+}
+
+.sidebar-header {
+    font-size: 0.8rem;
+    font-weight: 800;
+    text-transform: uppercase;
+    letter-spacing: 1px;
+    color: var(--text-secondary);
+    margin-bottom: 1.5rem;
+}
+
+.pipeline-steps {
+    list-style: none;
+    display: flex;
+    flex-direction: column;
+    gap: 0.75rem;
+}
+
+.pipeline-steps .step {
+    padding: 0.5rem 0.75rem;
+    border-radius: 6px;
+    font-size: 0.9rem;
+    color: var(--text-secondary);
+    transition: all 0.3s ease;
+    display: flex;
+    align-items: center;
+    gap: 0.5rem;
+}
+
+.pipeline-steps .step::before {
+    content: "○";
+    color: var(--text-secondary);
+    font-weight: bold;
+}
+
+.pipeline-steps .step.active {
+    color: var(--text-primary);
+    background: rgba(99, 102, 241, 0.1);
+    font-weight: 600;
+}
+
+.pipeline-steps .step.active::before {
+    content: "●";
+    color: var(--accent-indigo);
+}
+
+.pipeline-steps .step.completed {
+    color: var(--accent-green);
+}
+
+.pipeline-steps .step.completed::before {
+    content: "✓";
+    color: var(--accent-green);
+}
+
+.terminal-main {
+    display: flex;
+    flex-direction: column;
+    background: rgba(5, 6, 10, 0.95);
+}
+
+.terminal-header {
+    display: flex;
+    align-items: center;
+    padding: 0.75rem 1.25rem;
+    background: rgba(15, 17, 26, 0.9);
+    border-bottom: 1px solid var(--border-color);
+    position: relative;
+}
+
+.terminal-buttons {
+    display: flex;
+    gap: 6px;
+}
+
+.terminal-buttons span {
+    width: 12px;
+    height: 12px;
+    border-radius: 50%;
+    display: inline-block;
+}
+
+.terminal-buttons span:nth-child(1) { background-color: var(--accent-red); }
+.terminal-buttons span:nth-child(2) { background-color: #f59e0b; }
+.terminal-buttons span:nth-child(3) { background-color: var(--accent-green); }
+
+.terminal-title {
+    margin: 0 auto;
+    font-family: var(--font-mono);
+    font-size: 0.8rem;
+    color: var(--text-secondary);
+}
+
+.terminal-body {
+    flex-grow: 1;
+    padding: 1.5rem;
+    font-family: var(--font-mono);
+    font-size: 0.9rem;
+    color: #cbd5e1;
+    white-space: pre-wrap;
+    overflow-y: auto;
+    max-height: 320px;
+}
+
+.term-prompt {
+    color: var(--accent-indigo);
+    font-weight: bold;
+}
+
+.term-cursor {
+    display: inline-block;
+    width: 8px;
+    height: 15px;
+    background-color: var(--text-primary);
+    animation: blink 1s infinite;
+    vertical-align: middle;
+}
+
+.terminal-footer {
+    padding: 1rem 1.5rem;
+    border-top: 1px solid var(--border-color);
+    background: rgba(10, 12, 18, 0.5);
+    display: flex;
+    justify-content: flex-end;
+}
+
+@keyframes blink {
+    0%, 100% { opacity: 0; }
+    50% { opacity: 1; }
+}
+
+/* Footer */
+.footer {
+    text-align: center;
+    padding: 4rem 2rem;
+    border-top: 1px solid var(--border-color);
+    color: var(--text-secondary);
+    font-size: 0.9rem;
+}
+
+/* Responsiveness */
+@media (max-width: 768px) {
+    .terminal-layout {
+        grid-template-columns: 1fr;
+    }
+    .terminal-sidebar {
+        border-right: none;
+        border-bottom: 1px solid var(--border-color);
+    }
+    .hero-title {
+        font-size: 2.5rem;
+    }
+}
```

## 10. Final Report

Pending.
