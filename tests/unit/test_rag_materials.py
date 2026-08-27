from __future__ import annotations

import app as app_module
from app import app, create_access_token, ensure_catalog, get_db
from database import (
    Base,
    KnowledgeBase,
    KnowledgePoint,
    Organization,
    TrainingModule,
    Upload,
    User,
    UserRole,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class FakePunditRAGClient:
    configured = True
    import_configured = True

    def ensure_knowledge_base(self, *, name, description=""):
        assert name
        assert "Microsoft" in description
        return {"kb_id": "external-kb-1"}

    def ingest_document(self, **kwargs):
        assert kwargs["external_knowledge_base_id"] == "external-kb-1"
        assert kwargs["content"] == b"official markdown"
        return {
            "document_id": "external-document-1",
            "task_id": "external-task-1",
            "status": "pending",
        }

    def get_import_status(self, task_id):
        assert task_id == "external-task-1"
        return {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "error": "",
        }


def test_material_upload_maps_punditrag_ids_and_tracks_async_status(monkeypatch, tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = session_factory()
    ensure_catalog(db)
    organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
    mentor = User(
        organization_id=organization.id,
        username="rag-material-mentor",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    db.add(mentor)
    db.commit()
    db.refresh(mentor)
    module = db.query(TrainingModule).order_by(TrainingModule.sequence).first()

    monkeypatch.setattr(app_module, "PunditRAGClient", FakePunditRAGClient)
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(mentor)}"}
    response = client.post(
        f"/v1/knowledge-bases/{module.knowledge_base_id}/documents",
        data={
            "module_id": str(module.id),
            "source_title": "Semantic Kernel overview",
            "source_url": "https://learn.microsoft.com/semantic-kernel/overview/",
            "source_section": "What is Semantic Kernel?",
            "source_version": "2026-08-19",
        },
        files={"document": ("overview.md", b"official markdown", "text/markdown")},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    knowledge_base = db.query(KnowledgeBase).filter_by(id=module.knowledge_base_id).one()
    upload = db.query(Upload).one()
    assert knowledge_base.external_ref == "external-kb-1"
    assert upload.external_document_id == "external-document-1"
    assert upload.external_task_id == "external-task-1"
    assert upload.source_version == "2026-08-19"

    listing = client.get(
        f"/v1/knowledge-bases/{module.knowledge_base_id}/documents?module_id={module.id}",
        headers=headers,
    )
    assert listing.status_code == 200
    assert listing.json()["items"][0]["index_status"] == "completed"

    app.dependency_overrides.clear()
    db.close()


def test_material_upload_rejects_non_official_source(monkeypatch, tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = session_factory()
    ensure_catalog(db)
    organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
    mentor = User(
        organization_id=organization.id,
        username="rag-invalid-source-mentor",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    db.add(mentor)
    db.commit()
    db.refresh(mentor)
    module = db.query(TrainingModule).order_by(TrainingModule.sequence).first()
    monkeypatch.setattr(app_module, "PunditRAGClient", FakePunditRAGClient)
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    response = TestClient(app).post(
        f"/v1/knowledge-bases/{module.knowledge_base_id}/documents",
        data={
            "module_id": str(module.id),
            "source_title": "Unofficial article",
            "source_url": "https://example.com/semantic-kernel",
            "source_section": "Overview",
            "source_version": "2026-08-19",
        },
        files={"document": ("article.md", b"content", "text/markdown")},
        headers={"Authorization": f"Bearer {create_access_token(mentor)}"},
    )

    assert response.status_code == 400
    assert db.query(Upload).count() == 0
    app.dependency_overrides.clear()
    db.close()


def test_official_search_retries_with_knowledge_point_when_first_query_is_empty(
    monkeypatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = session_factory()
    ensure_catalog(db)
    module = db.query(TrainingModule).order_by(TrainingModule.sequence).first()
    point = (
        db.query(KnowledgePoint)
        .filter_by(module_id=module.id)
        .order_by(KnowledgePoint.sequence)
        .first()
    )
    knowledge_base = db.query(KnowledgeBase).filter_by(id=module.knowledge_base_id).one()
    knowledge_base.external_ref = "external-kb-1"
    organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
    mentor = User(
        organization_id=organization.id,
        username="rag-fallback-mentor",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    db.add(mentor)
    db.flush()
    db.add(
        Upload(
            user_id=mentor.id,
            knowledge_base_id=knowledge_base.id,
            module_id=module.id,
            filename="official.md",
            filepath="/data/uploads/official.md",
            file_type="text/markdown",
            file_size=17,
            source_title="Understanding the kernel in Semantic Kernel",
            source_url="https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
            source_section="Build a kernel with services and plugins",
            source_version="2026-08-27",
            external_document_id="external-document-1",
            index_status="completed",
        )
    )
    db.commit()

    class EmptyThenEvidenceClient:
        configured = True
        queries: list[str] = []

        def search(self, query, *_args, **_kwargs):
            self.queries.append(query)
            if len(self.queries) == 1:
                return []
            return [
                {
                    "text": "Official evidence",
                    "metadata": {"external_document_id": "external-document-1"},
                }
            ]

    fake_client = EmptyThenEvidenceClient()
    monkeypatch.setattr(app_module, "PunditRAGClient", lambda: fake_client)

    evidence, error = app_module.search_official_evidence(
        db,
        query="a query that does not retrieve a document",
        knowledge_base_id=knowledge_base.id,
        module_id=module.id,
        trace_id="trace-fallback",
        knowledge_point_ids=[point.id],
    )

    assert error is None
    assert len(evidence) == 1
    assert fake_client.queries == [
        "a query that does not retrieve a document",
        f"{point.code} {point.name}",
    ]
    assert evidence[0]["metadata"]["source_url"].startswith(
        "https://learn.microsoft.com/"
    )
    db.close()
