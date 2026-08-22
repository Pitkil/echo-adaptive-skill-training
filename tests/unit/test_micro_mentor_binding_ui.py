from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_mentor_upload_requires_a_selected_learner_when_speaker_is_confirmed() -> None:
    html = (REPOSITORY_ROOT / "apps" / "api" / "index.html").read_text(encoding="utf-8")
    script = (
        REPOSITORY_ROOT / "apps" / "api" / "web" / "echo-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="speaker-confirmed"' in html
    assert 'id="mentor-learner-select" disabled' in html
    assert "/v1/micro/learners" in script
    assert 'data.append("learner_id", learnerId)' in script
    assert "if (speakerConfirmed && !learnerId)" in script
    assert 'addEventListener("change", syncSpeakerBindingControl)' in script
