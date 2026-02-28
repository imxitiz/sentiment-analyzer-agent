Task: Build the Sovereign Sentiment Agent (End-to-End Pipeline)

The repository is currently empty. I need you to build a production-ready, highly modular, real-time Sentiment Analysis platform from scratch. Do not stop until the entire pipeline is working, tested, and a user can enter a topic and watch the dashboard update in real-time.

Please execute the following phases in order, adhering strictly to the SOLID principles and abstraction requirements in your system prompt:

Phase 1: Project Initialization & Infrastructure

    Initialize a project with TypeScript.
    Set up Convex DB for the reactive backend and install UI libraries (Tailwind, Lucide icons, Recharts for 15/20+ dashboard widgets).
    Set up a local SQLite database to act as the raw URL ingestion queue.
    Implement deeply contextual logging (tracking User, Topic Session, Action, and Reason).

Phase 2: The Harvester Agent (Link Discovery)

    Implement a LangGraph.js orchestrator.
    Build the "Searcher/Harvester" module. When a user provides a topic (e.g., "Candidate X"), this module uses web search/MCP tools to find relevant social media and forum URLs.
    It must asynchronously write these URLs to the SQLite database with a state of status: 'PENDING'.

Phase 3: The Async Extraction Workers

    Build the scraper module in TypeScript.
    It must query the SQLite DB for batches of 10 PENDING links, fetch the raw text content, and update the SQLite state to COMPLETED.
    Design this worker to run asynchronously in the background.

Phase 4: Analytics & Real-Time Sync

    Pass the raw scraped text to an LLM/Sentiment module to perform Dimensional Sentiment Analysis (extracting Valence, Arousal, and Key Topics).
    Write the final structured data and metadata (timestamps, inferred demographics) to Convex DB.

Phase 5: The "No-Slop" Premium UX Dashboard

    Build a Next.js UI where a user can create a "New Topic Session."
    Real-Time Transparency: As the backend processes, the UI must subscribe to Convex and display:
        What the agent is currently doing (e.g., "Discovering links for 'Solar Policy'").
        A live feed showing 5-second cycling snippets of raw text currently being scraped.
    Analytics Dashboard: Implement beautiful, dynamic charts (Sentiment distribution bell curves, time-series volume, topic word clouds).
    Chat Interface: Add a sidebar chat where the user can talk to the data (RAG architecture based on the processed topic).

Make sure all layers are decoupled (use dependency injection!). Validate the frontend using your Playwright tools. Finish the task only when the full pipeline can accept a topic, scrape data, analyze it, and stream it to the dashboard.

what will happen the workflow from the user prespective is, user will type the topic on the AI chat alike interface, and it will take that, and try to refine it, if further info is needed from the user ask the user within first 1/2 minutes and refine the topic, generate bunch of keywords, update it's own keywords, save those keywords on db or somewhere so that we can track off those stuffs.. add new keywords after getting some more info by searching about that topic on internet, hashtags, and all on all major social media, now use those keywords, hashtags, and get the links, links will be now collected on the fastest DB sqlite if possible also make it concurrent so that 2/3 agents can write on the DB at a same time if needed it just doesn't get locked out.. after orchastator of this searching agent think it's enough or after some time of timeout it will stop and give task to do the actual web scraping from all of those links.. start to do do web scraping and storing on the actual real db like mongodb nosql db, and after all scraping task is complete start the work of data clearning.. and putting all those data to the vector db and all so that later if needed we should be able to do chat with that data, like data shoud be with various a really good bunch of meta data, from where from whome what time, when collected, when posted everything as much as possible meta data shoud be saved on dbs so taht taht will be used on chat and also on filtering from which sites etc. etc.. we should collect as much possible meta data as we can up to its limit, now cleaning is done, the work of analyzing should start and rating should be done to each individual data, what's the sentimental of this post, and after the work of analysis is complete, we've to starting showing things on dashboard of that topic or task, and if user want they can do refresh after certain day if they wanna refresh the things and do th rescraping again, and that will be treated as the 2nd verison, shouldn't replace the preivous things at all!!

1. Executive Summary & Core Philosophy

This document serves as the absolute source of truth for developing the "Sovereign Sentiment Agent," a fully autonomous, end-to-end sentiment analysis research lab. The system processes large volumes of user-generated content from social media to assess public inclination toward specific topics or candidates.

As the AI coding assistant executing this project, you must build this strictly following a Multi-Agent Orchestration approach. You are not writing a linear script; you are building an agentic mesh with clear boundaries, interfaces, and asynchronous hand-offs.

Engineering Mandates:

    Modularity & SOLID Principles: The system must be highly decoupled. Use dependency injection and abstract interfaces for databases, scrapers, and LLMs so that any component can be swapped without affecting the rest of the system.
    TypeScript Ecosystem: The entire pipeline (including web scraping and orchestration) must be written in TypeScript, utilizing modern libraries.
    Non-Destructive Versioning: Data is never overwritten. If a user "refreshes" a topic after a few days, it must be saved as a new version (e.g., Version 2), allowing historical comparison against Version 1.

2. The Step-by-Step Agentic Workflow

The pipeline must execute in the exact chronological order defined below.
Phase 1: Topic Refinement & Context Expansion (The Chat Interface)

    User Interaction: The workflow begins in a chat-like React UI where the user inputs a research topic.
    Refinement Loop: The Orchestrator agent evaluates the topic. If the request is too broad, it must prompt the user with clarifying questions within the first 1-2 minutes.
    Context Expansion: Once clarified, the agent searches the internet (via API or MCP tools) to find related keywords, key players, and trending hashtags.
    Tracking: These expanded keywords are immediately saved to the database to track exactly what parameters are driving the data collection.

Phase 2: The Harvester (Concurrent Link Discovery)

    Role: The system utilizes a "Harvester-Processor" model to separate link collection from heavy data scraping. Harvester agents use the expanded keywords to find relevant post URLs across platforms.
    Concurrent SQLite Queue: Discovered links must be written to a local SQLite database acting as a high-speed queue. This database must be configured to handle concurrent writes safely so that multiple Harvester agents can push URLs simultaneously without locking the database.
    Timeout/Threshold: The Orchestrator monitors the Harvester. Once a sufficient number of unique links are collected, or a specific timeout is reached, the Orchestrator stops the harvesting phase and triggers Phase 3.

Phase 3: The Scraper (Deep Extraction)

    Role: Extraction workers pull batches of pending URLs from the SQLite queue and scrape the actual page content.
    Bronze Layer Storage: The raw, unstructured text scraped from the social media sites must be stored in a NoSQL database (e.g., MongoDB).

Phase 4: The Processor (Cleaning & Metadata Embedding)

    Data Cleaning: A Processor agent takes the raw NoSQL data and applies filtering to remove spam, ads, and noisy boilerplate.
    Maximized Metadata: The agent must extract and attach as much metadata as possible (e.g., author, platform, timestamp of post, timestamp of collection, inferred geolocation, original search keyword).
    Vector Database: The cleaned text is converted into embeddings and stored in a Vector DB (e.g., Pinecone, FAISS, Weaviate) alongside its extensive metadata. This is critical to enable future filtering and RAG-based chat interactions.

Phase 5: The Analyst (Sentiment Scoring)

    Scoring Logic: The cleaned data is passed to a sentiment model.
    Granular Rating: Each individual post must receive its own sentiment rating. The system should aim for Dimensional Aspect-Based Sentiment Analysis (mapping Valence and Arousal) to understand the intensity of the emotion, not just positive/negative/neutral labels.

Phase 6: The Reactive Dashboard & UI

    Real-Time Presentation: As the analysis completes, the structured results must be pushed to a reactive database (e.g., Convex) that automatically updates the Next.js frontend without requiring a page refresh.
    Widgets: The dashboard must generate comprehensive visual representations, including time-series charts, sentiment distribution bell curves, and platform divergence comparisons.
    Interactive Chat: Because the data is stored in a Vector DB with rich metadata, the UI must include a chat interface allowing the user to query the collected data (e.g., "Summarize the negative feedback from Reddit users on Tuesday").

3. Implementation Guidelines for the AI Agent

    Do Not Write "AI Slop": The user interface must be clean, premium, and functional. It must show the real-time status of the background workers (e.g., "Harvesting keywords...", "Scraping 45/100 links...").
    Centralized Configuration: Follow the DRY (Don't Repeat Yourself) principle. Constants, API endpoints, and configuration variables must be centralized so they only need to be updated in one place.
    Logging as a Story: Implement structured logging that explains what happened, why it happened, and which user/topic triggered it. Do not just log basic error outputs.
    Autonomous Execution: Read this document, initialize the architecture, and execute the phases sequentially. Use MCP tools to test your work. Do not finish the task until a user can type a topic into the chat interface and watch the pipeline flow autonomously through to the final dashboard visualizations.
