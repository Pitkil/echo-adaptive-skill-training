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


def test_workspace_has_accessible_and_actionable_start_state() -> None:
    assert 'class="skip-link" href="#main-content"' in INDEX
    assert 'id="main-content"' in INDEX
    assert INDEX.count("data-chat-prompt=") == 3
    assert "button.dataset.chatPrompt" in SCRIPT
    assert "测验阶段由 ECHO 自动安排" in INDEX


def test_visual_system_has_desktop_and_mobile_layout_contracts() -> None:
    assert '--canvas: #f4fafd' in STYLES
    assert 'grid-template-columns: 272px minmax(0, 1fr)' in STYLES
    assert '@media (max-width: 620px)' in STYLES
    assert '.resource-card, .resource-card:first-child' in STYLES
    assert '.resource-list > .empty-state' in STYLES
    assert 'grid-column: 1 / -1' in STYLES
    assert 'overflow-x: hidden' in STYLES


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


def test_video_learning_never_starts_microphone_implicitly() -> None:
    assert 'id="course-video-player"' in INDEX
    assert 'id="course-video-list"' in INDEX
    assert "讲师上传的视频会保存在服务器，并记录你的观看进度" in INDEX
    assert "视频播放本身不会开启麦克风" in INDEX
    assert 'id="video-start-evidence"' in INDEX
    assert 'id="video-knowledge-point"' in INDEX
    assert 'id="video-evidence-context"' in INDEX
    assert "startVideoEvidence" in SCRIPT
    assert 'data.append("knowledge_point_id"' in SCRIPT
    assert "getUserMedia({audio: true})" in SCRIPT
    assert 'addEventListener("play", startOrStopRecording)' not in SCRIPT
    assert 'addEventListener("timeupdate", startOrStopRecording)' not in SCRIPT
    assert '.video-learning-grid' in STYLES
    assert '.video-evidence-context' in STYLES


def test_course_and_video_views_have_mobile_collapse_rules() -> None:
    assert '.course-hero { min-height: 0; border-radius: 20px; }' in STYLES
    assert '.course-module-item { grid-template-columns: 43px minmax(0, 1fr) 18px;' in STYLES
    assert '.video-learning-grid { grid-template-columns: minmax(0, 1fr); }' in STYLES
    assert '.video-source-actions, .video-source-actions .button { width: 100%; }' in STYLES
