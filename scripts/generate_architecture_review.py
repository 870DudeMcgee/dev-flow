import os
import sys
import tempfile
import time
import subprocess

def generate_report():
    timestamp = int(time.time())
    temp_dir = tempfile.gettempdir()
    report_path = os.path.join(temp_dir, f"architecture-review-{timestamp}.html")
    
    html_content = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Architecture Review — devflow</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans leading-relaxed">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <!-- Header -->
      <header class="border-b border-stone-200 pb-6">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 class="text-3xl font-bold tracking-tight text-slate-900 font-serif">Architecture Review — devflow</h1>
            <p class="text-sm text-slate-500 mt-1">Reviewing codebase depth, seams, and leakage to improve testability and AI-navigability.</p>
          </div>
          <div class="text-right">
            <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Date</span>
            <p class="text-sm font-medium text-slate-700">2026-05-27</p>
          </div>
        </div>

        <!-- Compact Legend -->
        <div class="mt-6 flex flex-wrap gap-4 items-center bg-white p-3 rounded-lg border border-stone-200 text-xs text-slate-600">
          <span class="font-semibold uppercase tracking-wider text-slate-400 mr-2 text-[10px]">Legend:</span>
          <div class="flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 border border-slate-400 bg-stone-100 rounded inline-block"></span>
            <span>Module</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 border border-dashed border-slate-500 rounded inline-block"></span>
            <span>Seam</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="text-red-600 font-bold font-mono">&rarr;</span>
            <span>Leakage</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 deep rounded inline-block"></span>
            <span>Deep Module</span>
          </div>
        </div>
      </header>

      <!-- Candidates list -->
      <section id="candidates" class="space-y-12">
        
        <!-- Candidate 1: Safety Auditing Engine -->
        <article class="bg-white rounded-xl border border-stone-200 shadow-sm overflow-hidden p-6 space-y-6">
          <div class="flex flex-wrap items-center justify-between gap-4 border-b border-stone-100 pb-4">
            <div class="space-y-1">
              <h2 class="text-xl font-bold text-slate-900 font-serif">1. Deepen the Safety Auditing System</h2>
              <div class="flex gap-2">
                <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">Strong Recommendation</span>
                <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700 border border-slate-200">in-process</span>
              </div>
            </div>
            <div class="font-mono text-xs text-slate-500 bg-stone-50 p-2 rounded border border-stone-200">
              src/devflow/safety.py<br>
              src/devflow/cli.py<br>
              src/devflow/agents/runner.py
            </div>
          </div>

          <!-- Before/After Visualization -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Before -->
            <div class="space-y-2">
              <h3 class="text-xs uppercase tracking-wider font-semibold text-slate-400">Before: Shallow Regex Scanner</h3>
              <div class="rounded-lg border border-stone-200 bg-stone-50 p-4 h-[320px] flex items-center justify-center">
                <pre class="mermaid w-full">
                  flowchart TD
                    subgraph Callers
                      CLI[cli.py]
                      Runner[agents/runner.py]
                    end
                    subgraph safety.py [Shallow Module]
                      Scan[scan_diff_for_hazards]
                    end
                    CLI -->|loads file, extracts diff| Scan
                    Runner -->|extracts diff| Scan
                    Scan -.leak.-> P1[Hardcoded Secret Regex]
                    Scan -.leak.-> P2[Hardcoded Subprocess Regex]
                    classDef leak stroke:#dc2626,stroke-width:1.5px;
                    class P1,P2,Scan leak
                </pre>
              </div>
            </div>
            <!-- After -->
            <div class="space-y-2">
              <h3 class="text-xs uppercase tracking-wider font-semibold text-slate-400">After: Bounded Safety Gate Seam</h3>
              <div class="rounded-lg border border-stone-200 bg-slate-900 p-4 h-[320px] flex items-center justify-center">
                <pre class="mermaid w-full">
                  flowchart TD
                    subgraph Callers
                      CLI[cli.py]
                      Runner[agents/runner.py]
                    end
                    subgraph safety_gate [Deep SafetyGate Module]
                      Gate[SafetyGate.audit]
                      subgraph Rules [Internal Rules Chain]
                        R1[RegexRule]
                        R2[AstSafetyRule]
                        R3[PathRestrictionRule]
                      end
                    end
                    CLI -->|single call| Gate
                    Runner -->|single call| Gate
                    Gate -.-> Rules
                    classDef dark fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
                    classDef internal fill:#1e293b,stroke:#64748b,color:#cbd5e1;
                    class Gate dark;
                    class R1,R2,R3 internal;
                </pre>
              </div>
            </div>
          </div>

          <!-- Problem/Solution & Wins -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-stone-100">
            <div class="space-y-4">
              <div>
                <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-1">Problem</span>
                <p class="text-sm text-slate-700">The current safety module is a shallow pass-through containing hardcoded regular expressions; callers are forced to handle raw file loading, diff extraction, and diagnostic parsing manually, leaking security rules across the execution engine.</p>
              </div>
              <div>
                <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-1">Solution</span>
                <p class="text-sm text-slate-700">Introduce a deep <code>SafetyGate</code> interface that takes a unified patch and context, executing an internally-composed chain of polymorphic safety rules (regex, AST, paths) loaded dynamically from system configuration.</p>
              </div>
            </div>
            <div>
              <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-2">Architectural Wins</span>
              <ul class="space-y-2 text-sm text-slate-700">
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Locality:</strong> security policies concentrate in one module.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Leverage:</strong> one interface coordinates multiple audit layers.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Interface shrinks:</strong> callers decoupled from pattern internals.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Testability:</strong> verify individual rule adapters independently.</span>
                </li>
              </ul>
            </div>
          </div>
        </article>

        <!-- Candidate 2: Diagnostic Analyzer Engine -->
        <article class="bg-white rounded-xl border border-stone-200 shadow-sm overflow-hidden p-6 space-y-6">
          <div class="flex flex-wrap items-center justify-between gap-4 border-b border-stone-100 pb-4">
            <div class="space-y-1">
              <h2 class="text-xl font-bold text-slate-900 font-serif">2. Deepen Diagnostic Classification & Analysis</h2>
              <div class="flex gap-2">
                <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">Strong Recommendation</span>
                <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700 border border-slate-200">in-process</span>
              </div>
            </div>
            <div class="font-mono text-xs text-slate-500 bg-stone-50 p-2 rounded border border-stone-200">
              src/devflow/failures.py<br>
              src/devflow/runner.py<br>
              src/devflow/agents/runner.py
            </div>
          </div>

          <!-- Before/After Visualization -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Before -->
            <div class="space-y-2">
              <h3 class="text-xs uppercase tracking-wider font-semibold text-slate-400">Before: Shallow Substring Matching</h3>
              <div class="rounded-lg border border-stone-200 bg-stone-50 p-4 h-[320px] flex items-center justify-center">
                <pre class="mermaid w-full">
                  flowchart TD
                    subgraph Callers
                      Runner[runner.py]
                      Agent[agents/runner.py]
                    end
                    subgraph failures.py [Shallow Module]
                      Classify[classify_failure]
                    end
                    Runner -->|raw string match| Classify
                    Agent -->|raw string match| Classify
                    Classify -.leak.-> LLM[Raw Stdout dumped to LLM Prompt]
                    classDef leak stroke:#dc2626,stroke-width:1.5px;
                    class Classify,LLM leak
                </pre>
              </div>
            </div>
            <!-- After -->
            <div class="space-y-2">
              <h3 class="text-xs uppercase tracking-wider font-semibold text-slate-400">After: Deep Diagnostics Seam</h3>
              <div class="rounded-lg border border-stone-200 bg-slate-900 p-4 h-[320px] flex items-center justify-center">
                <pre class="mermaid w-full">
                  flowchart TD
                    subgraph Callers
                      Runner[runner.py]
                      Agent[agents/runner.py]
                    end
                    subgraph diagnostics [Deep DiagnosticAnalyzer Module]
                      Analyzer[DiagnosticAnalyzer.analyze]
                      subgraph Parsers [Internal Adapters]
                        P1[PytestAdapter]
                        P2[MypyAdapter]
                        P3[RuffAdapter]
                        P4[SyntaxAdapter]
                      end
                    end
                    Runner -->|raw stdout log| Analyzer
                    Agent -->|raw stdout log| Analyzer
                    Analyzer -.-> Parsers
                    Analyzer -->|Structured Packet| JSON[DiagnosticPacket<br>- file, line, snippet, hints]
                    classDef dark fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
                    classDef internal fill:#1e293b,stroke:#64748b,color:#cbd5e1;
                    class Analyzer dark;
                    class P1,P2,P3,P4 internal;
                </pre>
              </div>
            </div>
          </div>

          <!-- Problem/Solution & Wins -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-stone-100">
            <div class="space-y-4">
              <div>
                <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-1">Problem</span>
                <p class="text-sm text-slate-700">Failure classification is shallow, performing raw substring matches to return a simple string; the logic of extracting exact filenames, lines, failing code context, or repair suggestions is absent, forcing callers to dump raw logs to model context.</p>
              </div>
              <div>
                <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-1">Solution</span>
                <p class="text-sm text-slate-700">Create a deep <code>DiagnosticAnalyzer</code> module that routes outputs through specific tool parser adapters (pytest, mypy, ruff, compiler) to extract a structured <code>DiagnosticPacket</code> containing file context and repair hints.</p>
              </div>
            </div>
            <div>
              <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-2">Architectural Wins</span>
              <ul class="space-y-2 text-sm text-slate-700">
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Locality:</strong> parsing regexes and traces live in one place.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Leverage:</strong> inner repair loop gets clean, high-leverage context.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Reduced token burn:</strong> filters compiler logs before model queries.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Testability:</strong> feed raw logs directly to verify parser adapters.</span>
                </li>
              </ul>
            </div>
          </div>
        </article>

        <!-- Candidate 3: Model Orchestration Seam -->
        <article class="bg-white rounded-xl border border-stone-200 shadow-sm overflow-hidden p-6 space-y-6">
          <div class="flex flex-wrap items-center justify-between gap-4 border-b border-stone-100 pb-4">
            <div class="space-y-1">
              <h2 class="text-xl font-bold text-slate-900 font-serif">3. Build a Model Orchestration Gateway Seam</h2>
              <div class="flex gap-2">
                <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-amber-50 text-amber-700 border border-amber-200">Worth Exploring</span>
                <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700 border border-slate-200">ports & adapters</span>
              </div>
            </div>
            <div class="font-mono text-xs text-slate-500 bg-stone-50 p-2 rounded border border-stone-200">
              src/devflow/orchestrator.py<br>
              src/devflow/agents/ollama.py<br>
              src/devflow/agents/runner.py
            </div>
          </div>

          <!-- Before/After Visualization -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Before -->
            <div class="space-y-2">
              <h3 class="text-xs uppercase tracking-wider font-semibold text-slate-400">Before: Split & Duplicated HTTP Clients</h3>
              <div class="rounded-lg border border-stone-200 bg-stone-50 p-4 h-[320px] flex items-center justify-center">
                <pre class="mermaid w-full">
                  flowchart TD
                    subgraph agents/runner.py [Caller Logic]
                      Impl[run_implement_agent]
                      Review[run_review_agent]
                      Repair[run_repair_agent]
                    end
                    subgraph Split Clients [Shallow Utilities]
                      Ollama[agents/ollama.py]
                      Gemini[orchestrator.py]
                    end
                    Impl -->|manual Ollama call| Ollama
                    Review -->|manual Ollama call| Ollama
                    Repair -->|duplicated fallback loop| Ollama
                    Impl -.leak.-> Net[Raw Connection Errors & Timeout handling]
                    classDef leak stroke:#dc2626,stroke-width:1.5px;
                    class Impl,Net leak
                </pre>
              </div>
            </div>
            <!-- After -->
            <div class="space-y-2">
              <h3 class="text-xs uppercase tracking-wider font-semibold text-slate-400">After: Unified Model Gateway Seam</h3>
              <div class="rounded-lg border border-stone-200 bg-slate-900 p-4 h-[320px] flex items-center justify-center">
                <pre class="mermaid w-full">
                  flowchart TD
                    subgraph agents/runner.py [Caller Logic]
                      Impl[run_implement_agent]
                      Review[run_review_agent]
                      Repair[run_repair_agent]
                    end
                    subgraph model_gateway [Deep ModelGateway Module]
                      Gateway[ModelGateway.invoke]
                      subgraph Adapters [Polymorphic Seam]
                        Gemini[GeminiClient]
                        Ollama[OllamaClient]
                        Mock[MockClient]
                      end
                    end
                    Impl -->|single prompt call| Gateway
                    Review -->|single prompt call| Gateway
                    Repair -->|single prompt call| Gateway
                    Gateway -.-> Adapters
                    classDef dark fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
                    classDef internal fill:#1e293b,stroke:#64748b,color:#cbd5e1;
                    class Gateway dark;
                    class Gemini,Ollama,Mock internal;
                </pre>
              </div>
            </div>
          </div>

          <!-- Problem/Solution & Wins -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-stone-100">
            <div class="space-y-4">
              <div>
                <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-1">Problem</span>
                <p class="text-sm text-slate-700">Model execution is divided across shallow functions in orchestrator.py and ollama.py; fallback loops, retry budgets, timeouts, and network connection handling are duplicated inside every agent command routine.</p>
              </div>
              <div>
                <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-1">Solution</span>
                <p class="text-sm text-slate-700">Build a unified <code>ModelGateway</code> interface that abstracts model selection, timeout/retry logic, and backpressure, using polymorphic adapters for Ollama, Gemini, and local mock testing.</p>
              </div>
            </div>
            <div>
              <span class="text-xs uppercase tracking-wider font-semibold text-slate-400 block mb-2">Architectural Wins</span>
              <ul class="space-y-2 text-sm text-slate-700">
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Locality:</strong> network logic is isolated from agent flows.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Leverage:</strong> callers get fallbacks and audits transparently.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Two adapters:</strong> real seam verified with local Ollama + Gemini API.</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-emerald-500 font-bold">&check;</span>
                  <span><strong>Mock seam:</strong> mock adapter enables fast, networkless unit testing.</span>
                </li>
              </ul>
            </div>
          </div>
        </article>

      </section>

      <!-- Top Recommendation Section -->
      <section id="top-recommendation" class="bg-slate-900 text-slate-100 rounded-xl border border-slate-800 shadow-md p-6 space-y-4">
        <span class="text-xs uppercase tracking-wider font-semibold text-cyan-400">Top Recommendation</span>
        <h2 class="text-2xl font-bold font-serif">Deepen Diagnostic Classification & Analysis</h2>
        <p class="text-sm text-slate-300 max-w-3xl">
          Deepening the diagnostic module provides the highest immediate token economy wins. By converting the shallow <code>classify_failure</code> function into a <code>DiagnosticAnalyzer</code> seam, we filter noisy standard logs, extract precise failing contexts, and dramatically reduce the local and cloud model context size. This increases both locality for maintainers and leverage for the inner repair loop.
        </p>
        <a href="#candidates" class="inline-flex items-center text-xs font-semibold text-cyan-400 hover:text-cyan-300 transition-colors">
          View candidate details &rarr;
        </a>
      </section>
    </main>
  </body>
</html>
"""
    
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(html_content)
        
    print(f"HTML report successfully written to: {report_path}")
    
    # Open the report in the default browser based on platform
    try:
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", report_path], check=True)
            print("Opened report in default browser on macOS.")
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", report_path], check=True)
            print("Opened report in default browser on Linux.")
        elif sys.platform.startswith("win32"):
            os.startfile(report_path)
            print("Opened report in default browser on Windows.")
    except Exception as exc:
        print(f"Warning: Could not automatically open the browser: {exc}")
        print("Please open the absolute path manually.")

if __name__ == "__main__":
    generate_report()
