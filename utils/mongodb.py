"""MongoDB connection abstraction layer.

Provides a thin, swappable interface over ``pymongo`` so the rest of the
codebase never imports ``pymongo`` directly.  If you ever need to switch
to another document store (DynamoDB, CouchDB, Firestore, …), only this
module and ``agents/services/document_store.py`` need to change.

Usage::

    from utils.mongodb import get_mongo_db, get_collection

    db = get_mongo_db()
    col = get_collection("scraped_documents")
    col.insert_one({"url": "https://example.com", ...})

Connection is lazy — the first call to ``get_mongo_client()`` creates
the singleton ``MongoClient``.  Subsequent calls reuse it.
"""

from __future__ import annotations

import hashlib
from typing import Any

from Logging import get_logger

logger = get_logger("utils.mongodb")

# Lazy-loaded singleton
_client: Any | None = None


def _mongo_uri() -> str:
    """Resolve MongoDB connection URI from env."""
    from env import config

    uri = config.get("MONGODB_URI")
    if uri:
        return uri
    host = config.get("MONGODB_HOST") or "localhost"
    port = config.get("MONGODB_PORT") or "27017"
    return f"mongodb://{host}:{port}"


def _mongo_db_name() -> str:
    from env import config

    return config.get("MONGODB_DATABASE") or "sentiment_analyzer"


def get_mongo_client() -> Any:
    """Return a lazily-created ``MongoClient`` singleton."""
    global _client
    if _client is not None:
        return _client

    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise ImportError(
            "pymongo is required for MongoDB support. Install it with: uv add pymongo"
        ) from exc

    uri = _mongo_uri()
    _client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=30000,
        maxPoolSize=20,
    )
    logger.info(
        "MongoDB client created  uri=%s  db=%s",
        uri.split("@")[-1] if "@" in uri else uri,
        _mongo_db_name(),
        action="mongo_connect",
    )
    return _client


def get_mongo_db(db_name: str | None = None) -> Any:
    """Return the default (or named) MongoDB database object."""
    client = get_mongo_client()
    return client[db_name or _mongo_db_name()]


def get_mongo_database(
    *, app_name: str | None = None, db_name: str | None = None
) -> Any:
    """Return a MongoDB database handle (alias for ``get_mongo_db``).

    The ``app_name`` parameter is accepted for logging context but does not
    change connection behaviour.
    """
    return get_mongo_db(db_name)


def get_collection(name: str, *, db_name: str | None = None) -> Any:
    """Return a MongoDB collection handle."""
    return get_mongo_db(db_name)[name]


def mongo_is_available() -> bool:
    """Quick connectivity check (non-blocking, short timeout)."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        return True
    except Exception:
        return False


def close_mongo() -> None:
    """Close the singleton client (for clean shutdown)."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
        logger.info("MongoDB client closed", action="mongo_close")


def content_hash(text: str) -> str:
    """SHA-256 digest of text content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_indexes(collection_name: str = "scraped_documents") -> None:
    """Create recommended indexes on the documents collection.

    Safe to call multiple times — MongoDB ignores duplicate index creation.
    """
    from pymongo import ASCENDING, DESCENDING, IndexModel

    col = get_collection(collection_name)
    indexes = [
        IndexModel([("doc_id", ASCENDING)], unique=True, name="idx_doc_id"),
        IndexModel(
            [("normalized_url", ASCENDING)], unique=True, name="idx_normalized_url"
        ),
        IndexModel([("content_hash", ASCENDING)], name="idx_content_hash"),
        IndexModel([("topic_refs", ASCENDING)], name="idx_topic_refs"),
        IndexModel(
            [("platform", ASCENDING), ("scrape_status", ASCENDING)],
            name="idx_platform_status",
        ),
        IndexModel(
            [("scrape_status", ASCENDING), ("last_scraped_at", DESCENDING)],
            name="idx_status_time",
        ),
        IndexModel([("domain", ASCENDING)], name="idx_domain"),
    ]
    col.create_indexes(indexes)
    logger.info(
        "Ensured indexes on %s  count=%d",
        collection_name,
        len(indexes),
        action="mongo_indexes",
    )


__all__ = [
    "close_mongo",
    "content_hash",
    "ensure_indexes",
    "get_collection",
    "get_mongo_client",
    "get_mongo_database",
    "get_mongo_db",
    "mongo_is_available",
]
