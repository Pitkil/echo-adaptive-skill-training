from __future__ import annotations

from app import app, create_access_token, ensure_catalog, get_db
from database import Base, Organization, User, UserRole
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_only_admin_can_manage_roles_and_last_admin_is_protected() -> None:
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
    admin = User(
        organization_id=organization.id,
        username="role-admin",
        hashed_password="not-used",
        role=UserRole.SYSTEM_ADMIN.value,
    )
    learner = User(
        organization_id=organization.id,
        username="role-learner",
        hashed_password="not-used",
        role=UserRole.LEARNER.value,
    )
    db.add_all([admin, learner])
    db.commit()
    db.refresh(admin)
    db.refresh(learner)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    learner_headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
    admin_headers = {"Authorization": f"Bearer {create_access_token(admin)}"}

    forbidden = client.get("/v1/admin/users", headers=learner_headers)
    assert forbidden.status_code == 403

    listing = client.get("/v1/admin/users", headers=admin_headers)
    assert listing.status_code == 200
    assert {item["username"] for item in listing.json()["items"]} == {
        admin.username,
        learner.username,
    }

    promoted = client.patch(
        f"/v1/admin/users/{learner.id}/role",
        json={"role": UserRole.MENTOR.value},
        headers=admin_headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == UserRole.MENTOR.value
    db.refresh(learner)
    assert learner.role == UserRole.MENTOR.value

    last_admin = client.patch(
        f"/v1/admin/users/{admin.id}/role",
        json={"role": UserRole.MENTOR.value},
        headers=admin_headers,
    )
    assert last_admin.status_code == 409

    app.dependency_overrides.clear()
    db.close()
