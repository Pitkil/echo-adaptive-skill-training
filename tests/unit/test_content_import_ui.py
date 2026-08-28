from __future__ import annotations

from pathlib import Path

from app import app
from fastapi.testclient import TestClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_content_import_ui_exposes_two_separate_workflows() -> None:
    html = (REPOSITORY_ROOT / "apps" / "api" / "index.html").read_text(encoding="utf-8")
    script = (
        REPOSITORY_ROOT / "apps" / "api" / "web" / "echo-app.js"
    ).read_text(encoding="utf-8")

    assert 'data-import-tab="materials"' in html
    assert 'data-import-tab="quizzes"' in html
    assert 'id="material-module-select"' in html
    assert 'id="knowledge-source-title"' in html
    assert 'id="knowledge-source-url"' in html
    assert 'id="knowledge-source-section"' in html
    assert 'id="knowledge-source-version"' in html
    assert 'id="quiz-module-select"' in html
    assert 'id="quiz-knowledge-select"' in html
    assert 'id="quiz-preview-section"' in html
    assert 'id="confirm-quiz-import"' in html
    assert "/v1/quiz-imports/preview" in script
    assert 'data.append("source_url", sourceUrl)' in script
    assert "/confirm" in script


def test_frontend_uses_profile_driven_resources_and_admin_navigation() -> None:
    html = (REPOSITORY_ROOT / "apps" / "api" / "index.html").read_text(encoding="utf-8")
    script = (
        REPOSITORY_ROOT / "apps" / "api" / "web" / "echo-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="resource-difficulty"' not in html
    assert 'id="resource-difficulty-label"' in html
    assert 'data-view="members"' in html
    assert "system-admin-only" in html
    assert "/v1/admin/users" in script
    assert "系统在线" in script
    assert "PunditRAG 架构" not in script
    assert "resetPrivilegedViews();" in script
    assert 'showView("workspace");' in script


def test_frontend_uses_one_server_owned_assessment_action() -> None:
    html = (REPOSITORY_ROOT / "apps" / "api" / "index.html").read_text(encoding="utf-8")
    script = (
        REPOSITORY_ROOT / "apps" / "api" / "web" / "echo-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="assessment-next"' in html
    assert 'id="assessment-action"' in html
    assert 'id="quiz-purpose-select"' not in html
    assert 'id="quick-quiz"' not in html
    assert "/assessment-progress" in script
    assert 'Trace：${meta.trace_id' not in script
    assert "部分辅助能力暂不可用，本轮学习记录已保留" in script
    assert "completed_degraded" not in script


def test_frontend_responses_disable_stale_browser_cache() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/web/echo-app.js?v=0.5.0")
        stylesheet = client.get("/web/echo-shell.css?v=0.5.0")

    assert page.headers["cache-control"] == "no-store, max-age=0"
    assert script.headers["cache-control"] == "no-store, max-age=0"
    assert stylesheet.headers["cache-control"] == "no-store, max-age=0"
    assert 'echo-app.js?v=' in page.text
    assert 'echo-shell.css?v=' in page.text
