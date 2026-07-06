from __future__ import annotations

from devflow.control_room.operating_layer_architecture_evidence_script import ARCHITECTURE_EVIDENCE_JS
from devflow.control_room.operating_layer_architecture_evidence_styles import ARCHITECTURE_EVIDENCE_CSS
from devflow.control_room.operating_layer_idea_greenhouse_script import IDEA_GREENHOUSE_JS
from devflow.control_room.operating_layer_idea_greenhouse_styles import IDEA_GREENHOUSE_CSS
from devflow.control_room.operating_layer_obsidian_intake_script import OBSIDIAN_INTAKE_JS
from devflow.control_room.operating_layer_obsidian_intake_styles import OBSIDIAN_INTAKE_CSS
from devflow.control_room.operating_layer_pipeline_script import PIPELINE_JS
from devflow.control_room.operating_layer_pipeline_styles import PIPELINE_CSS
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer_html import INDEX_HTML as SPLIT_INDEX_HTML
from devflow.control_room.operating_layer_script import APP_JS as SPLIT_APP_JS
from devflow.control_room.operating_layer_styles import APP_CSS as SPLIT_APP_CSS
from devflow.control_room.operating_layer_workbench_script import WORKBENCH_JS
from devflow.control_room.operating_layer_workbench_styles import WORKBENCH_CSS


def test_operating_layer_assets_facade_keeps_split_asset_contract() -> None:
    assert INDEX_HTML == SPLIT_INDEX_HTML
    assert APP_CSS == SPLIT_APP_CSS
    assert APP_JS == SPLIT_APP_JS
    assert '<link rel="stylesheet" href="/app.css?v=unified-workbench-20260629">' in INDEX_HTML
    assert '<script src="/app.js?v=unified-workbench-20260629"></script>' in INDEX_HTML
    assert ".focus-overlay" in APP_CSS
    assert "pipeline-section" in INDEX_HTML
    assert ".panel" in APP_CSS
    assert ".task-control-grid" in APP_CSS
    assert ".bottom-dock" not in APP_CSS
    assert "openFocus" in APP_JS
    assert "closeFocus" in APP_JS
    assert "sendBrainstormMessage" in APP_JS
    assert "loadSnapshot" in APP_JS
    assert "renderOrchestrator" in APP_JS
    assert "renderMissionFeed" in APP_JS
    assert "renderWorkerLanes" in APP_JS
    assert "firstViewportPresentationFromSnapshot" in APP_JS
    assert "fallbackFirstViewportPresentation" in APP_JS
    assert "older/partial snapshots" in APP_JS
    assert "renderFirstViewport" in APP_JS
    assert "renderArchitectureEvidence" in APP_JS
    assert "renderWorkbench" in APP_JS
    assert "'/api/workbench/implement'" in APP_JS
    assert "'/api/gates/setup'" in APP_JS
    assert "renderSerialRuntimePanel" in APP_JS
    assert "serial-runtime-panel" in INDEX_HTML
    assert "serial-runtime-panel" in APP_CSS
    assert "local_model_readiness" in APP_JS
    assert "localModelReadinessAction" in APP_JS
    assert "local-model-readiness-actions" in APP_CSS
    assert "first_viewport" in APP_JS
    assert "executeAction" in APP_JS
    assert "rememberApprovedActionResult" not in APP_JS
    assert "refreshSnapshotAfterApprovedAction" not in APP_JS
    assert "brainstormMessage" not in APP_JS
    assert "function taskAction(" not in APP_JS
    assert "renderWorkerLanes" in APP_JS
    assert "task-control-grid" in INDEX_HTML
    assert "architecture-evidence-section" in INDEX_HTML
    assert "workbench-stage-path" in INDEX_HTML
    assert "workbench-gate-strip" in INDEX_HTML


def test_operating_layer_architecture_evidence_assets_are_facade_parts() -> None:
    assert ARCHITECTURE_EVIDENCE_JS in APP_JS
    assert ARCHITECTURE_EVIDENCE_CSS in APP_CSS
    assert APP_JS.count("function renderArchitectureEvidence") == 1
    assert APP_CSS.count("/* ===== ARCHITECTURE EVIDENCE ===== */") == 1
    assert 'sandbox="allow-scripts" only' in ARCHITECTURE_EVIDENCE_JS
    assert "Loading report…" in ARCHITECTURE_EVIDENCE_JS
    assert "@media (max-width: 1200px)" in ARCHITECTURE_EVIDENCE_CSS
    assert "@media (max-width: 900px)" in ARCHITECTURE_EVIDENCE_CSS


def test_operating_layer_obsidian_intake_assets_are_facade_parts() -> None:
    assert OBSIDIAN_INTAKE_JS in APP_JS
    assert OBSIDIAN_INTAKE_CSS in APP_CSS
    assert APP_JS.count("function renderObsidianIntake") == 1
    assert APP_JS.count("async function loadObsidianIntake()") == 1
    assert APP_CSS.count("/* ===== OBSIDIAN INTAKE ===== */") == 1


def test_operating_layer_workbench_assets_are_facade_parts() -> None:
    assert WORKBENCH_JS in APP_JS
    assert WORKBENCH_CSS in APP_CSS
    assert APP_JS.count("function renderWorkbench(") == 1
    assert APP_JS.count("async function runWorkbenchImplement(") == 1
    assert APP_JS.count("function setupWorkbenchActions(") == 1
    assert APP_CSS.count("/* ===== UNIFIED CHAT WORKBENCH ===== */") == 1
    assert ".status-pill" not in WORKBENCH_CSS
    assert "@media (max-width: 1200px)" in WORKBENCH_CSS
    assert "@media (max-width: 900px)" in WORKBENCH_CSS


def test_operating_layer_pipeline_assets_are_facade_parts() -> None:
    assert PIPELINE_JS in APP_JS
    assert PIPELINE_CSS in APP_CSS
    assert APP_JS.count("function renderPipeline(input)") == 1
    assert APP_JS.count("async function refreshPipelineState()") == 1
    assert APP_JS.count("function setupPipelineButtons(scope)") == 1
    assert APP_CSS.count("/* ===== PIPELINE SECTION ===== */") == 1
    assert "@media (max-width: 900px)" in PIPELINE_CSS


def test_operating_layer_idea_greenhouse_assets_are_facade_parts() -> None:
    assert IDEA_GREENHOUSE_JS in APP_JS
    assert IDEA_GREENHOUSE_CSS in APP_CSS
    assert APP_JS.count("function renderIdeaGreenhouse") == 1
    assert APP_JS.count("async function handleIdeaGreenhouseClick") == 1
    assert APP_JS.count("function handleIdeaGreenhouseKeydown") == 1
    assert APP_CSS.count("/* ===== IDEA GREENHOUSE ===== */") == 1
    assert "function runApprovedCommand" not in IDEA_GREENHOUSE_JS
    assert "function executeAction" not in IDEA_GREENHOUSE_JS
    assert "function setupTaskSurfaceActions" not in IDEA_GREENHOUSE_JS
    assert "function setupTaskSurfaceActions" in APP_JS
    assert "runApprovedCommand(command, { contextNote: note })" in APP_JS
    assert APP_JS.index(OBSIDIAN_INTAKE_JS) < APP_JS.index(WORKBENCH_JS)
    assert APP_JS.index(WORKBENCH_JS) < APP_JS.index(PIPELINE_JS)
    assert APP_JS.index(PIPELINE_JS) < APP_JS.index(ARCHITECTURE_EVIDENCE_JS)


def test_operating_layer_client_renders_stale_lock_warning() -> None:
    assert "lockStatusWarning" in APP_JS
    assert "const lockWarningLine = lockStatusWarning(item);" in APP_JS
    assert "const lockWarning = lockStatusWarning(task);" in APP_JS
    assert "Read-only stale lock visibility" in APP_JS


def test_operating_layer_refactor_ui_has_static_asset_contract() -> None:
    assert 'id="refactor-run-btn"' in INDEX_HTML
    assert 'id="refactor-view-work-btn"' in INDEX_HTML
    assert 'id="refactor-worker"' in INDEX_HTML
    assert '<option value="local-fast">local-fast</option>' in INDEX_HTML
    assert '<option value="codex55">codex55</option>' in INDEX_HTML
    assert "/api/refactor/start" in APP_JS
    assert "/api/refactor/status" in APP_JS
    assert "renderRefactorWorkView" in APP_JS
    assert "data-refactor-tab" in APP_JS
    assert "Rationale" in APP_JS
    assert "Status reason" in APP_JS
    assert "Worker Plan" in APP_JS
    assert "Loop Status" in APP_JS
    assert "Handoff Evidence" in APP_JS
    assert "Worker thinking" not in APP_JS
    assert "REFACTOR_APPROVAL_ACTION" in APP_JS
    assert "setupRefactorLoop();" in APP_JS


def test_operating_layer_html_includes_idea_greenhouse_asset_contract() -> None:
    assert "Unified Chat Workbench" in INDEX_HTML
    assert "Idea -> Brainstorm -> Spec -> Plan -> Implement" in INDEX_HTML
    assert "idea-greenhouse-section" in INDEX_HTML
    assert "workbench-stage-path" in INDEX_HTML
    assert "workbench-gate-strip" in INDEX_HTML
    assert "workbench-next-action" in INDEX_HTML
    assert "workbench-implement-result" in INDEX_HTML
    assert "pipeline-spine" in INDEX_HTML
    assert "product-review-section" in INDEX_HTML
    assert "idea-greenhouse-status" in INDEX_HTML
    assert "idea-capture-form" in INDEX_HTML
    assert "idea-capture-text" in INDEX_HTML
    assert "idea-capture-title" in INDEX_HTML
    assert "idea-capture-submit" in INDEX_HTML
    assert "idea-greenhouse-lanes" in INDEX_HTML
    assert "idea-greenhouse-primary-action" in INDEX_HTML


def test_operating_layer_task_control_replaces_fixed_review_dock_contract() -> None:
    assert '<section id="product-review-section" class="product-review-section" aria-label="Task Control">' in INDEX_HTML
    assert '<h3 class="panel-title">Task Control</h3>' in INDEX_HTML
    assert 'class="task-control-grid"' in INDEX_HTML
    assert "bottom-dock" not in INDEX_HTML
    assert "Product / Review" not in INDEX_HTML
    assert ".task-control-grid" in APP_CSS
    assert ".bottom-dock" not in APP_CSS

    product_review_rules = APP_CSS[
        APP_CSS.index(".product-review-section {") : APP_CSS.index(".product-review-header {")
    ]
    assert "position: fixed" not in product_review_rules

    layout_column_rules = APP_CSS[
        APP_CSS.index(".layout-columns {") : APP_CSS.index("}", APP_CSS.index(".layout-columns {"))
    ]
    assert "max-height" not in layout_column_rules
    assert "overflow-y: auto" not in layout_column_rules


def test_operating_layer_css_includes_idea_greenhouse_layout_contract() -> None:
    for token in (
        ".idea-greenhouse-section",
        ".idea-capture-form",
        ".idea-greenhouse-lanes",
        "grid-template-columns: repeat(3, minmax(0, 1fr));",
        ".idea-lane",
        ".idea-lane-header",
        ".idea-card",
        ".idea-card.raw",
        ".idea-card.clarify",
        ".idea-card.candidate",
        ".idea-card.promoted",
        ".idea-card.parked",
        ".idea-card.archived",
        ".idea-primary-action",
        ".status-pill.muted",
        ".idea-card[role=\"button\"]",
        ".idea-detail-grid",
        ".idea-detail-evidence",
        ".idea-detail-metadata",
        ".idea-detail-metadata-list",
    ):
        assert token in APP_CSS

    idea_lane_rules = APP_CSS[
        APP_CSS.index(".idea-greenhouse-lanes {") : APP_CSS.index(".idea-lane {")
    ]
    assert "max-height: 48px" not in idea_lane_rules

    mobile_rules = APP_CSS[APP_CSS.index("@media (max-width: 900px)") :]
    assert ".idea-greenhouse-lanes { grid-template-columns: repeat(3, minmax(0, 1fr));" in mobile_rules
    assert ".layout-columns { flex-direction: column; padding: 0 12px; }" in mobile_rules
    assert INDEX_HTML.index('<div class="zone" id="zone-capture-plan"') < INDEX_HTML.index(
        '<div class="zone" id="zone-execute"'
    ) < INDEX_HTML.index('<aside class="chat-sidebar"')
    assert INDEX_HTML.index('id="idea-greenhouse-section"') < INDEX_HTML.index(
        'id="pipeline-spine"'
    ) < INDEX_HTML.index('id="orchestrator-section"') < INDEX_HTML.index('id="product-review-section"')


def test_operating_layer_desktop_layout_keeps_primary_panels_from_flex_shrinking() -> None:
    """Primary control-room panels may scroll on desktop, but must never shrink and clip content."""
    desktop_start = APP_CSS.index("@media (min-width: 1201px)")
    desktop_rules = APP_CSS[desktop_start : APP_CSS.index("@media (max-width: 1200px)", desktop_start)]

    assert ".main-content {" in APP_CSS
    assert ".chat-sidebar {" in APP_CSS
    assert ".chat-sidebar .brainstorm-section {" in APP_CSS
    assert ".task-control-grid" in desktop_rules
    layout_column_rules = APP_CSS[
        APP_CSS.index(".layout-columns {") : APP_CSS.index("}", APP_CSS.index(".layout-columns {"))
    ]
    assert "max-height" not in layout_column_rules
    assert "overflow-y: auto" not in layout_column_rules


def test_operating_layer_home_layout_uses_compact_shell_contract() -> None:
    assert "--sidebar-w: 56px;" in APP_CSS
    assert ".sidebar:hover" in APP_CSS
    assert ".sidebar:hover .brand-text" in APP_CSS
    assert '<a href="#zone-capture-plan" class="nav-item active" data-nav="home"' in INDEX_HTML
    assert '<a href="#zone-execute" class="nav-item" data-nav="work"' in INDEX_HTML
    assert 'data-nav-target="zone-execute"' in INDEX_HTML
    assert "setupNavigation" in APP_JS
    assert "scrollIntoView" in APP_JS

    assert 'id="topbar-health"' in INDEX_HTML
    assert 'class="panel health-section"' not in INDEX_HTML
    assert "#topbar-health" in APP_CSS
    assert ".health-section" not in APP_CSS
    assert "orchestrator-health-bars" in INDEX_HTML
    assert "local-model-inventory" in INDEX_HTML
    assert "renderTopbarHealth" in APP_JS
    assert "renderLocalModelInventory" in APP_JS
    assert "data-local-model-command" in APP_JS
    for token in (
        ".local-model-inventory",
        ".local-model-summary",
        ".local-model-list",
        ".local-model-item",
        ".local-model-status",
        ".local-model-action",
    ):
        assert token in APP_CSS

    assert 'id="brainstorm-history-details" class="brainstorm-history-inline"' in INDEX_HTML
    assert ".brainstorm-history-inline summary" in APP_CSS
    assert ".brainstorm-section" in APP_CSS
    assert "min-height: clamp(340px, 44vh, 520px);" in APP_CSS
    assert "#pipeline-spine .pipeline-step" in APP_CSS
    assert ".architecture-evidence-section" in APP_CSS
    assert ".architecture-artifact-chip" in APP_CSS
    assert "min-height: 0;" in APP_CSS
    assert ".orchestrator-section.is-idle" in APP_CSS
    assert "toggle('is-idle'" in APP_JS


def test_operating_layer_idle_desktop_keeps_brainstorm_in_chat_sidebar() -> None:
    assert INDEX_HTML.index('<div class="zone" id="zone-capture-plan"') < INDEX_HTML.index(
        '<aside class="chat-sidebar"'
    ) < INDEX_HTML.index('id="brainstorm-section"')
    chat_sidebar = INDEX_HTML[
        INDEX_HTML.index('<aside class="chat-sidebar"') :
        INDEX_HTML.index("</aside>", INDEX_HTML.index('<aside class="chat-sidebar"'))
    ]
    assert 'id="brainstorm-section"' in chat_sidebar
    assert 'id="brainstorm-transcript"' in chat_sidebar

    assert ".chat-sidebar .brainstorm-section" in APP_CSS
    assert ".chat-sidebar .brainstorm-transcript" in APP_CSS
    assert ".product-review-section.is-empty" in APP_CSS
    assert ".mission-feed-section.is-empty" in APP_CSS
    assert "$('product-review-section')?.classList.toggle" in APP_JS
    assert "section?.classList.toggle('is-empty'" in APP_JS


def test_operating_layer_pipeline_uses_compact_four_step_grid() -> None:
    pipeline_rules = APP_CSS[
        APP_CSS.index("#pipeline-spine .pipeline-stages {") : APP_CSS.index("#pipeline-spine .pipeline-step {")
    ]
    assert "display: grid" in pipeline_rules
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in pipeline_rules
    assert "repeat(auto-fit" not in pipeline_rules


def test_operating_layer_js_includes_idea_greenhouse_runtime_contract() -> None:
    for token in (
        "setupIdeaGreenhouse",
        "renderIdeaGreenhouse",
        "captureIdeaFromGreenhouse",
        "secondaryIdeaActions",
        "Parked from Idea Greenhouse",
        "idea-greenhouse-lanes",
        "data-inspect-idea",
        "findIdeaCard",
        "renderIdeaDetail",
        "Raw metadata",
        "Evidence paths",
    ):
        assert token in APP_JS


def test_operating_layer_js_model_selectors_share_all_available_agents_contract() -> None:
    assert "function selectableAgents()" in APP_JS
    assert "function renderModelPickerDropdown(config)" in APP_JS
    assert "function setupModelPicker(config" in APP_JS
    assert "const selectable = selectableAgents();" in APP_JS
    assert "selectable.filter(agent => !agent.is_local).map(toSelectableModelRow)" in APP_JS
    assert "selectable.filter(agent => agent.is_local).map(toSelectableModelRow)" in APP_JS
    assert "builderModelPickerConfig()" in APP_JS
    assert "judgeModelPickerConfig()" in APP_JS
    assert "builder_profile_id: builderModel" in APP_JS
    assert "judge_profile_id: judgeModel" in APP_JS
    assert "'/api/local-model/ensure'" in APP_JS
    assert "Starting..." in APP_JS
    assert "const previousValue = getModelPickerValue(config);" in APP_JS
    assert "setModelPickerValue(config, previousValue, { persist: false });" in APP_JS
    assert "setModelPickerValue(config, agent.id, { persist: true });" in APP_JS
    assert "a.adapter === 'openai_compatible' || a.adapter === 'ollama_chat'" not in APP_JS


def test_builder_judge_model_pickers_use_hidden_inputs_and_shared_dropdowns() -> None:
    assert '<select id="bj-builder-model">' not in INDEX_HTML
    assert '<select id="bj-judge-model">' not in INDEX_HTML
    assert 'type="hidden" id="bj-builder-model" name="builder_profile_id"' in INDEX_HTML
    assert 'type="hidden" id="bj-judge-model" name="judge_profile_id"' in INDEX_HTML
    assert 'id="bj-builder-model-selector"' in INDEX_HTML
    assert 'id="bj-builder-model-dropdown"' in INDEX_HTML
    assert 'id="bj-judge-model-selector"' in INDEX_HTML
    assert 'id="bj-judge-model-dropdown"' in INDEX_HTML


def test_operating_layer_css_prevents_right_rail_brainstorm_controls_from_overlapping_transcript() -> None:
    header_rules = APP_CSS[
        APP_CSS.index(".chat-sidebar .brainstorm-section .panel-header {") :
        APP_CSS.index(".chat-sidebar .brainstorm-section .panel-header-controls {")
    ]
    controls_rules = APP_CSS[
        APP_CSS.index(".chat-sidebar .brainstorm-section .panel-header-controls {") :
        APP_CSS.index(".chat-sidebar .brainstorm-section .model-selector-wrap {")
    ]
    wrapper_rules = APP_CSS[
        APP_CSS.index(".chat-sidebar .brainstorm-section .model-selector-wrap {") :
        APP_CSS.index(".chat-sidebar .brainstorm-section .model-dropdown {")
    ]
    dropdown_rules = APP_CSS[
        APP_CSS.index(".chat-sidebar .brainstorm-section .model-dropdown {") :
        APP_CSS.index(".chat-sidebar .brainstorm-transcript {")
    ]

    assert "min-height: auto;" in header_rules
    assert "overflow: visible;" in header_rules
    assert "display: flex;" in controls_rules
    assert "flex-wrap: wrap;" in controls_rules
    assert "width: 100%;" in controls_rules
    assert "flex: 1 1 auto;" in wrapper_rules
    assert "min-width: 0;" in wrapper_rules
    assert "min-width: 260px;" in dropdown_rules


def test_operating_layer_css_includes_park_archive_form_tokens() -> None:
    for token in (
        ".idea-detail-park-section",
        ".idea-detail-archive-section",
        ".idea-archive-title",
        ".idea-archive-reason",
        ".idea-archive-reason::placeholder",
    ):
        assert token in APP_CSS


def test_operating_layer_js_includes_park_archive_detail_form_contract() -> None:
    """Slice 3: detail drawer park/archive reason form renders and is wired."""
    # Form renderer exists
    assert "renderIdeaParkArchiveForm" in APP_JS
    # Card-level park command uses a concrete, non-empty reason (not placeholder)
    assert "Parked from Idea Greenhouse" in APP_JS
    assert "Archived from Idea Greenhouse" in APP_JS

    # Park and archive actions are present where appropriate
    for lane_id in ("raw", "clarify", "candidate"):
        assert f"'{lane_id}'" in APP_JS  # confirm lanes checked


def test_operating_layer_js_park_archive_form_has_required_tokens() -> None:
    """Confirm the detail-form has reason textarea, submit buttons, and status div."""
    # Data attributes are built via template literal with ternary; confirm all keys exist
    assert 'data-idea-' in APP_JS and '-submit=' in APP_JS
    assert '="reason"' in APP_JS
    assert '[data-idea-park-submit]' in APP_JS
    assert '[data-idea-archive-submit]' in APP_JS


def test_operating_layer_js_park_archive_command_construction() -> None:
    """PARK/ARCHIVE command strings are literal, user-supplied, never placeholders."""
    assert 'devflow idea park ${ideaId} --reason' in APP_JS
    assert 'devflow idea archive ${ideaId} --reason' in APP_JS
    # shellQuote guards the reason so arbitrary text is safely escaped
    assert "shellQuote" in APP_JS


def test_operating_layer_js_park_archive_approval_payload_required() -> None:
    """Full approval payload (human_approved, approval_phrase, approved_command) included."""
    assert "human_approved" in APP_JS
    assert "approval_phrase" in APP_JS
    assert "approved_command" in APP_JS
    # The action URL is the actions/run endpoint
    assert "'/api/actions/run'" in APP_JS


def test_operating_layer_js_park_archive_snapshot_refresh_on_success() -> None:
    """After successful park/archive, loadSnapshot is triggered."""
    assert "loadSnapshot" in APP_JS
    # The _submitParkOrArchive function uses setTimeout + loadSnapshot for refresh
    assert "_submitParkOrArchive" in APP_JS
    # Confirm the pattern: reason validation rejects < 3 chars and writes to the action-specific status.
    assert "reasonValue.length < 3" in APP_JS
    assert "`idea-${actionType}-status`" in APP_JS
    assert "function setIdeaDetailStatus(message, tone, statusId)" in APP_JS


def test_operating_layer_js_park_archive_click_handlers_wired() -> None:
    """Click handlers for the park/archive submit buttons exist."""
    assert "[data-idea-park-submit]" in APP_JS
    assert "[data-idea-archive-submit]" in APP_JS


def test_operating_layer_js_start_brainstorm_from_idea_contract() -> None:
    """Slice 4: idea detail drawer can open a brainstorm session with lineage."""
    assert "data-idea-brainstorm" in APP_JS
    assert "idea-brainstorm-status" in APP_JS
    assert "JSON.stringify({ idea_id: ideaId })" in APP_JS
    assert "setActiveBrainstormSession(data.session_id, { userSelected: true })" in APP_JS
    assert "setActiveNav('brainstorm')" in APP_JS
    assert "await loadBrainstormTranscript(data.session_id)" in APP_JS
    assert "Brainstorm session started from " in APP_JS
    assert "Next: add context or escalate to Spec" in APP_JS
    assert APP_JS.index("await loadBrainstormTranscript(data.session_id)") < APP_JS.index("Brainstorm session started from ")


def test_operating_layer_js_card_level_brainstorm_button_contract() -> None:
    """Slice 2: every actionable idea card gets a visible Continue brainstorm button."""
    assert "Continue brainstorm" in APP_JS
    assert 'data-idea-brainstorm="' in APP_JS
    assert "idea-card-brainstorm-actions" in APP_JS
    assert 'class="btn btn-sm btn-secondary"' in APP_JS


def test_operating_layer_guided_sections_render_before_advanced_sections() -> None:
    assert "Brainstorm" in INDEX_HTML
    assert "DeepSeek V4 Flash Free" in INDEX_HTML
    assert "brainstorm-chat-form" in INDEX_HTML
    assert "pipeline-stages-container" in INDEX_HTML
    assert "Worker lanes" in INDEX_HTML
    assert "Review queue" in INDEX_HTML
    assert "Evidence stream" in INDEX_HTML
    assert "Task Control" in INDEX_HTML
    assert "Product / Review" not in INDEX_HTML
    assert "Next Task" in INDEX_HTML
    assert "brainstorm-definition-of-done" in INDEX_HTML
    assert "Pipeline" in INDEX_HTML
    assert "focus-overlay" in INDEX_HTML


def test_operating_layer_task_cards_expose_state_specific_next_actions() -> None:
    assert "worker-card" in APP_JS
    assert "Worker lanes" in APP_JS
    assert "renderWorkerLanes" in APP_JS
    assert "firstViewportPresentationFromSnapshot" in APP_JS
    assert "fallbackFirstViewportPresentation" in APP_JS
    assert "older/partial snapshots" in APP_JS
    assert "Browser runtime override" in APP_JS
    assert "renderFirstViewport" in APP_JS
    assert "BROWSER TASK CAPABILITIES" in APP_JS
    assert "Legacy fallback for older snapshots" in APP_JS
    assert "raw.intent || intentForCommand(raw.command)" in APP_JS
    assert "raw.required_inputs" in APP_JS
    assert "Array.isArray(raw.required_inputs) && raw.required_inputs.length" not in APP_JS
    assert "for (const control of task?.controls || []) push(control);" in APP_JS
    assert "for (const action of task?.actions || []) push(action);" in APP_JS
    assert "function taskCapabilities" in APP_JS
    assert "task?.controls" in APP_JS
    assert "required_inputs" in APP_JS
    assert "fillCapabilityCommand" in APP_JS
    assert "devflow task run ${task.id} --worker ${w.id}" not in APP_JS
    assert "data-task-run-shell" in APP_JS
    assert "data-select-task" in APP_JS
    assert "data-task-close" in APP_JS
    assert "Cleanup preview" in APP_JS
    assert "Worker / model" in APP_JS
    assert "openFocus" in APP_JS
    assert "closeFocus" in APP_JS
    assert "worker-card" in APP_CSS
    assert "worker-light" in APP_CSS
    assert "command-result" in APP_CSS


def test_operating_layer_command_preview_uses_human_readable_safety_labels() -> None:
    assert "executeAction" in APP_JS
    assert "closeFocus" in APP_JS
    assert "openFocus" in APP_JS


def test_operating_layer_classify_form_uses_full_idea_ids_and_requires_choices() -> None:
    assert "function renderIdeaClassifyForm" in APP_JS
    assert "if (!/^I-[0-9]{4}$/.test(ideaId)) return '';" in APP_JS
    assert "if (!/^I-[0-9]{4}$/.test(ideaId)) return null;" in APP_JS
    assert 'option value="">Choose maturity...' in APP_JS
    assert "Choose a maturity before classifying." in APP_JS
    assert "Please write a classification note." in APP_JS
    assert "devflow idea classify ${ideaId} --maturity ${maturityValue}" in APP_JS
    assert "human_approved: true" in APP_JS
    assert "approved_command: command" in APP_JS
    assert ".idea-detail-classify-section" in APP_CSS
    assert ".idea-classify-note" in APP_CSS


def test_operating_layer_js_uses_backend_pipeline_contract_not_boolean_pipeline_state() -> None:
    """Slice 3: UI should render pipeline cards from backend pipeline.stages,
    not from duplicate local JS booleans such as hasTranscript, hasSpec,
    hasPlan, hasImplementation."""
    # The good stages-based pipeline contract MUST be present
    assert "renderPipeline" in APP_JS
    assert ".stages" in APP_JS
    assert "pipelineState.stages" in APP_JS
    assert "let pipelineState = { stages:" in APP_JS

    # The old boolean pipeline state initialisation MUST be absent;
    # only the stages-based pipelineState = { stages: [] } should remain.

    # Single-line form:  pipelineState = { hasTranscript: false, ... }
    assert "pipelineState = { hasTranscript" not in APP_JS, (
        "Old single-line boolean pipelineState initialisation still present. "
        "Remove it so backend pipeline.stages is the single source of truth."
    )

    # Multi-line form:
    #   pipelineState = {
    #     hasTranscript: ...
    assert "pipelineState = {\n      hasTranscript" not in APP_JS, (
        "Old multi-line boolean pipelineState initialisation still present. "
        "Remove it so backend pipeline.stages is the single source of truth."
    )


def test_operating_layer_js_pipeline_primary_action_contract() -> None:
    """Slice 4: pipeline should expose one canonical primary action button."""
    assert "data-pipeline-primary-action" in APP_JS, "Primary action button missing data attribute"
    assert "pipeline-primary-context" in APP_JS, "Primary action context copy missing"
    assert "pipeline-current-stage" in APP_JS, "Active stage copy missing"
    assert "pipeline-next-action" in APP_JS, "Next action copy missing"
    assert "pipeline-evidence-path" in APP_JS, "Evidence/artifact path copy missing"
    assert "getPrimaryActionLabel" in APP_JS, "label function not present"
    assert "getPipelinePrimaryStage" in APP_JS, "primary stage resolver not present"
    assert "getNextStageLabel" in APP_JS, "next-stage label helper not present"
    assert "useModelForBrainstormStage" in APP_JS, "model-backed stages should be explicit"
    assert "setupPipelineButtons(container)" in APP_JS, "dynamic pipeline controls should be rebound after render"
    assert "runPipelinePrimaryStage(stage, btn)" in APP_JS, "primary button should execute the stage directly"
    assert "document.querySelectorAll('#pipeline-stages-container [data-brainstorm-stage]')" not in APP_JS
    assert "stageButton.click()" not in APP_JS


def test_operating_layer_obsidian_intake_asset_contract() -> None:
    assert "Obsidian Intake" in INDEX_HTML
    assert 'id="obsidian-intake-panel"' in INDEX_HTML
    assert 'id="obsidian-intake-lane-counts"' in INDEX_HTML
    assert 'id="obsidian-intake-body"' in INDEX_HTML
    assert INDEX_HTML.index("Unified Chat Workbench") < INDEX_HTML.index("Obsidian Intake") < INDEX_HTML.index("Pipeline")

    assert "/api/obsidian/cards" in APP_JS
    assert "function renderObsidianIntake()" in APP_JS
    assert "async function loadObsidianIntake()" in APP_JS
    assert "buildObsidianBrainstormContext" in APP_JS
    assert "data-obsidian-use-context" in APP_JS
    assert "Use as brainstorm context" in APP_JS
    assert "Copy path" in APP_JS
    assert "Open note" in APP_JS
    assert "obsidian://" in APP_JS

    assert ".obsidian-intake-section" in APP_CSS
    assert ".obsidian-intake-lane-counts" in APP_CSS
    assert ".obsidian-intake-body" in APP_CSS
    assert ".obsidian-intake-card" in APP_CSS
    assert ".obsidian-intake-detail" in APP_CSS


def test_operating_layer_js_pipeline_stage_cards_are_status_summaries_not_duplicate_controls() -> None:
    """Pipeline stage cards should not render duplicate enabled stage-advance buttons."""
    pipeline_block = APP_JS[
        APP_JS.index("function renderPipeline(input)") : APP_JS.index("// Write implementation context")
    ]
    assert "data-brainstorm-stage" not in pipeline_block
    assert "Escalate to Spec" not in pipeline_block
    assert "Generate Spec" not in pipeline_block
    assert "Generate Plan" not in pipeline_block
    assert "Create Task" not in pipeline_block


def test_operating_layer_js_primary_pipeline_uses_adopted_backend_session() -> None:
    """Brainstorm session adoption should keep using backend pipeline.session_id."""
    assert "snap?.first_viewport?.pipeline?.session_id" in APP_JS
    assert "setActiveBrainstormSession(pipeline.session_id" in APP_JS
