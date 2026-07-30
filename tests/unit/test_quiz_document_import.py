from __future__ import annotations

import app as app_module
from app import app, create_access_token, ensure_catalog, get_db
from database import Base, Organization, Quiz, TrainingProgram, User, UserRole
from fastapi.testclient import TestClient
from Quiz.import_from_document import extract_quiz_preview, validate_quiz_item
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_structured_text_quiz_is_extracted_for_preview(tmp_path) -> None:
    source = tmp_path / "semantic-kernel-pretest.md"
    source.write_text(
        """
题目：Kernel 在 Semantic Kernel 应用中的主要作用是什么？
答案：集中管理模型服务与插件。
题型：Open
用途：前测
难度：基础
评分方法：说明模型服务和插件均由 Kernel 组织得 2 分，只说明一项得 1 分。
资料名称：Understanding the kernel
官方链接：https://learn.microsoft.com/semantic-kernel/concepts/kernel
出处章节：The kernel is at the center
是否更新MIRT：是
""".strip(),
        encoding="utf-8",
    )

    text_length, items = extract_quiz_preview(source)

    assert text_length > 0
    assert len(items) == 1
    assert items[0]["purpose"] == "pretest"
    assert items[0]["difficulty"] == "foundation"
    assert items[0]["counts_for_mirt"] is True
    assert items[0]["valid"] is True
    assert items[0]["issues"] == []


def test_preview_validation_requires_answer_scoring_and_source() -> None:
    issues = validate_quiz_item(
        {
            "content": "题目存在",
            "answer": "",
            "scoring_method": "",
            "source_title": "",
            "source_url": "",
            "source_section": "",
        }
    )

    assert issues == [
        "缺少答案",
        "缺少评分方法",
        "缺少资料名称",
        "缺少官方链接",
        "缺少出处章节",
    ]


def test_preview_then_confirm_import_persists_quiz_metadata(tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    ensure_catalog(db)
    organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
    mentor = User(
        organization_id=organization.id,
        username="mentor-import-test",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    db.add(mentor)
    db.commit()
    db.refresh(mentor)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app_module.UPLOAD_DIR = tmp_path
    token = create_access_token(mentor)
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    program = db.query(TrainingProgram).filter_by(organization_id=organization.id).one()
    module = app_module.list_modules(program.id, db, mentor)[0]
    point = app_module.list_knowledge_points(module["id"], db, mentor)[0]
    quiz_text = """
题目：插件函数为什么需要清晰描述输入和输出？
答案：帮助模型正确选择函数并提供有效参数。
用途：阶段测试
难度：标准
评分方法：说明函数选择和参数生成各得 1 分。
资料名称：Plugins in Semantic Kernel
官方链接：https://learn.microsoft.com/semantic-kernel/concepts/plugins/
出处章节：What is a Plugin
是否更新MIRT：否
""".strip()

    preview_response = client.post(
        "/v1/quiz-imports/preview",
        data={"module_id": module["id"], "knowledge_point_id": point["id"]},
        files={"document": ("quiz.md", quiz_text.encode("utf-8"), "text/markdown")},
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert db.query(Quiz).filter_by(content=preview["items"][0]["content"]).count() == 0

    confirm_response = client.post(
        f"/v1/quiz-imports/{preview['preview_id']}/confirm",
        json={"items": preview["items"]},
        headers=headers,
    )
    assert confirm_response.status_code == 200
    imported = db.query(Quiz).filter_by(content=preview["items"][0]["content"]).one()
    assert imported.purpose == "stage_test"
    assert imported.difficulty == "standard"
    assert imported.source_title == "Plugins in Semantic Kernel"
    assert imported.counts_for_mirt is False

    app.dependency_overrides.clear()
    db.close()
