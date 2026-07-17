"""Isolated asynchronous API test application."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.main import create_app
from transcriptforge_api.models import Base
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.local import LocalStorage
from transcriptforge_api.workers.dispatch import (
    get_analysis_dispatcher,
    get_preparation_dispatcher,
    get_validation_dispatcher,
)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "objects")


@pytest.fixture
def dispatched_run_ids() -> list[str]:
    return []


@pytest.fixture
def dispatched_preparation_ids() -> list[str]:
    return []


@pytest.fixture
def dispatched_analysis_ids() -> list[str]:
    return []


@pytest_asyncio.fixture
async def session_factory(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def test_app(
    tmp_path: Path,
    storage: LocalStorage,
    dispatched_run_ids: list[str],
    dispatched_preparation_ids: list[str],
    dispatched_analysis_ids: list[str],
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[FastAPI]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    def override_storage() -> LocalStorage:
        return storage

    def override_dispatcher():  # type: ignore[no-untyped-def]
        return dispatched_run_ids.append

    def override_preparation_dispatcher():  # type: ignore[no-untyped-def]
        return dispatched_preparation_ids.append

    def override_analysis_dispatcher():  # type: ignore[no-untyped-def]
        return dispatched_analysis_ids.append

    application = create_app()
    test_settings = Settings(
        environment="test",
        run_work_root=tmp_path / "runs",
        reference_cache_root=tmp_path / "references",
        local_storage_root=tmp_path / "objects",
    )
    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.dependency_overrides[get_storage_backend] = override_storage
    application.dependency_overrides[get_validation_dispatcher] = override_dispatcher
    application.dependency_overrides[get_preparation_dispatcher] = override_preparation_dispatcher
    application.dependency_overrides[get_analysis_dispatcher] = override_analysis_dispatcher
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as http_client:
        yield http_client
