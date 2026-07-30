from __future__ import annotations

from pathlib import Path

import pytest
from app import ensure_catalog
from catalog import (
    KNOWLEDGE_BASE_CODE,
    MODULE_SPECS,
    ORGANIZATION_CODE,
    PROGRAM_CODE,
    PROGRAM_NAME,
)
from database import (
    Base,
    KnowledgeBase,
    KnowledgePoint,
    Organization,
    Quiz,
    TrainingModule,
    TrainingProgram,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.mark.parametrize(
    ("legacy_kb_code", "legacy_program_code"),
    [
        ("RAG-KB", "RAG-ENGINEERING"),
        ("MS-AF-OFFICIAL", "MS-AF-ENGINEERING"),
    ],
)
def test_legacy_demo_catalog_is_migrated_in_place_and_idempotent(
    legacy_kb_code: str,
    legacy_program_code: str,
) -> None:
    db = make_session()
    organization = Organization(code=ORGANIZATION_CODE, name="Legacy organization")
    db.add(organization)
    db.flush()
    knowledge_base = KnowledgeBase(
        organization_id=organization.id,
        code=legacy_kb_code,
        name="Legacy knowledge base",
    )
    program = TrainingProgram(
        organization_id=organization.id,
        code=legacy_program_code,
        name="Legacy training program",
    )
    db.add_all([knowledge_base, program])
    db.flush()
    module = TrainingModule(
        program_id=program.id,
        knowledge_base_id=knowledge_base.id,
        code="M1",
        name="Legacy module",
        sequence=1,
    )
    db.add(module)
    db.flush()
    point = KnowledgePoint(
        module_id=module.id,
        code="M1-KP1",
        name="Legacy point",
        sequence=1,
    )
    db.add(point)
    db.flush()
    quiz = Quiz(
        module_id=module.id,
        knowledge_point_id=point.id,
        content="请说明“Legacy point”在旧演示领域中的核心目标。",
        answer="Legacy point",
        type="Short",
    )
    db.add(quiz)
    db.commit()
    original_ids = (knowledge_base.id, program.id, module.id, point.id, quiz.id)

    ensure_catalog(db)
    ensure_catalog(db)

    migrated_kb = db.query(KnowledgeBase).filter_by(code=KNOWLEDGE_BASE_CODE).one()
    migrated_program = db.query(TrainingProgram).filter_by(code=PROGRAM_CODE).one()
    modules = (
        db.query(TrainingModule)
        .filter_by(program_id=migrated_program.id)
        .order_by(TrainingModule.sequence)
        .all()
    )
    points = (
        db.query(KnowledgePoint)
        .filter_by(module_id=modules[0].id)
        .order_by(KnowledgePoint.sequence)
        .all()
    )
    migrated_quiz = db.query(Quiz).filter_by(id=quiz.id).one()

    assert migrated_program.name == PROGRAM_NAME
    assert (migrated_kb.id, migrated_program.id, modules[0].id, points[0].id, migrated_quiz.id) == original_ids
    assert [item.code for item in modules] == ["M1", "M2", "M3"]
    assert [item.name for item in modules] == [spec["name"] for spec in MODULE_SPECS]
    assert [item.name for item in points] == list(MODULE_SPECS[0]["knowledge_points"])
    assert migrated_quiz.answer == MODULE_SPECS[0]["knowledge_points"][0]
    assert "Semantic Kernel" in migrated_quiz.content
    assert db.query(TrainingProgram).count() == 1
    assert db.query(TrainingModule).count() == 3
    assert db.query(KnowledgePoint).count() == 12
    assert db.query(Quiz).count() == 12


def test_active_product_surfaces_share_the_frozen_domain() -> None:
    active_files = [
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "AGENTS.md",
        REPOSITORY_ROOT / "docs" / "competition-requirements.md",
        REPOSITORY_ROOT / "docs" / "architecture.md",
        REPOSITORY_ROOT / "apps" / "api" / "index.html",
        REPOSITORY_ROOT / "apps" / "api" / "app.py",
    ]
    stale_labels = [
        "企业级 RAG 应用开发与质量治理",
        "企业知识库构建",
        "检索、重排与引用生成",
        "RAG 评测与幻觉治理",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_files)

    assert "Semantic Kernel" in combined
    assert all(spec["name"] in combined for spec in MODULE_SPECS)
    assert all(label not in combined for label in stale_labels)
