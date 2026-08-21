from types import SimpleNamespace

import app
from app import build_micro_event_summary, session_micro_events


def test_micro_event_summary_describes_behavior_without_inventing_transcript() -> None:
    assert build_micro_event_summary("hesitation", "pending") == "检测到犹豫信号，待人工确认"
    assert build_micro_event_summary("thinking_pause", "confirmed") == "检测到思考停顿信号，已确认"
    assert build_micro_event_summary("other", "rejected") == "检测到其他微表征信号，已忽略"


def test_session_event_response_keeps_summary_separate_from_transcript(monkeypatch) -> None:
    row = SimpleNamespace(
        id="event-1",
        event_type="hesitation",
        start_ms=100,
        end_ms=300,
        confidence=0.8,
        transcript=None,
        evidence_uri="detector://event-1",
        evidence_status="pending",
    )

    class Query:
        def filter_by(self, **_):
            return self

        def order_by(self, *_):
            return self

        def all(self):
            return [row]

    db = SimpleNamespace(query=lambda _: Query())
    user = SimpleNamespace(id=2)
    monkeypatch.setattr(app, "get_owned_session", lambda *_: None)

    result = session_micro_events(1, db=db, user=user)

    assert result["items"][0]["summary"] == "检测到犹豫信号，待人工确认"
    assert result["items"][0]["transcript"] is None
