from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from devflow.legacy.control_room.paths import dogfood_cases_dir
from devflow.legacy.control_room.persistence import atomic_write_text

DOGFOOD_SCHEMA_VERSION = 1
PRODUCTION_READINESS_SUITE = "production-readiness"

CATEGORY_MAX: dict[str, int] = {
    "A_safety_git_discipline": 26,
    "B_pipeline_correctness": 38,
    "C_context_efficiency": 15,
    "D_worker_artifact_quality": 36,
    "E_recovery_failure_handling": 34,
    "F_knowledge_capture": 10,
    "G_performance_lightweight": 5,
    "H_operating_layer_visual_qa": 10,
}

CATEGORY_LABELS: dict[str, str] = {
    "A_safety_git_discipline": "A - Safety and Git discipline",
    "B_pipeline_correctness": "B - Pipeline correctness",
    "C_context_efficiency": "C - Context efficiency",
    "D_worker_artifact_quality": "D - Worker/artifact quality",
    "E_recovery_failure_handling": "E - Recovery and failure handling",
    "F_knowledge_capture": "F - Knowledge capture",
    "G_performance_lightweight": "G - Performance/lightweight behavior",
    "H_operating_layer_visual_qa": "H - Operating-layer visual QA",
}

CRITICAL_CASES = {
    "unsafe-worker-outcome",
    "git-native-worker-lane-hardening",
    "plan-only-unsafe-git-state",
    "failed-verification-recovery",
    "central-schema-refactor-risk",
}


@dataclass(frozen=True)
class DogfoodCaseCatalog:
    suite: str
    cases: tuple[dict[str, Any], ...]

    @classmethod
    def production_readiness(cls) -> DogfoodCaseCatalog:
        return cls(PRODUCTION_READINESS_SUITE, tuple(_production_readiness_case_dicts()))

    def requested_ids(self, case_ids: Iterable[str] | None) -> list[str]:
        return list(case_ids) if case_ids else [case["id"] for case in self.cases]

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {case["id"]: case for case in self.cases}

    def find(self, case_id: str) -> dict[str, Any] | None:
        return self.by_id().get(case_id)

    def require(self, case_id: str) -> dict[str, Any]:
        case = self.find(case_id)
        if case is None:
            raise KeyError(f"Dogfood case not found: {case_id}")
        return case

    def materialize(self, root: Path) -> list[Path]:
        paths: list[Path] = []
        dogfood_cases_dir(root).mkdir(parents=True, exist_ok=True)
        for case in self.cases:
            path = dogfood_cases_dir(root) / f"{case['id']}.yaml"
            atomic_write_text(path, yaml.safe_dump(case, sort_keys=False))
            paths.append(path)
        return paths

    def category_max_for(self, requested: Iterable[str]) -> dict[str, int]:
        requested_ids = set(requested)
        category_max = {category: 0 for category in CATEGORY_MAX}
        for case in self.cases:
            if case["id"] not in requested_ids:
                continue
            for category, points in case["scoring"].items():
                category_max[category] += points
        return category_max

    def render_list(self, cases: list[dict[str, Any]] | None = None) -> str:
        selected = cases or list(self.cases)
        lines = [f"Dogfood suite: {self.suite}", ""]
        for case in selected:
            max_score = case_max_score(case)
            lines.append(f"{case['id']}: {case['title']} ({max_score} pts, {case['risk_level']} risk)")
        return "\n".join(lines) + "\n"

    def render_case(self, case_id: str) -> str:
        return yaml.safe_dump(self.require(case_id), sort_keys=False)

    def is_critical(self, case_id: str) -> bool:
        return case_id in CRITICAL_CASES


def production_readiness_cases() -> list[dict[str, Any]]:
    return list(DogfoodCaseCatalog.production_readiness().cases)


def materialize_dogfood_cases(root: Path) -> list[Path]:
    return DogfoodCaseCatalog.production_readiness().materialize(root)


def render_dogfood_case_list(cases: list[dict[str, Any]] | None = None) -> str:
    return DogfoodCaseCatalog.production_readiness().render_list(cases)


def render_dogfood_case(case_id: str) -> str:
    return DogfoodCaseCatalog.production_readiness().render_case(case_id)


def case_max_score(case: dict[str, Any]) -> int:
    return sum(int(value) for value in case.get("scoring", {}).values())


def is_critical_case(case_id: str) -> bool:
    return DogfoodCaseCatalog.production_readiness().is_critical(case_id)


def _case_definition(
    *,
    case_id: str,
    title: str,
    category: str,
    task_type: str,
    risk_level: str,
    purpose: str,
    expected_behavior: list[str],
    command_sequence: list[str],
    success_criteria: list[str],
    scoring: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "id": case_id,
        "title": title,
        "category": category,
        "task_type": task_type,
        "risk_level": risk_level,
        "purpose": purpose,
        "expected_behavior": expected_behavior,
        "setup": ["Create only task, outcome, or dogfood artifacts required for this case."],
        "command_sequence": command_sequence,
        "success_criteria": success_criteria,
        "scoring": scoring,
        "cleanup": [
            "Do not promote, push, call providers, create databases, or create dashboard assets.",
            "Remove any temporary non-.devflow dirty marker created by the case.",
        ],
        "notes": [
            "Deterministic local dogfood case.",
            "Workers remain replaceable; Dev-Flow owns state, verification, and promotion gates.",
        ],
    }


def _production_readiness_case_dicts() -> list[dict[str, Any]]:
    cases = [
        _case_definition(
            case_id="tiny-deterministic-docs-task",
            title="Tiny deterministic docs task",
            category="B_pipeline_correctness",
            task_type="docs_only_shell_task",
            risk_level="low",
            purpose="Prove Dev-Flow does not overcomplicate a tiny deterministic change.",
            expected_behavior=[
                "create a bounded task",
                "build a bounded task packet",
                "run a tiny workspace-only docs command",
                "verify with a docs-appropriate check",
                "leave the main checkout untouched except ignored dogfood evidence",
            ],
            command_sequence=[
                "devflow task create 'Dogfood tiny docs task'",
                "devflow task packet <task-id>",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'mkdir -p docs && printf ...'",
                "devflow task verify <task-id> --shell 'test -s docs/dogfood-tiny-note.md'",
            ],
            success_criteria=[
                "task reaches verified state",
                "context packet stays bounded",
                "workspace-only file is verified",
                "no promotion or provider call occurs",
            ],
            scoring={
                "A_safety_git_discipline": 0,
                "B_pipeline_correctness": 4,
                "C_context_efficiency": 7,
                "G_performance_lightweight": 2,
            },
        ),
        _case_definition(
            case_id="cli-help-bounded-feature-task",
            title="CLI/help bounded feature task",
            category="B_pipeline_correctness",
            task_type="cli_help_plan_only",
            risk_level="low",
            purpose="Prove small CLI-facing work follows the pipeline without broad execution.",
            expected_behavior=[
                "create/load task",
                "write orchestration plan-only evidence",
                "inspect dogfood CLI help",
                "avoid unrelated edits and provider calls",
            ],
            command_sequence=[
                "devflow task create 'Dogfood CLI help bounded task'",
                "devflow task orchestrate <task-id> --plan-only",
                "devflow dogfood --help",
            ],
            success_criteria=[
                "orchestration plan exists",
                "dogfood help exposes run/list/report commands",
                "command evidence is stored as a case artifact",
            ],
            scoring={
                "B_pipeline_correctness": 6,
                "C_context_efficiency": 3,
                "G_performance_lightweight": 2,
            },
        ),
        _case_definition(
            case_id="unsafe-worker-outcome",
            title="Unsafe worker outcome",
            category="A_safety_git_discipline",
            task_type="worker_outcome_validation",
            risk_level="high",
            purpose="Prove invalid worker metadata is rejected and preserved as evidence.",
            expected_behavior=[
                "files_touched with parent traversal fails",
                ".git paths fail",
                "unsafe human-review metadata is enforced",
                "validation writes evidence without mutating source",
            ],
            command_sequence=[
                "write invalid worker outcome JSON",
                "devflow worker validate-outcome <outcome-json>",
            ],
            success_criteria=[
                "validation status is failed",
                "path safety errors are explicit",
                "human review error is explicit",
            ],
            scoring={
                "A_safety_git_discipline": 4,
                "D_worker_artifact_quality": 5,
            },
        ),
        _case_definition(
            case_id="git-native-worker-lane-hardening",
            title="Git-native worker lane hardening",
            category="A_safety_git_discipline",
            task_type="git_native_two_lane_recovery",
            risk_level="high",
            purpose="Prove opt-in Git worktree lanes are visible, recoverable, promotable, and cleanup-safe.",
            expected_behavior=[
                "create two Git-native shell-worker lanes in a scratch repo",
                "verify each lane against its worker branch commit",
                "preview both lanes and project lane readiness across supervisor and operating-layer surfaces",
                "promote one lane in the scratch repo",
                "confirm the second lane reports stale recovery after main advances",
                "dry-run and apply cleanup for the promoted lane while preserving task evidence",
            ],
            command_sequence=[
                "devflow task create --git-worktree 'Dogfood Git lane one' (scratch repo)",
                "devflow task create --git-worktree 'Dogfood Git lane two' (scratch repo)",
                "devflow task run <task-id> --worker shell -- commit disjoint file",
                "devflow task verify <task-id> --shell 'test -f <file>'",
                "devflow task promote-preview <task-id>",
                "devflow task promote <first-task-id> (scratch repo only)",
                "devflow task cleanup <first-task-id> --dry-run/--apply (scratch repo only)",
            ],
            success_criteria=[
                "both lanes are ready before promotion",
                "supervisor status and operating-layer snapshot expose lane summaries",
                "second lane reports stale recovery after first promotion",
                "cleanup removes the promoted worktree and preserves canonical task evidence",
            ],
            scoring={
                "A_safety_git_discipline": 4,
                "B_pipeline_correctness": 2,
                "E_recovery_failure_handling": 2,
            },
        ),
        _case_definition(
            case_id="local-worker-lane-hardening",
            title="Local worker lane hardening",
            category="D_worker_artifact_quality",
            task_type="local_worker_evidence_ladder",
            risk_level="medium",
            purpose="Prove registry-backed local worker evidence is visible and recoverable without provider calls.",
            expected_behavior=[
                "write deterministic read-only WorkerEvidence",
                "write deterministic local patch worker proposal evidence",
                "project both local worker lane types across supervisor and operating-layer surfaces",
                "run patch review, dry-run, apply, verify, and promote-preview gates explicitly",
                "avoid provider API calls, autonomous routing, auto-promotion, commits, pushes, databases, and hidden memory",
            ],
            command_sequence=[
                "write read-only WorkerEvidence fixture",
                "write local patch worker proposal fixture",
                "devflow task review-patch <task-id> --agent qwopus-implementer",
                "devflow task patch-dry-run <task-id> --agent qwopus-implementer",
                "devflow task apply-patch <task-id> --agent qwopus-implementer",
                "devflow task verify <task-id> --shell 'test -f hello.txt'",
                "devflow task promote-preview <task-id>",
            ],
            success_criteria=[
                "read-only local worker lane is summarized with review-only next action",
                "local patch worker lane advances through the explicit patch ladder",
                "workspace mutation occurs only after apply-patch",
                "supervisor and operating-layer snapshots expose local worker lane state",
            ],
            scoring={
                "A_safety_git_discipline": 2,
                "B_pipeline_correctness": 2,
                "D_worker_artifact_quality": 3,
                "E_recovery_failure_handling": 3,
            },
        ),
        _case_definition(
            case_id="registry-runtime-contract",
            title="Registry runtime contract",
            category="D_worker_artifact_quality",
            task_type="registry_runtime_contract",
            risk_level="medium",
            purpose=(
                "Prove agent registry list/show/packet surfaces expose runnable, evidence-only, "
                "packet-only/read-only, and provider-refusal contracts without provider calls."
            ),
            expected_behavior=[
                "create a scratch repo and initialize Dev-Flow",
                "create a task and inspect agent list/show JSON runtime contracts",
                "build shell and manual packets with evidence boundaries",
                "run the devflow-shell-worker registry alias only inside the isolated workspace",
                "attempt and refuse an enabled remote/provider-backed agent before any provider call",
                "write registry-runtime-contract-summary.json evidence",
            ],
            command_sequence=[
                "devflow init (scratch repo)",
                "devflow task create 'Dogfood registry runtime contract'",
                "devflow agent list --json",
                "devflow agent show devflow-shell-worker --json",
                "devflow agent packet <task-id> devflow-shell-worker",
                "devflow agent packet <task-id> devflow-manual-codex-worker",
                "devflow task run <task-id> --worker devflow-shell-worker -- /bin/sh -c 'printf ...'",
                "devflow task run <task-id> --worker remote-provider-worker (refused)",
            ],
            success_criteria=[
                "runtime_contract JSON has execution surface, run allowances, packet allowance, refusal, next command, and evidence contract",
                "shell alias writes agent-local packet/log/result evidence and mutates only the workspace",
                "manual packet keeps handoff, result, question, and failure contracts",
                "remote/provider-backed run refuses with experimental_readonly or equivalent runtime refusal",
                "no provider APIs, routing, verification, promotion, commit, push, database, RAG, embeddings, or hidden memory are used",
            ],
            scoring={
                "A_safety_git_discipline": 2,
                "B_pipeline_correctness": 3,
                "D_worker_artifact_quality": 3,
                "E_recovery_failure_handling": 2,
            },
        ),
        _case_definition(
            case_id="success-empty-worker-outcome",
            title="success_empty worker outcome",
            category="D_worker_artifact_quality",
            task_type="worker_outcome_quality",
            risk_level="medium",
            purpose="Prove empty worker success is preserved as no useful progress.",
            expected_behavior=[
                "success_empty remains success_empty in tool evidence",
                "no_useful_result is not normalized into completed useful work",
                "useful result scores higher than empty result",
            ],
            command_sequence=[
                "write no_useful_result outcome with success_empty tool status",
                "write completed outcome with success_with_result tool status",
                "compare deterministic usefulness scores",
            ],
            success_criteria=[
                "empty outcome validates only with human review required",
                "success_empty earns less usefulness credit than success_with_result",
            ],
            scoring={
                "B_pipeline_correctness": 2,
                "D_worker_artifact_quality": 7,
            },
        ),
        _case_definition(
            case_id="model-audition-evidence",
            title="Model audition evidence ladder",
            category="D_worker_artifact_quality",
            task_type="local_model_audition",
            risk_level="medium",
            purpose="Prove read-only local model auditions produce plan/run/score/report evidence without provider calls.",
            expected_behavior=[
                "write dry-run candidate plan evidence",
                "execute selected read-only local profiles through deterministic WorkerEvidence fixtures",
                "write audition-level runs, scorecard, and report artifacts",
                "rank grounded output above generic or hallucinated output",
                "avoid source edits, proposal.patch, verification, promotion, commits, pushes, and provider calls",
            ],
            command_sequence=[
                "devflow agent audition <task-id> --job review-debug --dry-run --json (fixture discovery)",
                "devflow agent audition <task-id> --job review-debug --execute --json (fixture worker-pool runs)",
            ],
            success_criteria=[
                "dry-run plan selects no more than three safe candidates",
                "execute writes runs.json, scorecard.json, and report.md",
                "WorkerEvidence is reused under local-model-runs",
                "scorecard ranks grounded output first and flags false claims",
            ],
            scoring={
                "A_safety_git_discipline": 2,
                "B_pipeline_correctness": 3,
                "D_worker_artifact_quality": 4,
            },
        ),
        _case_definition(
            case_id="plan-only-unsafe-git-state",
            title="Plan-only unsafe Git state",
            category="A_safety_git_discipline",
            task_type="orchestration_plan_git_guardrail",
            risk_level="high",
            purpose="Prove orchestration recognizes unsafe Git state without running workers.",
            expected_behavior=[
                "temporary dirty marker makes Git state unsafe",
                "plan records dirty_git_tree stop condition",
                "parallelism is blocked",
                "temporary marker is removed and cleanup result is visible",
            ],
            command_sequence=[
                "create temporary dirty marker",
                "devflow task orchestrate <task-id> --plan-only",
                "remove temporary dirty marker",
            ],
            success_criteria=[
                "dirty_git_tree is active",
                "recommended execution is human_review_first or sequential",
                "no worker execution occurs",
                "cleanup status is recorded",
            ],
            scoring={
                "A_safety_git_discipline": 5,
                "E_recovery_failure_handling": 3,
            },
        ),
        _case_definition(
            case_id="failed-verification-recovery",
            title="Failed verification recovery",
            category="E_recovery_failure_handling",
            task_type="verification_failure",
            risk_level="medium",
            purpose="Prove failed verification blocks promotion readiness and records next state.",
            expected_behavior=[
                "failed verification is captured",
                "promotion readiness is blocked",
                "next safe action is explainable",
            ],
            command_sequence=[
                "devflow task create 'Dogfood failed verification recovery'",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'printf actual > recovery.txt'",
                "devflow task verify <task-id> --shell 'test \"$(cat recovery.txt)\" = expected'",
                "inspect promotion readiness errors",
            ],
            success_criteria=[
                "task status is verification_failed",
                "verification exit code is non-zero",
                "promotion_readiness_errors is non-empty",
            ],
            scoring={
                "A_safety_git_discipline": 4,
                "B_pipeline_correctness": 3,
                "E_recovery_failure_handling": 6,
            },
        ),
        _case_definition(
            case_id="knowledge-capture-from-validation-failure",
            title="Knowledge capture from validation failure",
            category="F_knowledge_capture",
            task_type="knowledge_capture",
            risk_level="low",
            purpose="Prove validation failures can become proposed, source-linked knowledge.",
            expected_behavior=[
                "validation failure evidence exists",
                "knowledge capture creates a proposed item",
                "source validation artifact is linked",
                "search can find the item",
                "knowledge is not auto-promoted",
            ],
            command_sequence=[
                "write invalid worker outcome JSON",
                "devflow worker validate-outcome <outcome-json>",
                "devflow knowledge capture --from-validation <validation-json>",
                "devflow knowledge search validation",
            ],
            success_criteria=[
                "knowledge status is proposed",
                "linked artifacts include validation evidence",
                "search returns the proposed item",
            ],
            scoring={
                "D_worker_artifact_quality": 3,
                "F_knowledge_capture": 10,
            },
        ),
        _case_definition(
            case_id="handoff-resume",
            title="Handoff/resume",
            category="E_recovery_failure_handling",
            task_type="artifact_resume",
            risk_level="low",
            purpose="Prove a fresh agent can reconstruct state from files and reports.",
            expected_behavior=[
                "task id and artifact paths are written to handoff evidence",
                "state reloads from canonical task files",
                "next safe action is explicit",
                "no hidden state is required",
            ],
            command_sequence=[
                "devflow task create 'Dogfood handoff resume'",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'printf handoff > handoff.txt'",
                "devflow task verify <task-id> --shell 'test -s handoff.txt'",
                "write dogfood handoff.md from file artifacts",
            ],
            success_criteria=[
                "fresh load of task succeeds",
                "handoff includes task id, artifacts, state, and next safe action",
            ],
            scoring={
                "B_pipeline_correctness": 3,
                "C_context_efficiency": 2,
                "E_recovery_failure_handling": 2,
            },
        ),
        _case_definition(
            case_id="parallelism-decision-docs-test-split",
            title="Parallelism decision docs/test split",
            category="C_context_efficiency",
            task_type="orchestration_context_layers",
            risk_level="low",
            purpose="Prove safe parallelism can be recommended or blocked conservatively with clear roles.",
            expected_behavior=[
                "plan-only orchestration writes role layers",
                "workers cannot promote",
                "DevMode skills are required",
                "no provider or worker execution occurs",
            ],
            command_sequence=[
                "devflow task create 'Update docs and tests for dogfood split'",
                "devflow task orchestrate <task-id> --plan-only",
            ],
            success_criteria=[
                "role context layers are present",
                "all roles have can_promote false",
                "notes state plan-only with no workers or providers",
            ],
            scoring={
                "C_context_efficiency": 3,
                "G_performance_lightweight": 1,
            },
        ),
        _case_definition(
            case_id="central-schema-refactor-risk",
            title="Central schema/refactor risk",
            category="A_safety_git_discipline",
            task_type="orchestration_high_risk_refusal",
            risk_level="high",
            purpose="Prove unsafe parallelism is refused for high-risk central changes.",
            expected_behavior=[
                "risk is high or medium",
                "recommended execution is not parallel",
                "parallelism_allowed is false",
                "human review is required",
            ],
            command_sequence=[
                "devflow task create 'Rewrite whole repo migration and disable guardrail'",
                "devflow task orchestrate <task-id> --plan-only",
            ],
            success_criteria=[
                "plan records high-risk stop conditions",
                "parallel execution is refused",
            ],
            scoring={
                "A_safety_git_discipline": 3,
                "E_recovery_failure_handling": 2,
            },
        ),
        _case_definition(
            case_id="simple-scheduler-parallel-coordination",
            title="Simple scheduler parallel coordination",
            category="B_pipeline_correctness",
            task_type="scheduler_projection",
            risk_level="medium",
            purpose="Prove scheduler status coordinates ready, blocked, stale, retry, and batch evidence without autonomous execution.",
            expected_behavior=[
                "project ready parallel batches from goal slice evidence",
                "surface dependency-blocked and question-blocked work",
                "mark stale running tasks without cleaning locks or rerunning work",
                "write explicit retry-request evidence without clearing old logs",
                "avoid provider calls, background scheduling, auto-verification, auto-promotion, commits, pushes, databases, and hidden memory",
            ],
            command_sequence=[
                "write deterministic goal slices and task evidence",
                "devflow scheduler status --json",
                "devflow scheduler retry <task-id> --reason '<reason>' --json",
            ],
            success_criteria=[
                "scheduler exposes ready, blocked, stale, and retry counts",
                "next action points to an explicit existing Dev-Flow command",
                "retry evidence preserves prior task state",
            ],
            scoring={
                "B_pipeline_correctness": 2,
                "D_worker_artifact_quality": 3,
                "E_recovery_failure_handling": 5,
            },
        ),
        _case_definition(
            case_id="question-blocker-resume-loop",
            title="Question blocker resume loop",
            category="E_recovery_failure_handling",
            task_type="question_resume_evidence",
            risk_level="medium",
            purpose="Exercise explicit question answer evidence without running workers or providers.",
            expected_behavior=[
                "list deterministic open question evidence",
                "surface malformed question evidence as a warning",
                "persist a human answer without changing source worker output",
                "let scheduler recommend a conservative explicit resume command",
                "avoid worker resume, provider calls, verification, promotion, commits, pushes, databases, and background schedulers",
            ],
            command_sequence=[
                "write deterministic worker question evidence",
                "devflow question list --json",
                "devflow question answer <question-id> --answer '<answer>' --json",
                "devflow scheduler status --json",
            ],
            success_criteria=[
                "question list exposes one deterministic open blocker and warning evidence",
                "answer writes project-level and task-local records",
                "source question evidence is preserved byte-for-byte",
                "scheduler no longer treats the answered question as an open blocker",
            ],
            scoring={
                "B_pipeline_correctness": 2,
                "D_worker_artifact_quality": 2,
                "E_recovery_failure_handling": 4,
            },
        ),
        _case_definition(
            case_id="operator-readiness-reconciliation",
            title="Operator readiness reconciliation",
            category="E_recovery_failure_handling",
            task_type="operator_readiness_projection",
            risk_level="medium",
            purpose="Prove operator-facing status, scheduler, supervisor, and operating-layer projections agree on lifecycle blockers and plain task labels.",
            expected_behavior=[
                "build deterministic generated-name and descriptive-name task fixtures",
                "mark a goal lifecycle as missing without mutating it from the projection",
                "preserve stale freshness dispatch evidence as a warning",
                "make scheduler, status, supervisor packet, and operating-layer snapshot agree on operator readiness counts",
                "prefer lifecycle repair over worker dispatch or stale task-creation guidance",
            ],
            command_sequence=[
                "write deterministic operator-readiness fixture",
                "devflow status --json",
                "devflow scheduler status --json",
                "devflow supervisor packet --json",
                "devflow operating-layer snapshot --json",
            ],
            success_criteria=[
                "major surfaces agree on worker-ready and lifecycle-blocked counts",
                "next safe action points to lifecycle repair",
                "generated task ids remain secondary to the descriptive slice title",
                "stale freshness guidance is retained as a warning, not an executable directive",
            ],
            scoring={
                "B_pipeline_correctness": 2,
                "D_worker_artifact_quality": 2,
                "E_recovery_failure_handling": 3,
            },
        ),
        _case_definition(
            case_id="intent-scaffold-approval-path",
            title="Intent scaffold approval path",
            category="B_pipeline_correctness",
            task_type="intent_scaffold_approval",
            risk_level="medium",
            purpose=(
                "Prove raw operator intent becomes reviewable Idea Foundry and goal/task scaffold evidence "
                "before canonical tasks or workers exist."
            ),
            expected_behavior=[
                "capture raw idea evidence",
                "preview scaffold without mutating goals or tasks",
                "write scaffold review evidence",
                "simulate human classification and idea promotion",
                "create goal from reviewed scaffold evidence",
                "project task slices without creating canonical task records",
                "avoid provider calls, worker runs, verification, task promotion, commits, and pushes",
            ],
            command_sequence=[
                "devflow idea capture 'build a search plugin'",
                "devflow idea scaffold-goal <idea-id> --dry-run",
                "devflow idea scaffold-goal <idea-id>",
                "devflow idea classify <idea-id> --maturity goal_ready",
                "devflow idea promote <idea-id> --to goal",
                "devflow idea create-goal <idea-id>",
                "devflow goal slices <goal-id>",
            ],
            success_criteria=[
                "dry-run scaffold preview leaves the scratch repo unchanged",
                "scaffold-goal JSON and Markdown evidence exist before goal creation",
                "created goal consumes scaffold PRD, context, risk, handoff, and task-slice evidence",
                "no canonical task record, worker run, verification, task promotion, commit, push, or provider call occurs",
            ],
            scoring={
                "B_pipeline_correctness": 4,
                "D_worker_artifact_quality": 4,
                "E_recovery_failure_handling": 2,
            },
        ),
        _case_definition(
            case_id="operating-layer-visual-qa-hardening",
            title="Operating Layer visual QA hardening",
            category="H_operating_layer_visual_qa",
            task_type="operating_layer_visual_qa",
            risk_level="medium",
            purpose="Prove the local operating-layer UI has deterministic visual QA evidence in dogfood.",
            expected_behavior=[
                "desktop and mobile visual QA paths are planned",
                "current and baseline PNG/SVG artifacts are written",
                "deterministic fallback is enough when browser screenshots are unavailable",
                "external/Appshot or Playwright rasters are accepted when present",
                "visual metadata covers no-overflow, guided first viewport, active work cards, and approval states",
            ],
            command_sequence=[
                "devflow task create 'Dogfood operating layer visual QA'",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'printf visual > visual.txt'",
                "devflow task verify <task-id> --shell 'test -s visual.txt'",
                "devflow operating-layer visual-qa --write-current --update-baseline --json",
            ],
            success_criteria=[
                "desktop and mobile current/baseline artifacts exist",
                "visual QA status is pass",
                "metadata confirms no horizontal overflow",
                "metadata confirms guided first viewport ordering, active work cards, and approval states",
            ],
            scoring={
                "H_operating_layer_visual_qa": 10,
            },
        ),
    ]
    _validate_suite_totals(cases)
    return cases


def validate_dogfood_case(case: dict[str, Any]) -> list[str]:
    required = {
        "schema_version",
        "id",
        "title",
        "category",
        "task_type",
        "risk_level",
        "purpose",
        "expected_behavior",
        "setup",
        "command_sequence",
        "success_criteria",
        "scoring",
        "cleanup",
        "notes",
    }
    errors: list[str] = []
    missing = sorted(required - set(case))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
        return errors
    if case["schema_version"] != DOGFOOD_SCHEMA_VERSION:
        errors.append("schema_version must be 1")
    if not isinstance(case["id"], str) or not case["id"]:
        errors.append("id must be a non-empty string")
    if case["category"] not in CATEGORY_MAX:
        errors.append(f"unknown category: {case['category']}")
    if case["risk_level"] not in {"low", "medium", "high"}:
        errors.append("risk_level must be low, medium, or high")
    for list_key in ("expected_behavior", "command_sequence", "success_criteria", "notes"):
        if not isinstance(case[list_key], list):
            errors.append(f"{list_key} must be a list")
    scoring = case["scoring"]
    if not isinstance(scoring, dict) or not scoring:
        errors.append("scoring must be a non-empty mapping")
    else:
        for category, value in scoring.items():
            if category not in CATEGORY_MAX:
                errors.append(f"unknown scoring category: {category}")
            if not isinstance(value, int) or value < 0:
                errors.append(f"scoring.{category} must be a non-negative integer")
    return errors


def _validate_suite_totals(cases: list[dict[str, Any]]) -> None:
    category_totals = {category: 0 for category in CATEGORY_MAX}
    for case in cases:
        errors = validate_dogfood_case(case)
        if errors:
            raise ValueError(f"Dogfood case {case.get('id', '<unknown>')} is invalid: {'; '.join(errors)}")
        for category, points in case["scoring"].items():
            category_totals[category] += points
    if category_totals != CATEGORY_MAX:
        raise ValueError(f"Dogfood suite scoring totals drifted: {category_totals} != {CATEGORY_MAX}")
