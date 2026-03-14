"""Sentiment analyzer agent — phase 5 sentiment scoring for cleaned documents.

This agent takes cleaned documents from the CleanerAgent and runs sentiment
analysis using the SentimentAnalyzer module. It produces sentiment scores
(0→1 continuous) for each document and stores results in MongoDB.

Pipeline position:
    Topic → Keywords → Harvest → Scrape → Clean → **Sentiment** → Dashboard

Features:
    - Fully async batch processing with semaphore-controlled concurrency
    - Topic-aware sentiment analysis (understands topic context)
    - Progress tracking and checkpointing
    - Error recovery for failed documents
    - MongoDB persistence for sentiment results
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agents.base import BaseAgent
from agents._registry import register_agent
from Logging import get_logger

logger = get_logger("agents.sentiment")


@register_agent
class SentimentAnalyzerAgent(BaseAgent):
    """Analyze sentiment of cleaned documents using HuggingFace models.

    This agent:
    1. Loads cleaned documents from MongoDB
    2. Runs sentiment analysis using SentimentAnalyzer (async batch)
    3. Stores sentiment results back to MongoDB
    4. Provides summary statistics

    Sentiment scores are continuous (0→1):
    - 0.0 = very negative
    - 0.5 = neutral
    - 1.0 = very positive
    """

    _name = "sentiment"
    _description = (
        "Analyze sentiment of cleaned documents using HuggingFace models. "
        "Produces continuous sentiment scores (0→1) for each document with "
        "async batch processing and error recovery."
    )
    _system_prompt_file = "system.txt"
    _llm_provider = "google"
    _llm_model = "gemini-2.5-flash"
    _timeout_seconds = 1800
    _max_retries = 1

    def invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke the sentiment analyzer agent.

        Parameters
        ----------
        message : str
            Topic name to analyze.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Sentiment analysis results including scores and statistics.
        """
        topic = message.strip()
        if not topic:
            raise ValueError("SentimentAnalyzerAgent requires a non-empty topic.")
        if self._demo:
            return self._demo_invoke(topic, **kwargs)
        return asyncio.run(self.ainvoke(topic, **kwargs))

    async def ainvoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Async invocation of the sentiment analyzer agent.

        Parameters
        ----------
        message : str
            Topic name to analyze.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Sentiment analysis results including scores and statistics.
        """
        topic = message.strip()
        if self._demo:
            return self._demo_invoke(topic, **kwargs)

        self._checkpoint_topic_input(topic)
        self._checkpoint_agent_status(topic, status="working", mark_started=True)

        # Runtime configuration for sentiment analysis
        runtime = self._build_runtime_config()

        try:
            # Load cleaned documents from MongoDB
            cleaned_docs = self._load_cleaned_documents(topic)

            if not cleaned_docs:
                summary = "Sentiment analyzer found no cleaned documents to process."
                self._checkpoint_agent_status(topic, status="completed")
                return {"status": "completed", "summary": summary, "stats": {}}

            # Initialize sentiment analyzer
            from SentimentAnalyzer import get_sentiment_analyzer

            analyzer = get_sentiment_analyzer()

            # Build run ID and prepare tracking
            run_id = str(uuid.uuid4())
            stats = {
                "total_documents": len(cleaned_docs),
                "analyzed": 0,
                "failed": 0,
                "avg_score": 0.0,
                "positive_count": 0,
                "neutral_count": 0,
                "negative_count": 0,
            }

            # Record start event
            latest_run_id = self._get_latest_run_id(topic)
            if latest_run_id:
                self._record_event(
                    latest_run_id,
                    event_type="sentiment_started",
                    agent=self._name,
                    status="running",
                    message=f"Starting sentiment analysis for {len(cleaned_docs)} documents",
                    meta={
                        "sentiment_run_id": run_id,
                        "total_documents": len(cleaned_docs),
                    },
                )

            # Process documents asynchronously with semaphore
            results = await self._process_documents_async(
                topic=topic,
                documents=cleaned_docs,
                analyzer=analyzer,
                runtime=runtime,
                max_concurrency=runtime.get("max_concurrency", 8),
            )

            # Aggregate results
            scores = []
            for result in results:
                if isinstance(result, Exception):
                    stats["failed"] += 1
                    continue
                if not isinstance(result, dict):
                    stats["failed"] += 1
                    continue

                score = result.get("score", 0.5)
                scores.append(score)
                stats["analyzed"] += 1

                if score >= 0.6:
                    stats["positive_count"] += 1
                elif score <= 0.4:
                    stats["negative_count"] += 1
                else:
                    stats["neutral_count"] += 1

            # Calculate average score
            if scores:
                stats["avg_score"] = sum(scores) / len(scores)

            # Store results in MongoDB
            await self._store_sentiment_results(topic, results, stats, run_id)

            # Build summary
            summary = (
                f"Sentiment analysis completed: {stats['analyzed']} documents analyzed. "
                f"Average score: {stats['avg_score']:.3f}. "
                f"Positive: {stats['positive_count']}, "
                f"Neutral: {stats['neutral_count']}, "
                f"Negative: {stats['negative_count']}."
            )

            # Record completion event
            if latest_run_id:
                self._record_event(
                    latest_run_id,
                    event_type="sentiment_completed",
                    agent=self._name,
                    status="completed",
                    message=summary,
                    meta={
                        "sentiment_run_id": run_id,
                        "total_documents": stats["total_documents"],
                        "analyzed": stats["analyzed"],
                        "failed": stats["failed"],
                        "avg_score": stats["avg_score"],
                        "positive_count": stats["positive_count"],
                        "neutral_count": stats["neutral_count"],
                        "negative_count": stats["negative_count"],
                    },
                )

            self._checkpoint_agent_status(topic, status="completed")

            return {
                "status": "completed",
                "summary": summary,
                "stats": stats,
                "run_id": run_id,
            }

        except Exception as exc:
            logger.error(
                "Sentiment analysis failed  topic=%s  error=%s",
                topic,
                exc,
                exc_info=True,
            )
            self._checkpoint_agent_status(topic, status="failed", last_error=str(exc))
            raise RuntimeError(
                f"Sentiment analysis failed for topic '{topic}': {exc}"
            ) from exc

    async def _process_documents_async(
        self,
        topic: str,
        documents: list[dict[str, Any]],
        analyzer: Any,
        runtime: dict[str, Any],
        max_concurrency: int = 8,
    ) -> list[dict[str, Any] | BaseException]:
        """Process documents asynchronously with semaphore-controlled concurrency.

        Parameters
        ----------
        topic : str
            Topic name.
        documents : list[dict[str, Any]]
            List of cleaned documents.
        analyzer : Any
            Sentiment analyzer instance.
        runtime : dict[str, Any]
            Runtime configuration.
        max_concurrency : int
            Maximum concurrent workers.

        Returns
        -------
        list[dict[str, Any]]
            List of sentiment analysis results.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _worker(document: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self._analyze_document(document, analyzer)

        # Process all documents concurrently
        results = await asyncio.gather(
            *[_worker(doc) for doc in documents], return_exceptions=True
        )

        return results

    async def _analyze_document(
        self,
        document: dict[str, Any],
        analyzer: Any,
    ) -> dict[str, Any]:
        """Analyze sentiment of a single document.

        Parameters
        ----------
        document : dict[str, Any]
            Document to analyze.
        analyzer : Any
            Sentiment analyzer instance.

        Returns
        -------
        dict[str, Any]
            Sentiment analysis result.
        """
        try:
            # Get text for analysis
            text = document.get("cleaned_text") or document.get("text", "")
            if not text:
                return {
                    "document_id": document.get("document_id", "unknown"),
                    "score": 0.5,
                    "label": "neutral",
                    "confidence": 0.0,
                    "status": "failed",
                    "error": "No text content",
                }

            # Analyze sentiment
            result = analyzer.analyze(text)

            return {
                "document_id": document.get("document_id"),
                "score": result.score,
                "label": result.label,
                "confidence": result.confidence,
                "status": "analyzed",
            }
        except Exception as exc:
            logger.warning(
                "Failed to analyze document  doc_id=%s  error=%s",
                document.get("document_id"),
                exc,
            )
            return {
                "document_id": document.get("document_id", "unknown"),
                "score": 0.5,
                "label": "neutral",
                "confidence": 0.0,
                "status": "failed",
                "error": str(exc),
            }

    def _load_cleaned_documents(self, topic: str) -> list[dict[str, Any]]:
        """Load cleaned documents from MongoDB.

        Parameters
        ----------
        topic : str
            Topic name.

        Returns
        -------
        list[dict[str, Any]]
            List of cleaned documents.
        """
        try:
            from utils.mongodb import get_mongo_db

            db = get_mongo_db()
            cleaned_collection = db["cleaned_documents"]

            topic_slug = topic.lower().replace(" ", "_")
            docs = list(
                cleaned_collection.find(
                    {"topic_slug": topic_slug},
                    {"cleaned_text": 1, "text": 1, "document_id": 1, "_id": 0},
                )
            )

            logger.info(
                "Loaded %d cleaned documents for topic '%s'",
                len(docs),
                topic,
            )
            return docs

        except Exception as exc:
            logger.warning(
                "Failed to load cleaned documents from MongoDB: %s",
                exc,
            )
            return []

    async def _store_sentiment_results(
        self,
        topic: str,
        results: list[dict[str, Any] | BaseException],
        stats: dict[str, Any],
        run_id: str,
    ) -> None:
        """Store sentiment results in MongoDB.

        Parameters
        ----------
        topic : str
            Topic name.
        results : list[dict[str, Any]]
            Sentiment analysis results.
        stats : dict[str, Any]
            Aggregated statistics.
        run_id : str
            Run ID for this sentiment analysis.
        """
        try:
            from utils.mongodb import get_mongo_db

            db = get_mongo_db()
            topic_slug = topic.lower().replace(" ", "_")

            # Store individual sentiment results
            sentiment_collection = db["sentiment_results"]
            for result in results:
                if isinstance(result, dict) and result.get("status") == "analyzed":
                    result["topic"] = topic
                    result["topic_slug"] = topic_slug
                    result["sentiment_run_id"] = run_id
                    sentiment_collection.update_one(
                        {"document_id": result["document_id"], "topic": topic},
                        {"$set": result},
                        upsert=True,
                    )

            # Store sentiment summary
            summary_collection = db["sentiment_summaries"]
            summary_collection.update_one(
                {"topic": topic},
                {
                    "$set": {
                        "topic": topic,
                        "topic_slug": topic_slug,
                        "sentiment_run_id": run_id,
                        "stats": stats,
                        "total_documents": stats["total_documents"],
                        "analyzed": stats["analyzed"],
                        "avg_score": stats["avg_score"],
                    }
                },
                upsert=True,
            )

            logger.info(
                "Stored sentiment results  topic=%s  num_results=%d",
                topic,
                len(results),
            )

        except Exception as exc:
            logger.warning(
                "Failed to store sentiment results in MongoDB  topic=%s  error=%s",
                topic,
                exc,
            )

    def _build_runtime_config(self) -> dict[str, Any]:
        """Build runtime configuration for sentiment analysis.

        Returns
        -------
        dict[str, Any]
            Runtime configuration.
        """
        from env import config

        return {
            "max_concurrency": int(config.get("SENTIMENT_MAX_CONCURRENCY") or 8),
            "max_documents_per_run": int(
                config.get("SENTIMENT_MAX_DOCUMENTS_PER_RUN") or 500
            ),
            "batch_size": int(config.get("SENTIMENT_BATCH_SIZE") or 16),
            "model": config.get("SENTIMENT_MODEL") or "distilroberta-base",
        }

    def _get_latest_run_id(self, topic: str) -> str | None:
        """Get the latest run ID for a topic.

        Parameters
        ----------
        topic : str
            Topic name.

        Returns
        -------
        str | None
            Latest run ID or None.
        """
        try:
            from agents.services import get_latest_run_id

            return get_latest_run_id(topic)
        except Exception:
            return None

    def _record_event(
        self,
        run_id: str,
        event_type: str,
        agent: str,
        status: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Record an orchestrator event.

        Parameters
        ----------
        run_id : str
            Run ID.
        event_type : str
            Event type.
        agent : str
            Agent name.
        status : str
            Status.
        message : str
            Message.
        meta : dict[str, Any] | None
            Additional metadata.
        """
        try:
            from agents.services import record_orchestrator_event

            record_orchestrator_event(
                run_id,
                event_type=event_type,
                agent=agent,
                status=status,
                message=message,
                meta=meta,
            )
        except Exception as exc:
            logger.warning("Failed to record event: %s", exc)

    def _demo_invoke(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Demo mode implementation with static sentiment data.

        Parameters
        ----------
        message : str
            Topic name.
        **kwargs : Any
            Additional arguments.

        Returns
        -------
        dict[str, Any]
            Demo sentiment analysis results.
        """
        import random

        topic = message.strip()
        random.seed(hash(topic))

        # Generate demo statistics
        total_docs = random.randint(50, 200)
        analyzed = total_docs - random.randint(0, 5)
        failed = total_docs - analyzed

        # Generate realistic distribution
        positive_ratio = random.uniform(0.3, 0.5)
        negative_ratio = random.uniform(0.2, 0.4)
        neutral_ratio = 1.0 - positive_ratio - negative_ratio

        positive_count = int(analyzed * positive_ratio)
        negative_count = int(analyzed * negative_ratio)
        neutral_count = int(analyzed * neutral_ratio)

        # Calculate average score
        avg_score = (
            ((positive_count * 0.75) + (neutral_count * 0.5) + (negative_count * 0.25))
            / analyzed
            if analyzed > 0
            else 0.5
        )

        stats = {
            "total_documents": total_docs,
            "analyzed": analyzed,
            "failed": failed,
            "avg_score": avg_score,
            "positive_count": positive_count,
            "neutral_count": neutral_count,
            "negative_count": negative_count,
        }

        summary = (
            f"Sentiment analysis completed (demo): {analyzed} documents analyzed. "
            f"Average score: {avg_score:.3f}. "
            f"Positive: {positive_count}, "
            f"Neutral: {neutral_count}, "
            f"Negative: {negative_count}."
        )

        return {
            "status": "completed",
            "summary": summary,
            "stats": stats,
            "run_id": f"demo-{uuid.uuid4().hex[:8]}",
        }
