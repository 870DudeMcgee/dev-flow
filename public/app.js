document.addEventListener("DOMContentLoaded", () => {
    const simulateBtn = document.getElementById("simulate-btn");
    const termBody = document.getElementById("terminal-stdout");
    const steps = [
        document.getElementById("step-0"),
        document.getElementById("step-1"),
        document.getElementById("step-2"),
        document.getElementById("step-3"),
        document.getElementById("step-4"),
        document.getElementById("step-5")
    ];

    let running = false;

    const logLines = [
        { text: "devflow task claim .devflow/tasks/001_example.md --agent antigravity --lock antigravity-session\n", delay: 800, stepIdx: 0 },
        { text: "🔒 Task claimed by antigravity under lock antigravity-session.\n", delay: 600, stepIdx: 0, completedIdx: 0 },
        { text: "🔍 Checking git status for clean worktree...\n", delay: 800, stepIdx: 1 },
        { text: "📂 Git worktree: [CLEAN] - 0 dirty files detected.\n", delay: 600, stepIdx: 1, completedIdx: 1 },
        { text: "🌿 Creating safe git checkpoint branch: devflow/task-001...\n", delay: 800, stepIdx: 2 },
        { text: "🌿 Checkpoint branch created. Base branch: main.\n", delay: 600, stepIdx: 2, completedIdx: 2 },
        { text: "📝 Extracting and validating unified diff block from task markdown...\n", delay: 1000, stepIdx: 3 },
        { text: "✅ Patch dry-run passed: 1 file parsed, 0 protected paths touched.\n", delay: 600, stepIdx: 3, completedIdx: 3 },
        { text: "🚀 Applying unified diff and running verification...\n", delay: 1200, stepIdx: 4 },
        { text: "🛠️  Running verification command: PYTHONPATH=src python3 -m unittest discover -s tests -q\n", delay: 1000, stepIdx: 4 },
        { text: "   Ran 35 tests in 4.721s -> OK\n", delay: 800, stepIdx: 4, completedIdx: 4 },
        { text: "📝 Writing final audit report to .devflow/reports/001.report.md...\n", delay: 800, stepIdx: 5 },
        { text: "🎉 Task completed successfully! Status transitioned: RUNNING -> COMPLETED.\n", delay: 500, stepIdx: 5, completedIdx: 5 }
    ];

    simulateBtn.addEventListener("click", async () => {
        if (running) return;
        running = true;
        simulateBtn.disabled = true;
        simulateBtn.innerText = "Simulating...";

        // Reset Terminal
        termBody.innerHTML = '<span class="term-prompt">devflow$</span> ';
        steps.forEach(step => {
            step.classList.remove("active", "completed");
        });
        steps[0].classList.add("active");

        // Typewriter prompt output
        const promptCmd = "PYTHONPATH=src python3 -m devflow run .devflow/tasks/001_example.md --yes\n";
        await typeText(promptCmd, "term-command");

        // Run through log logs
        for (const log of logLines) {
            await sleep(log.delay);
            
            // Manage Steps classes
            if (log.stepIdx !== undefined) {
                steps.forEach((s, idx) => {
                    if (idx === log.stepIdx) s.classList.add("active");
                    else s.classList.remove("active");
                });
            }
            if (log.completedIdx !== undefined) {
                steps[log.completedIdx].classList.add("completed");
            }

            // Append Output Line
            const lineSpan = document.createElement("span");
            lineSpan.innerText = log.text;
            if (log.text.includes("OK") || log.text.includes("success") || log.text.includes("passed")) {
                lineSpan.style.color = "#10b981"; // green
            } else if (log.text.includes("claim") || log.text.includes("Creating")) {
                lineSpan.style.color = "#6366f1"; // indigo
            }
            termBody.appendChild(lineSpan);
            termBody.scrollTop = termBody.scrollHeight;
        }

        // Complete state
        steps.forEach(s => s.classList.remove("active"));
        simulateBtn.disabled = false;
        simulateBtn.innerText = "Run Another Simulation";
        running = false;
    });

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function typeText(text, className) {
        return new Promise(resolve => {
            let i = 0;
            const container = document.createElement("span");
            if (className) container.className = className;
            termBody.appendChild(container);

            const interval = setInterval(() => {
                if (i < text.length) {
                    container.innerText += text[i];
                    termBody.scrollTop = termBody.scrollHeight;
                    i++;
                } else {
                    clearInterval(interval);
                    resolve();
                }
            }, 30);
        });
    });
});
