from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INDEX = (REPOSITORY_ROOT / "apps" / "api" / "index.html").read_text(encoding="utf-8")
SCRIPT = (REPOSITORY_ROOT / "apps" / "api" / "web" / "echo-app.js").read_text(
    encoding="utf-8"
)
STYLES = (REPOSITORY_ROOT / "apps" / "api" / "web" / "echo-shell.css").read_text(
    encoding="utf-8"
)


def test_learning_workspace_only_exposes_user_facing_content() -> None:
    assert "幕后依据" not in INDEX
    assert "这轮如何得出" not in INDEX
    assert 'class="trace-panel"' not in INDEX
    assert 'id="trace-detail"' not in INDEX
    assert "Trace：" not in SCRIPT
    assert "agent-loop" not in SCRIPT


def test_demo_uses_product_roles_instead_of_team_ownership() -> None:
    assert "成员 A" not in INDEX
    assert "成员 B" not in INDEX
    assert "成员 C" not in INDEX
    assert "成员 D" not in INDEX
    for role_name in ("学习情况分析 Agent", "内容生成 Agent", "内容检查 Agent", "下一步安排 Agent"):
        assert role_name in INDEX


def test_each_role_gets_a_focused_navigation_and_manager_preview() -> None:
    assert INDEX.count('class="nav-item learner-only') == 5
    assert 'class="nav-item manager-only" data-view="courses"' in INDEX
    assert "学习者视角预览" in INDEX
    assert 'class="nav-item mentor-only" data-view="content"' in INDEX
    assert INDEX.count('class="nav-item system-admin-only"') == 2
    assert '$$(".learner-only")' in SCRIPT
    assert '$$(".mentor-only")' in SCRIPT
    assert 'showView({mentor: "content", system_admin: "members"}[state.role] || "courses")' in SCRIPT


def test_workspace_has_accessible_and_actionable_start_state() -> None:
    assert 'class="skip-link" href="#main-content"' in INDEX
    assert 'id="main-content"' in INDEX
    assert INDEX.count("data-chat-prompt=") == 3
    assert "button.dataset.chatPrompt" in SCRIPT
    assert "测验阶段由 ECHO 自动安排" in INDEX
    assert '.assessment-next {' in STYLES
    assert 'align-items: end;' in STYLES
    assert '.assessment-next .button {' in STYLES
    assert 'min-height: 36px;\n    align-self: end;' in STYLES


def test_visual_system_has_desktop_and_mobile_layout_contracts() -> None:
    assert '--canvas: #f4fafd' in STYLES
    assert 'grid-template-columns: 224px minmax(0, 1fr)' in STYLES
    assert '@media (max-width: 620px)' in STYLES
    assert '.resource-card, .resource-card:first-child' in STYLES
    assert '.resource-list > .empty-state' in STYLES
    assert 'grid-column: 1 / -1' in STYLES
    assert 'overflow-x: hidden' in STYLES
    assert '@media (min-width: 861px)' in STYLES
    assert '@media (min-width: 861px) {' in STYLES
    assert '.app-shell { min-height: calc(100dvh / .9); zoom: .9; }' in STYLES
    assert '.sidebar { height: calc(100dvh / .9); }' in STYLES


def test_learner_insight_exposes_required_visual_report_views() -> None:
    assert 'id="blindspot-chart"' in INDEX
    assert '资源难度匹配曲线' in INDEX
    assert 'renderBlindspotChart' in SCRIPT
    assert 'type: "line"' in SCRIPT
    assert '.learning-path::before' in STYLES
    assert '.path-grid { align-items: start; }' in STYLES
    assert '#difficulty-chart { width: 100% !important; height: 250px !important;' in STYLES


def test_learner_workspace_exposes_current_learning_path() -> None:
    assert 'id="workspace-learning-path"' in INDEX
    assert 'id="workspace-path-next-title"' in INDEX
    assert 'renderWorkspacePath' in SCRIPT
    assert 'grid-template-columns: minmax(0, 1fr) clamp(280px, 22vw, 340px)' in STYLES
    assert "当前学习任务" in INDEX
    assert "当前优先知识点" in INDEX
    assert '#view-workspace { width: 100%; padding: 0 0 22px; }' in STYLES
    assert 'align-items: stretch;' in STYLES


def test_learner_exposes_decision_visualization_for_path_choices() -> None:
    assert 'aria-label="学习决策流程"' in INDEX
    assert 'class="decision-flow"' in INDEX
    assert 'class="workspace-decision-rail"' in INDEX
    assert 'id="course-path-difficulty"' in INDEX
    assert 'workspace-path-evidence' in SCRIPT
    assert '.decision-flow {' in STYLES
    assert '.workspace-decision-rail {' in STYLES


def test_chat_history_has_internal_scroll_boundary_and_jump_control() -> None:
    assert 'id="chat-jump-bottom"' in INDEX
    assert 'syncChatScrollControl' in SCRIPT
    assert 'scrollChatToBottom' in SCRIPT
    assert 'height: clamp(640px, calc(100dvh - 114px), 900px)' in STYLES
    assert '.chat-messages { min-height: 0;' in STYLES
    assert '.chat-jump.visible' in STYLES


def test_chat_submission_exposes_pending_feedback() -> None:
    assert '正在根据你的学习证据整理下一步' in SCRIPT
    assert 'setChatSending(true)' in SCRIPT
    assert 'aria-busy' in SCRIPT
    assert '.message.pending' in STYLES
    assert 'max-height: 76px; overflow-y: auto; resize: none;' in STYLES


def test_request_ids_work_without_browser_random_uuid_support() -> None:
    assert "function createRequestId()" in SCRIPT
    assert "window.crypto?.getRandomValues" in SCRIPT
    assert "request_id: createRequestId()" in SCRIPT
    assert "request_id: crypto.randomUUID" not in SCRIPT


def test_assistant_messages_render_safe_inline_markdown() -> None:
    assert "function renderAssistantMessage" in SCRIPT
    assert "document.createTextNode" in SCRIPT
    assert 'document.createElement(isStrong ? "strong" : "code")' in SCRIPT
    workspace_message_flow = SCRIPT.split("function appendMessage", 1)[1].split(
        "function syncChatScrollControl", 1
    )[0]
    assert 'renderAssistantMessage(message, content);' in workspace_message_flow
    assert "message.innerHTML = content" not in SCRIPT
    assert ".message.assistant strong" in STYLES
    assert ".message.assistant code" in STYLES


def test_workspace_composer_preserves_desktop_and_mobile_spacing() -> None:
    assert "padding: 24px clamp(14px, 1.8vw, 26px) 5px;" in STYLES
    assert "grid-template-rows: auto minmax(170px, 1fr) auto;" in STYLES
    assert ".composer { display: grid; gap: 12px;" in STYLES
    assert "transform: translateY(8px);" in STYLES
    assert "padding: 9px 16px 10px 15px;" in STYLES
    assert "margin-top: -55px; padding: 0 16px 9px;" in STYLES
    assert ".composer-actions > .button.primary { transform: translateY(4px); }" in STYLES
    assert ".composer-actions > .button.primary svg { width: 15px; height: 15px;" in STYLES
    assert ".composer-actions > .button.primary { width: 100%; transform: none; }" in STYLES


def test_resource_generation_exposes_progress_and_failure_feedback() -> None:
    assert 'id="generate-resources-label"' in INDEX
    assert 'label.textContent = "正在生成，请稍候"' not in SCRIPT
    assert 'button.setAttribute("aria-busy", "true")' in SCRIPT
    assert 'class="resource-generation-state" role="status"' in SCRIPT
    assert "资源列表暂时无法读取" in SCRIPT
    assert '.resource-generation-state {' in STYLES
    assert 'data-resource-type="practice_guide"' in INDEX
    assert 'data-resource-type="staged_test"' in INDEX
    assert '下载 Word' in SCRIPT
    assert '/download`' in SCRIPT
    assert '开始阶段练习' in SCRIPT
    assert '待人工发布' not in SCRIPT
    assert '.button.is-loading > svg { animation: none; }' in STYLES
    assert 'class="resource-toolbar"' in INDEX
    assert 'data-resource-type="practice_guide"><i data-lucide="list-checks"></i><span>' in INDEX
    assert 'grid-template-columns: repeat(3, minmax(0, 1fr))' in STYLES
    assert '草稿，可预览' not in SCRIPT
    assert '下载${isDraft' not in SCRIPT
    assert 'data-publish-resource' not in SCRIPT


def test_resource_generation_does_not_allow_stale_list_requests_to_replace_loading_state() -> None:
    assert 'isGeneratingResources: false' in SCRIPT
    assert 'resourceLoadRequestId: 0' in SCRIPT
    assert '++state.resourceLoadRequestId;' in SCRIPT
    assert 'await loadResources({allowDuringGeneration: true});' in SCRIPT
    assert 'async function loadResources({allowDuringGeneration = false} = {})' in SCRIPT
    assert 'if (state.isGeneratingResources && !allowDuringGeneration) return;' in SCRIPT
    assert 'requestId !== state.resourceLoadRequestId' in SCRIPT


def test_auth_layout_scales_with_short_desktop_viewports() -> None:
    assert 'min(6.1vw, 9.5vh)' in STYLES
    assert '.auth-visual img {' in STYLES
    assert 'position: absolute;' in STYLES
    assert '@media (min-width: 621px) and (max-height: 800px)' in STYLES
    assert '@media (min-width: 861px) and (max-height: 620px)' in STYLES
    assert '.auth-panel { align-items: start; overflow-y: auto; }' in STYLES


def test_learner_audio_panel_uses_a_finished_product_control() -> None:
    assert 'class="upload-panel learner-audio-panel"' in INDEX
    assert 'class="audio-input-grid"' in INDEX
    assert 'for="learner-audio-file"' in INDEX
    assert 'id="learner-audio-file-name"' in INDEX
    assert 'id="learner-job-status-text"' in INDEX
    assert 'setLearnerJobStatus' in SCRIPT
    assert '.audio-input-button.is-recording' in STYLES
    assert '.audio-status[data-state="ready"]' in STYLES
    assert '.upload-grid:has(> .manager-only.hidden)' in STYLES


def test_general_audio_submission_closes_the_completed_panel() -> None:
    audio_submission_flow = SCRIPT.split("async function uploadLearnerAudio()", 1)[1].split(
        "async function submitConfirmedOralAnswer", 1
    )[0]
    assert "function closeSubmittedLearnerAudioPanel" in SCRIPT
    assert 'panel.classList.add("hidden");' in SCRIPT
    assert "const isVideoOralAttempt" in audio_submission_flow
    assert "closeSubmittedLearnerAudioPanel();" in audio_submission_flow
    assert audio_submission_flow.index("closeSubmittedLearnerAudioPanel();") < audio_submission_flow.index(
        "if (!isVideoOralAttempt)"
    )
    assert "后台完成转写与微表征分析" in audio_submission_flow
    assert 'panel.dataset.audioState = "awaiting_confirmation";' in SCRIPT
    assert '[data-audio-state="awaiting_confirmation"] .audio-submit' in STYLES


def test_course_center_exposes_one_real_course_and_honest_samples() -> None:
    assert 'data-view="courses"' in INDEX
    assert 'id="view-courses" class="view active"' in INDEX
    assert 'id="course-center-title"' in INDEX
    assert 'id="course-module-list"' in INDEX
    assert INDEX.count("课程样例") == 3
    assert INDEX.count("即将开放") == 3
    assert 'id="course-continue"' in INDEX
    assert 'renderCourseCenter' in SCRIPT
    assert 'showView("courses")' in SCRIPT


def test_course_module_cards_open_video_learning() -> None:
    select_module_flow = SCRIPT.split("async function selectCourseModule(moduleId)", 1)[1].split(
        "function openCourseWorkspace", 1
    )[0]
    assert 'openVideoLearning();' in select_module_flow
    assert 'showView("workspace")' not in select_module_flow
    assert '"继续视频伴学"' in SCRIPT
    assert '"视频伴学"' in SCRIPT


def test_video_learning_never_starts_microphone_implicitly() -> None:
    assert 'id="course-video-player"' in INDEX
    assert 'id="course-video-list"' in INDEX
    assert "讲师上传的视频会保存在服务器，并记录你的观看进度" in INDEX
    assert "视频播放本身不会开启麦克风" in INDEX
    assert 'id="video-start-evidence"' in INDEX
    assert 'id="video-knowledge-point"' in INDEX
    assert 'id="video-evidence-context"' in INDEX
    assert 'id="video-inline-recorder"' in INDEX
    assert 'id="video-inline-recorder-content"' in INDEX
    assert 'id="video-review-progress"' in INDEX
    assert 'id="learner-audio-panel"' in INDEX
    assert "startVideoEvidence" in SCRIPT
    inline_flow = SCRIPT.split("function startVideoEvidence()", 1)[1].split(
        "function mountVideoEvidenceRecorder()", 1
    )[0]
    assert 'mountVideoEvidenceRecorder();' in inline_flow
    assert 'showView("evidence")' not in inline_flow
    assert '$("#video-inline-recorder").scrollIntoView' in inline_flow
    assert "function restoreEvidenceRecorder()" in SCRIPT
    assert "function setVideoReviewProgress" in SCRIPT
    assert "activeVideoKnowledgePointId: null" in SCRIPT
    assert "const checkpointKnowledgePointId = state.activeCheckpoint" in SCRIPT
    assert "knowledgePointId: checkpointKnowledgePointId" in SCRIPT
    assert 'data.append("knowledge_point_id"' in SCRIPT
    assert "getUserMedia({audio: true})" in SCRIPT
    assert 'addEventListener("play", startOrStopRecording)' not in SCRIPT
    assert 'addEventListener("timeupdate", startOrStopRecording)' not in SCRIPT
    assert '.video-learning-grid' in STYLES
    assert '.video-evidence-context' in STYLES
    assert '.video-inline-recorder {' in STYLES


def test_video_learning_has_an_in_page_echo_companion() -> None:
    assert 'id="video-echo-float"' in INDEX
    assert 'aria-controls="video-echo-panel"' in INDEX
    assert 'id="video-echo-panel"' in INDEX
    assert 'id="video-echo-form"' in INDEX
    assert "function toggleVideoEchoPanel" in SCRIPT
    assert "function bindVideoEchoDrag" in SCRIPT
    assert "function positionVideoEchoPanel" in SCRIPT
    assert 'trigger.setPointerCapture(pointerId);' in SCRIPT
    assert 'trigger.dataset.dragged === "true"' in SCRIPT
    assert "async function sendVideoEchoMessage" in SCRIPT
    assert 'appendVideoEchoMessage("user", userInput)' in SCRIPT
    assert 'api("/chat"' in SCRIPT
    assert '.video-echo-float {' in STYLES
    assert '.video-echo-panel {' in STYLES
    assert 'cursor: grab;' in STYLES
    assert '.video-echo-float.is-dragging' in STYLES


def test_learner_and_admin_video_knowledge_points_have_separate_loaders() -> None:
    assert SCRIPT.count("async function loadVideoKnowledgePoints()") == 1
    assert SCRIPT.count("async function loadAdminVideoKnowledgePoints()") == 1
    learner_loader = SCRIPT.split("async function loadVideoKnowledgePoints()", 1)[1].split(
        "function releaseVideoObjectUrl", 1
    )[0]
    admin_loader = SCRIPT.split("async function loadAdminVideoKnowledgePoints()", 1)[1].split(
        "async function loadAdminVideos", 1
    )[0]
    assert '$("#video-knowledge-point")' in learner_loader
    assert '$("#video-knowledge-point-select")' in admin_loader
    assert 'if (viewName === "video") loadVideoKnowledgePoints();' in SCRIPT
    assert "loadAdminVideoKnowledgePoints();" in SCRIPT


def test_video_player_uses_lightweight_preload_and_throttled_progress() -> None:
    assert 'id="course-video-player" preload="metadata" playsinline' in INDEX
    assert "now - state.lastVideoProgressSave < 15000" in SCRIPT
    assert 'lastVideoProgressSnapshot: ""' in SCRIPT
    assert 'addEventListener("waiting"' in SCRIPT
    assert 'addEventListener("stalled"' in SCRIPT
    assert 'textContent = "已暂停，等待口述练习"' in SCRIPT


def test_video_oral_flow_has_compact_visible_progress_and_toast() -> None:
    assert '$("#video-checkpoint").classList.add("hidden");' in SCRIPT
    assert 'requestAnimationFrame(() => {' in SCRIPT
    assert '.video-review-progress {' in STYLES
    assert 'max-width: min(260px, calc(100vw - 32px))' in STYLES


def test_video_privacy_note_is_removed_and_resource_empty_state_is_compact() -> None:
    assert 'video-privacy-note' not in INDEX
    assert 'data-lucide="mic-off"' not in INDEX
    assert '.resource-list > .empty-state { grid-column: 1 / -1; display: grid;' in STYLES
    assert '.resource-list > .empty-state { grid-column: 1 / -1; min-height:' not in STYLES


def test_video_checkpoint_advances_and_closes_after_audio_submission() -> None:
    checkpoint_flow = SCRIPT.split("function handleVideoTimeUpdate()", 1)[1].split(
        "function showVideoCheckpoint", 1
    )[0]
    assert "return pauseForPendingVideoCheckpoint();" in checkpoint_flow
    assert "function pauseForPendingVideoCheckpoint" in SCRIPT
    assert "void loadCourseCheckpoints(video.id);" in SCRIPT
    assert "window.requestAnimationFrame(pauseForPendingVideoCheckpoint);" in SCRIPT
    assert "isLoadingVideoCheckpoints: false" in SCRIPT
    assert "if (state.isLoadingVideoCheckpoints) return;" in SCRIPT
    assert "VIDEO_CHECKPOINT_TOLERANCE_SECONDS = 0.75" in SCRIPT
    assert "promptedCheckpointIds: new Set()" in SCRIPT
    assert "&& !state.promptedCheckpointIds.has(item.id)" in SCRIPT
    assert "state.promptedCheckpointIds.add(pending.id);" in SCRIPT
    assert "&& !state.triggeredCheckpointIds.has(item.id)" not in SCRIPT
    assert "state.triggeredCheckpointIds.add(state.videoEvidenceContext.checkpointId);" in SCRIPT
    assert "if (state.activeCheckpoint?.id) state.triggeredCheckpointIds.add" in SCRIPT
    upload_flow = SCRIPT.split("async function uploadLearnerAudio()", 1)[1].split(
        "async function submitConfirmedOralAnswer", 1
    )[0]
    assert '$("#video-checkpoint").classList.add("hidden")' in upload_flow


def test_video_uses_zoom_safe_synchronized_controls() -> None:
    assert '<video id="course-video-player" preload="metadata" playsinline' in INDEX
    assert 'id="video-seek" type="range"' in INDEX
    assert "function syncVideoControls()" in SCRIPT
    assert "function seekCourseVideo(event)" in SCRIPT
    assert 'addEventListener("input", seekCourseVideo)' in SCRIPT
    assert '.video-controls input[type="range"]::-webkit-slider-runnable-track' in STYLES
    assert "function revealVideoControls()" in SCRIPT
    assert '.video-frame.is-playing .video-controls:not(.is-active):not(:focus-within)' in STYLES


def test_course_and_video_views_have_mobile_collapse_rules() -> None:
    assert '.course-hero { min-height: 0; border-radius: 20px; }' in STYLES
    assert '.course-module-item { grid-template-columns: 43px minmax(0, 1fr) 18px;' in STYLES
    assert '.video-learning-grid { grid-template-columns: minmax(0, 1fr); }' in STYLES
    assert '.video-source-actions, .video-source-actions .button { width: 100%; }' in STYLES
    assert '.video-lesson-heading > div, .video-lesson-heading h2 { width: 100%; max-width: 100%; }' in STYLES
