# Designing an AI-Powered Multi-Agent Sentiment Analysis System for Social Media

**Project Brief:** Build an autonomous pipeline that **scrapes social
media and web content**, performs sentiment analysis, and presents
insights via a real-time dashboard. The system should handle large
volumes of user-generated text, categorize opinions
(positive/negative/neutral), track trends over time, and answer
topic-based queries (e.g. "What is public sentiment about Candidate
X?"). The workflow will be **modular**, **agent-driven**, and use
cutting-edge AI tools (LLMs, vector databases, reactive frontends) for
maximum flexibility and scalability. Our solution will also be robust to
future changes (new platforms, new AI models, etc.), and will be
production-ready by project end.

This guide walks through **every phase** of the project -- from initial
planning to final presentation -- explaining **what to do, why, and
how**. We cover data sourcing, collection, storage, preprocessing,
modeling, orchestration, and visualization. We also discuss coding
practices with AI assistants, development workflows, and future-proof
design. The goal is that after reading this, you'll have a **clear
roadmap** and deep understanding to confidently tackle the project.

------------------------------------------------------------------------

## 1. Understanding Objectives and Scope

1. **Clarify the goals and use cases.** This project is essentially a
    *"social listening"* or *"opinion mining"* system. Its **primary
    purpose** is to gauge public sentiment on topics (e.g., election
    candidates, products, events) via social media and online
    discussions. One key use case is **election analysis**: using social
    chatter to predict voter inclinations. Other use cases include brand
    monitoring and market research. Being clear on the objectives helps
    guide every decision. Early on, write a **specification document**
    describing the main deliverables (e.g., "a dashboard showing
    sentiment trends; a chatbot answering sentiment queries"). Use an
    LLM (e.g., GPT-4o, Claude) interactively to flesh out these
    requirements. Prompt the AI to **generate questions and iterative
    clarifications** until the spec is
    comprehensive[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code).

2. **Identify stakeholders and constraints.** Who will use the system?
    (e.g., data analysts, campaign managers). Clarify performance needs:
    near real-time updates? Historical data only? Assess budget and
    resources: will we use paid APIs or only free scraping? The project
    description explicitly asks to **evaluate paid API needs and rate
    limits** before starting. So investigate if the chosen platforms
    require API keys (e.g., Twitter's API) or if we must rely on
    scraping (and comply with terms). Early on, review legal/ethical
    guidelines: only scrape *public* data and avoid PII
    violations[\[2\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Thus%20scraping%2C%20developers%20must%20consider,Scraping%20should%20ideally).
    Summarize these in a "Project Constraints" section.

3. **Define success metrics.** The project requires an evaluation of
    model accuracy (precision, recall, F1) and a qualitative check of
    insights. Decide on ground truth or benchmark data (e.g., public
    tweets with labels) for evaluating sentiment accuracy. Plan how to
    measure system reliability (uptime, data freshness).

4. **Plan deliverables and timeline.** Break down the project into
    milestones (data collection pipeline, model development, dashboard
    prototype, agent integration, etc.). Use AI-assisted planning: ask
    GPT/Claude to draft a **project plan** with tasks and timelines.
    Revise until it makes sense. Treat this as your "roadmap" to keep
    the project on
    track[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code)[\[3\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Scope%20management%20is%20everything%20%E2%80%94,the%20whole%20codebase%20at%20once).

**Tip:** Don't jump into coding. First produce a detailed **design
document** or outline (possibly with AI help) that covers architecture,
components, and responsibilities. This upfront effort saves debugging
later[\[4\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Next%2C%20I%20feed%20the%20spec,the%20subsequent%20coding%20much%20smoother)[\[5\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Break%20work%20into%20small%2C%20iterative,chunks).

------------------------------------------------------------------------

## 2. Data Sources and Platforms

**Social Media Platforms:** We will mine **social networks and web
forums** where user opinions appear. Candidates include **Twitter/X,
Reddit, Facebook, Instagram, TikTok, and public comment sections** (news
sites, blogs, forums). Also consider **news comments** or discussion
boards. Choose platforms based on *relevance* and *data accessibility*.
For election analysis, Twitter/X and Facebook groups often have
political chatter; for broader market sentiment, review sites (Yelp,
Amazon reviews) can supplement.

- **APIs vs. Scraping:** Where available, use official APIs (e.g.,
    Twitter API, Reddit API) because they provide structured, reliable
    access. APIs often require authentication and have rate limits, so
    check if they fit our data volume needs. If API access is *limited
    or costly*, fall back to web scraping, as long as it's *allowed by
    terms*. As **Statology** notes, APIs are structured but have
    constraints, while web scraping is "more complex and error-prone"
    and must obey ethical/legal
    rules[\[6\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=API%20endpoints%20provide%20the%20most,rate%20limits%20and%20data%20constraints).
    Plan to combine both: use APIs for heavy data (subject to quotas)
    and scraping for publicly accessible content not covered by APIs.

- **Ethical & Legal Compliance:** Always scrape *public* data, and
    honor `robots.txt` and platform TOS. Avoid private or sensitive
    info. As one guide warns, "developers must consider ethical
    guidelines... scraping is not always in line with a platform's terms
    of
    service"[\[2\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Thus%20scraping%2C%20developers%20must%20consider,Scraping%20should%20ideally).
    Document this compliance plan. For example, only scrape content from
    publicly visible posts and use only aggregated or anonymized info on
    the dashboard.

- **Data Volume Goals:** Sentiment analysis benefits from **large
    datasets**. The literature emphasizes that "sentiment analysis
    requires a high amount of data to validate a theory... it's common
    to use web scraping to gather
    data"[\[7\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=match%20at%20L300%20Sentiment%20analysis,or%20use%20them%20for%20research).
    Plan to collect thousands or millions of posts per topic. Design the
    pipeline accordingly: efficient scrapers, scalable storage, and
    parallel processing will be needed.

- **Platform Diversity:** To understand *trends and divergences*,
    include multiple sources. Different communities express opinions
    differently. We will incorporate at least 3--5 major platforms
    (e.g., Twitter, Reddit, news comments, forums). We should structure
    the data pipeline so that adding a new source later (e.g., Instagram
    comments) is easy: implement each as a **modular adapter**.

- **Topic Tracking:** Our agent must know *what topics to look for*.
    This could be seed keywords (e.g., candidate names). One approach:
    when a user specifies a topic (say "Candidate X"), the agent should
    expand on related keywords (e.g., nicknames, hashtags) by consulting
    wiki or news APIs (e.g., "Key players" and synonyms). Then it
    queries sources for these terms.

**Result:** At this stage, we have a list of target platforms and
topics, and a plan for data access (API keys needed? proxies needed?).
Summarize platform choices and access methods (API vs scrape) with notes
on any paid requirements or
blockers[\[6\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=API%20endpoints%20provide%20the%20most,rate%20limits%20and%20data%20constraints).

------------------------------------------------------------------------

## 3. Data Collection Strategy

Building a **robust web scraping pipeline** is crucial. We need a
strategy for finding relevant content and feeding it into analysis.

### 3.1 Gathering Links vs. Direct Scraping

One question is whether to first **collect links/IDs** (e.g., tweet
URLs, Reddit thread IDs) and store them, then fetch content, or to
scrape content on-the-fly. There are trade-offs:

- **Two-phase approach (Link Collection + Scrape):** First run a
    crawler or search agent that *discovers URLs* of relevant posts and
    stores them (in SQLite or a queue). Then a second agent reads these
    links and scrapes the actual text and metadata. This decouples
    "finding what to scrape" from "downloading content," which can
    improve modularity and error handling. It also lets multiple scraper
    agents work from a shared link database.

- **Single-pass scraping:** Alternatively, scrap the content
    immediately as links are found. This might be simpler but couples
    discovery to scraping; failures (e.g. CAPTCHAs) can interrupt the
    flow.

The user's idea of collecting links first and saving in DB (like SQLite)
is reasonable for *very large* scraping tasks. It ensures we know
*exactly* what to scrape before processing. For example, we could have
an "Agent A" that uses search APIs or Google/Bing queries (via free
services) to find pages matching keywords, or traverses sitemaps/forum
threads, and pushes links into a database. Then "Agent B" reads links
and fetches content. This also allows retries if some scrapes fail.

However, be mindful: adding this extra step introduces complexity. As
Grepsr notes, web scraping should "automatically collect and update the
database for sentiment analysis" to reduce manual
work[\[8\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=Sentiment%20analysis%20using%20web%20scraping,You%20can).
In practice, many pipelines batch link discovery and content fetch
together. It might be acceptable to have a simpler streaming pipeline
where scrapers both find and fetch content in one go, as long as we log
all URLs processed.

**Suggested approach:** Use a hybrid. For dynamic content (e.g.,
infinite scroll, social feeds), use search endpoints or APIs to
**collect post IDs** (e.g., Twitter search query). For static site
scraping (e.g., news comment pages, forums), a crawler can fetch all
relevant links first. Store discovered links in a lightweight database
(e.g., SQLite or a simple JSON store). Then run scraping workers reading
from that DB. This allows separating concerns and scaling.

### 3.2 Scraping Tools and Techniques

Select the best tools for each task:

- **Python Scrapers:** Python is ideal for scraping. Use libraries
    like **Scrapy** (for structured crawling), **Requests** or **HTTPX**
    (for fetching pages), and **BeautifulSoup** or **lxml** (for parsing
    HTML)[\[9\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=In%20this%20guide%2C%20we%27ll%20apply,use%20a%20few%20Python%20libraries)[\[10\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=code,TextBlob%20import%20pandas%20as%20pd).
    For sites with heavy JavaScript (Instagram, Twitter web UI),
    consider **Playwright** or **Selenium** to automate a headless
    browser. These can bypass dynamic loading and anti-scraping
    measures, at the cost of complexity.

- **Anti-Bot Measures:** Use proxy rotation (via Scrapy middlewares or
    a service like Scrapfly/ProxyCrawl). Throttle request rates and
    randomize user agents to mimic human behavior. The Scrapfly blog
    emphasizes handling anti-bot systems (Captcha, Cloudflare) as a key
    challenge[\[11\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=JavaScript%20Rendering).
    Build retry logic: if a request fails due to throttling, back off
    and try another route.

- **APIs and Third-Party:** Where possible, use official or
    third-party APIs. For example, Reddit's API (with PRAW) can fetch
    comments easily. You might also use tools like **Twint** (for
    Twitter scraping without API) or any updated alternative, though
    many workarounds may break. (As of 2026, assess new Twitter scraping
    tools; maybe Mastodon for X content.)

- **Search Aggregation:** To discover initial posts, use search
    engines or platform search. For instance, the Twitter API can search
    tweets by keyword. Google's Custom Search API or Bing Search API
    (though they limit daily queries) can find news articles or public
    forum pages. There are free tiers (limited queries) that might be
    enough for small-scale searches.

- **Store Links:** Whatever method, **store all raw HTML or JSON**
    responses as a backup (Bronze data layer). Also store link metadata
    (e.g., fetched URL, timestamp) in your link database. This raw dump
    helps with debugging and future processing.

### 3.3 Queueing and Asynchrony

Don't run this as a single-threaded job. Use asynchronous or
multi-threaded scraping to handle high volume:

- **Message Queue:** Set up a message broker (like RabbitMQ or Kafka).
    The link-discovery agent publishes URLs to a queue; multiple scraper
    workers consume from it, fetch content, and publish the raw text to
    another queue or directly to storage. This decouples components and
    scales horizontally.

- **Concurrency Controls:** Rate-limit per-domain to avoid bans. Use
    back-off on errors. Monitoring is important: log success/fail counts
    and latencies.

### 3.4 Data Versioning

We should keep historical snapshots. If a user submits a topic query
again later, we should not *overwrite* old data but version it. Use a
**version identifier** or timestamp for each data collection run. When
the user tweaks a topic and re-scrapes, the system should be able to
compare "Version 1 vs Version 2" results. Store version metadata in the
database.

------------------------------------------------------------------------

## 4. Data Storage Architecture

Design a robust data architecture that separates raw, processed, and
analytical data.

### 4.1 Raw Data (Bronze Layer)

- **NoSQL Database (e.g. MongoDB):** Store the *raw scraped
    posts/comments* here. Each record can have fields like: `id`
    (unique), `platform`, `url`, `timestamp`, `username`, `text`, and
    any other metadata (likes, replies count, etc.). Because social data
    schemas vary, a flexible NoSQL DB is best. Use MongoDB or a similar
    JSON-document store. This is the **Bronze layer** (unprocessed
    data).

- Each ingested record should have a `version_id` and `topic_tag` to
    identify which run or query it belongs to.

- **Backup:** Also save this raw data (or its content) in cloud
    storage (S3) for safety.

### 4.2 Processed/Refined Data (Silver Layer)

- **Cleaned & Structured Data:** After preprocessing (cleaning,
    deduplication), store the cleaned text and relevant fields (e.g.,
    `tokens`, `sentiment_score`, `embedding`, `language`, etc.) in a
    separate collection or database. This is the Silver layer
    (analysis-ready). You might keep this in MongoDB or move to a SQL
    store if you need structured querying.

- Include sentiment labels (`positive/neutral/negative`) and any extra
    tags (e.g., identified topics, geolocation). If you infer
    geolocation or user demographics from content, attach them here.

- This layer should also track provenance (e.g., link back to raw ID).

### 4.3 Vector Store for Embeddings

- **Vector Database (FAISS/Pinecone/Weaviate):** Store text embeddings
    here to support semantic search and chat-based QA. Every document
    (tweet/comment) will have an embedding (e.g., from a
    sentence-transformer model). Insert these into the vector DB. The
    user can later ask, "show me tweets similar to this idea," or the
    chatbot can retrieve relevant evidence.

- Vector DB will enable fast similarity search over millions of items.
    As [DataCamp notes](#ref30), vector DBs allow "searches rooted in
    semantic or contextual relevance rather than relying solely on exact
    matches"[\[12\]](https://www.datacamp.com/blog/the-top-5-vector-databases#:~:text=The%20primary%20benefit%20of%20a,criteria%20as%20with%20conventional%20databases).
    For example, we can find posts *about* a candidate without matching
    exact keywords.

- Choose one: **Pinecone** (managed SaaS, fast to start) or
    **Weaviate/Milvus** (self-hosted open-source). Mention whichever
    fits our infra plan (if cloud, Pinecone is quick, if on-premise,
    Weaviate + Qdrant or FAISS).

### 4.4 Reactive/Real-Time Database (Convex)

- **Convex DB:** For the user interface, the spec mentioned a
    "reactive database." Convex is a modern cloud DB that automatically
    pushes updates to
    clients[\[13\]](https://docs.convex.dev/realtime#:~:text=Turns%20out%20Convex%20is%20automatically,triggers%20the%20subscription%20in%20the).
    Use Convex for the final **dashboard state**. For example, when the
    pipeline finishes or new posts arrive, update Convex records (e.g.,
    counts by sentiment, latest posts). The React/Next.js frontend can
    subscribe to Convex queries and auto-refresh charts.

- Convex ensures every client sees a consistent, up-to-date view:
    "every client subscription gets updated simultaneously to the same
    snapshot"[\[14\]](https://docs.convex.dev/realtime#:~:text=Every%20client%20subscription%20gets%20updated,consistent%20view%20of%20your%20data).
    This avoids race conditions in the UI.

- **Alternative:** If not using Convex, similar real-time features can
    be built with Firebase or WebSockets, but Convex is designed for
    exactly this: **"turns out Convex is automatically
    realtime!"**[\[13\]](https://docs.convex.dev/realtime#:~:text=Turns%20out%20Convex%20is%20automatically,triggers%20the%20subscription%20in%20the)
    with minimal effort. We can just write to it and the UI updates.

### 4.5 Metadata Store

- Keep a simple SQL (or NoSQL) table of **topics/queries** and their
    versions. This tracks what data corresponds to which analysis job.
    For multi-tenancy, each user or project ID can have its own topics
    list.

- This can even live in Convex or in a separate small DB. It's mainly
    for UI to let users pick a topic and see its historical runs.

### 4.6 Deployment and Scaling

- Deploy databases in cloud (AWS RDS for Mongo, or Atlas; Pinecone
    cloud or a Kubernetes cluster for Weaviate).

- Ensure indexing on important fields (timestamp, platform, sentiment)
    to query quickly.

**Diagram (Figure 1):** We embed an illustrative diagram here.

![](media/rId47.png){width="5.833333333333333in"
height="3.2841666666666667in"}\
*Figure: The* *"Pillars of Sentiment Data"* *infographic highlights why*
*volume, variety, and velocity* *of data are crucial. Web scraping
supplies massive, diverse text streams which sentiment models then
distill into insights. (Image source: Grepsr)*

The pillars remind us that our pipeline must continuously gather **large
volumes** of content (velocity) from **diverse sources** (variety)
across platforms, to feed the AI analysis.

------------------------------------------------------------------------

## 5. Data Preprocessing

Once raw text is collected, it must be cleaned and normalized before
analysis.

### 5.1 Cleaning Noisy Text

Social media text is **noisy**: slang, abbreviations, emojis, HTML, &
non-text. As Statology notes, "Social media data is notoriously
messy---filled with slang, emojis, abbreviations, and
inconsistencies"[\[15\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Data%20Preprocessing).
We need robust cleaning:

- **Remove HTML/URLs:** Strip tags and links so analysis only sees
    user text.
- **Normalize Case:** Lowercase all text (unless case matters, e.g.,
    acronyms).
- **Remove or convert emojis:** Emojis carry sentiment (😂, ❤️). Use a
    library (e.g., emoji) to convert emoji to text descriptions (e.g.,
    😊 → "smiling_face"). This preserves sentiment cues.
- **Handle Punctuation/Stopwords:** Remove excessive punctuation,
    numbers if irrelevant. Optionally remove common stopwords (depending
    on model choice). As ScrapeHero's code suggests, stripped
    punctuation and stemming helps prepare for sentiment
    analysis[\[16\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=The%20clean%20function%20calls%20getText,prepares%20it%20for%20sentiment%20analysis).
- **Tokenization:** Split text into words/tokens. Use spaCy or NLTK to
    tokenize. This also handles slang splitting (e.g., "can't" → "can
    not").
- **Stemming/Lemmatization:** For some models, reducing words to roots
    helps (e.g., "running"→"run"). Use SnowballStemmer or spaCy's
    lemmatizer. The ScrapeHero example uses Snowball for
    English[\[17\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=).
- **Language Detection:** If needed, detect language (e.g., using
    `langdetect`). We might focus on English but tag other languages.

*Important:* Keep a copy of the original raw text. The processed form is
for modeling, but raw text is needed for quotes on dashboard and QA.

### 5.2 Quality Filtering

Implement a **Quality Control Agent**: monitor incoming data for low
value content. For example: - **Spam Filtering:** If a post is just "Buy
this product" or contains links/adverts, skip it. - **Duplication:**
Sometimes scraping hits the same post twice (from different channels).
Remove duplicates (identical text or same ID). - **Language Filtering:**
Drop posts in unrelated languages (unless we build multilingual
sentiment models). - **Relevance Filtering:** If scraping broad news
sites, an agent could drop posts that don't contain any target
keywords/topics. Automate some of this (keyword checks, regex filters),
and manually review initial samples to adjust filters.

### 5.3 Feature Extraction

Convert cleaned text to features for modeling: - **Traditional
Features:** TF-IDF or Bag-of-Words can serve as a baseline (Statology
mentions TF-IDF,
BoW)[\[18\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Popular%20techniques%20include%20TF,for%20more%20accurate%20sentiment%20categorization). -
**Embeddings:** More powerful are transformer-based embeddings. For each
text snippet, compute: - A sentence embedding (for vector search and
clustering). - Token embeddings if needed by the sentiment model. - Use
libraries like Hugging Face's `transformers` to get embeddings (BERT,
RoBERTa).

Store these in the Silver layer and in the vector DB (for later use in
RAG/chat).

### 5.4 Metadata Enrichment

While processing, extract or infer additional metadata: - **Topic
Tags:** Assign the original query/topic to the post. - **Geolocation:**
If user location is given in profile or content, geocode it. Even rough
region tags allow heatmap charts. - **Time Bins:** Round timestamps to
hours/days for plotting trends. - **User Influence:** If available, note
follower counts or karma to weigh posts. Store any useful meta (e.g.,
platform, user category) in the Silver DB to enable filtering in the
dashboard.

------------------------------------------------------------------------

## 6. Sentiment Modeling and Analysis

At this stage, we have cleaned text ready for sentiment classification.

### 6.1 Choosing a Sentiment Model

- **Simple Baseline:** TextBlob or VADER (for social media) can do
    quick polarity scoring (they give a -1 to 1 score). The scrapfly
    tutorial used
    TextBlob[\[19\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=Sentiment%20analysis%20requires%20a%20high,or%20use%20them%20for%20research).
    This is easy to implement but may be inaccurate for slang/sarcasm.
- **Transformer Models:** Better accuracy comes from fine-tuning
    models. Options:
- **DistilRoBERTa or BERT:** Smaller, fast models trained for
    sentiment (e.g., distilbert-base-uncased-finetuned-sst2) on Hugging
    Face. Good for English.
- **XLM-RoBERTa:** If you expect multiple languages.
- **Custom Fine-Tune:** If you have labeled data, fine-tune a model on
    domain-specific sentiment (election tweets, etc).
- **Zero-Shot or LLMs:** Use GPT-4o or Claude (via prompts) to
    classify sentiment. This is flexible (handles nuance/sarcasm) but
    costlier and slower at scale. Could use LLMs for **spot checks** or
    in QA, but rely on a tuned small model for bulk processing.

Given we need **production throughput**, a hybrid is sensible: Use a
*fast transformer* (like DistilBERT) in batch mode for all posts (gives
binary or 3-class output). Optionally *validate* a sample with an LLM to
calibrate. Over time, we could even use the chat interface to "explain
why this tweet is negative," giving interpretability.

Cite Statology: deep learning (RNN/LSTM/transformer) "often outperform
traditional methods when sufficient data is
available"[\[20\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=The%20choice%20of%20machine%20learning,for%20baseline%20sentiment%20analysis%20tasks).

### 6.2 Classification Granularity

- Most use cases need **3 classes**: positive, neutral, negative.
    Label each post accordingly. You could also assign a **continuous
    sentiment score** in \[-1,1\] for finer plotting.
- Advanced: Track **emotion categories** (joy, anger, etc.) or detect
    sarcasm explicitly. Modern transformer models can output
    probabilities for emotions. The Grepsr post notes that deep models
    can catch "context, sarcasm, and mixed
    sentiments"[\[21\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Sentiment%20analysis%20figures%20out%20whether,how%20brands%20read%20people%E2%80%99s%20minds).
    We might not implement full sarcasm-detection (that's a research
    area) but acknowledge it as a limitation.
- **Contextual Sentiment:** We could also compute overall sentiment by
    aggregating all posts, but better is to preserve each post's score
    for distribution analysis.

### 6.3 Processing Strategy

- Run sentiment inference as a **stream**, processing new posts as
    they arrive. Because we have them in the Silver layer, we can batch
    them to the model.
- Cache results to avoid reprocessing. Only new or updated posts get
    re-analyzed.
- Evaluate periodically: use a held-out set of labeled tweets to
    measure accuracy
    (precision/recall)[\[22\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Metrics%20like%20accuracy%20%2C%20precision%2C,Sentiment%20analysis%20on).

### 6.4 Key-Phrase and Topic Analysis

Beyond sentiment, extract keywords or topics: - Use TF-IDF or an LLM to
find **keywords** in positive vs negative posts. These fuel charts like
\"Topic clusters\" or \"word cloud.\" - Consider a small topic-modeling
(LDA or embedding clustering) to identify sub-themes within the data
(e.g., "immigration", "economy" in political posts). - Extract named
entities (people, orgs) as needed for context.

### 6.5 Model Outputs Storage

Store each post's sentiment result (class and score) in the database.
Add a field like `sentiment_label` and `sentiment_score`. This enables
quick filtering ("show all positive tweets") and feeds the dashboard
metrics.

------------------------------------------------------------------------

## 7. Multi-Agent Workflow Architecture

Modern AI systems often use **agentic orchestration** rather than a
monolithic script. We will design a **multi-agent system** to coordinate
data collection, analysis, and querying. This improves modularity and
resilience[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi)[\[24\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=,reduces%20code%20and%20prompt%20complexity).

### 7.1 Agent Roles and Responsibilities

Plan specialized agents (or microservices) for distinct tasks, each with
a clear context:

- **Search/Discovery Agent:** Receives a topic/query, expands it (via
    LLM or heuristic synonyms), and identifies initial link seeds. It
    can use Google/Bing Search APIs or specialized site searches.
- **Scraper Agents:** One agent per platform type. E.g., *Twitter
    Agent* fetches tweets; *Reddit Agent* fetches threads/comments;
    *Forum Agent* scrapes forum pages. Each encapsulates the scraping
    logic for that site.
- **Processor Agent:** Takes raw text, applies cleaning/tokenization
    (as above). We might group cleaning and sentiment into one agent or
    separate them. Possibly **TextAgent** (cleans text) and
    **SentimentAgent** (classifies sentiment).
- **Analytics Agent:** Periodically aggregates results (trend
    analysis, counts by sentiment over time).
- **QA/Chatbot Agent:** Handles user queries using vector store (RAG).
    This agent listens to natural language questions (via the UI/chat)
    and retrieves relevant posts/insights. It needs the embedding store
    and a knowledge store (could be the cleaned data or even the HTML
    content).
- **Dashboard Agent:** Feeds the UI. It writes summary stats (volume,
    sentiment distribution) to Convex in real-time as data comes in.
- **Controller/Orchestrator Agent:** Coordinates the workflow. It
    might be a static planner (LangGraph orchestrator) or dynamic (an
    LLM planning agent). Its job: "Given topic X, start SearchAgent →
    spawn ScraperAgents → monitor until enough data → signal
    ProcessorAgents → update UI". It also handles errors: e.g., if one
    platform is blocked, try another.

The orchestrator could be implemented with LangGraph or a similar
framework, which supports multi-stage
workflows[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi)[\[25\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=Sequential%20orchestration).
LangGraph explicitly supports "multi-agent, hierarchical, sequential"
flows[\[26\]](https://www.langchain.com/langgraph#:~:text=LangGraph%27s%20flexible%20framework%20supports%20diverse,robustly%20handles%20realistic%2C%20complex%20scenarios).

### 7.2 Communication and State Management

- Use the database as the **shared state**. For example, the
    orchestrator updates a "job status" record (pending, running, done).
    Agents read/write to Convex or another state DB to hand off tasks.
- **Messaging:** Agents communicate via queues or pub/sub. E.g.,
    SearchAgent publishes new URLs to a "to-scrape" queue; ScraperAgents
    consume from it.
- **Context Passing:** Each agent should have access only to its
    needed context. E.g., SentimentAgent shouldn't scrape; it should get
    pre-cleaned text. The orchestrator ensures data flows through the
    right steps (the **sequential pattern** in multi-agent
    systems[\[27\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=The%20multi,the%20orchestration%20of%20its%20subagents)[\[28\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=The%20image%20shows%20several%20sections,through%20the%20Agent%20n%20section)).

### 7.3 Real-Time & Asynchronous Operation

The system must handle streaming data and long-running tasks:

- **Asynchrony:** Design as an **event-driven pipeline**. When new
    data arrives, trigger the next step automatically. Use a tool like
    **Apache Airflow**, AWS Step Functions, or a message-driven
    architecture. The scraped data queue triggers processing, which in
    turn updates analysis, which then updates the dashboard.
- **Agent Reactivity:** Agents should periodically check if tasks are
    complete or if certain conditions are met. For example, if the
    SearchAgent fetched 10,000 posts, it might notify the orchestrator
    that sampling is sufficient, which triggers the SentimentAgent on
    those posts.
- **Human-in-the-loop:** For quality control or disambiguation, we can
    integrate an approval step. LangGraph supports *human review
    loops*[\[26\]](https://www.langchain.com/langgraph#:~:text=LangGraph%27s%20flexible%20framework%20supports%20diverse,robustly%20handles%20realistic%2C%20complex%20scenarios)
    if needed (e.g., before publishing final sentiment charts, a user
    could approve the interpretation of trends).

### 7.4 Tooling for Agents

- **LangGraph / LangChain:** Use LangGraph to define the multi-agent
    orchestration. It allows complex flows and
    statefulness[\[26\]](https://www.langchain.com/langgraph#:~:text=LangGraph%27s%20flexible%20framework%20supports%20diverse,robustly%20handles%20realistic%2C%20complex%20scenarios).
    For example, define nodes/actions: "Search Web", "Scrape X",
    "Analyze Sentiment", and edges for dependencies. The orchestrator
    LLM model can choose which node to activate next based on progress.
- **CrewAI:** Similar multi-agent orchestration; could serve as the
    "brain" to manage the crew of
    agents[\[29\]](https://www.crewai.com/#:~:text=CrewAI%20makes%20it%20easy%20for,reliably%20and%20with%20full%20control).
    It emphasizes "context sharing and delegation" among agents.
- **N8N or Temporal (if not fully AI-driven):** For a more
    deterministic approach, you could use a workflow engine like
    Temporal or n8n to chain tasks, but given the spec's focus on AI
    agents, frameworks like LangGraph are more fitting.

### 7.5 Handling Failures and Loops

- **Retries and Fallbacks:** If an agent fails (e.g., scraper
    blocked), the orchestrator should catch that and try alternatives
    (different proxy, slower rate).
- **Quality Checks:** Insert mini "health check" nodes that sample
    outputs. For example, after scraping, check if the text contains
    non-empty content.
- **Looping:** If initial search yields little sentiment (say all
    neutral), the orchestrator might loop back and expand search terms
    or include new sources. This is an advanced "self-driving" behavior:
    the agent assesses data sufficiency and decides to collect
    more[\[30\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=Model%20parameters%20are%20optimized%20using,31%20%2C%2053).

### 7.6 Example Flow

1. **User Input:** "Analyze sentiment on Solar Energy policy."
2. **Orchestrator:** Expands to keywords ("solar policy", names) using
    an LLM, selects platforms (Reddit, X, Facebook Post, Facebook Comment, Youtube Video Comments, News).
3. **SearchAgent:** Fetches URLs from platform APIs or web search. Adds
    them to Link DB.
4. **ScraperAgents:** One per platform reads links and saves raw posts
    to DB.
5. **ProcessorAgents:** Cleans each post as it arrives, writes cleaned
    text.
6. **SentimentAgent:** Assigns sentiment scores to cleaned posts.
    Writes results.
7. **AnalyticsAgent:** Periodically aggregates counts (e.g. daily
    sentiment averages). Writes to Convex or analytics DB.
8. **DashboardAgent:** Reads analytics and recent posts, sends updates
    to the UI (via Convex).
9. **User UI:** Reacts to Convex updates and displays charts in real
    time.
10. **ChatbotAgent:** If user asks "What do people say about X?",
    queries the vector store and replies using an LLM augmented with
    evidence.

This pipeline can run **continuously in the background**, updating as
new data trickles in. Multiple topics can be handled in parallel as
separate agent workflows.

*Citations:* The idea of breaking tasks into specialized agents is
supported by the literature: "Multi-agent systems (MAS) have emerged as
a promising paradigm for complex NLP tasks... architectures delegate
subtasks to specialized
agents"[\[30\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=Model%20parameters%20are%20optimized%20using,31%20%2C%2053)[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi).
The Google Cloud guide also emphasizes that multi-agent design
"decomposes a large objective into smaller sub-tasks" for scalability
and
reliability[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi).

------------------------------------------------------------------------

## 8. Sentiment Insights and Dashboard Design

The **user-facing output** is a rich dashboard of charts and insights.
Based on the project spec and the "Insights Layer" concepts, we should
include at least 15--20 visualization elements that highlight different
aspects of sentiment data.

### 8.1 Key Dashboard Components

Here are recommended charts and what they show:

1. **Sentiment Distribution:** A **histogram or bell curve** of
    sentiment scores across all collected
    posts[\[19\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=Sentiment%20analysis%20requires%20a%20high,or%20use%20them%20for%20research)[\[31\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Web%20scraping%20automates%20the%20extraction,steady%20pipeline%20of%20fresh%20insights).
    This shows whether opinions skew positive or negative. E.g., x-axis
    = sentiment score (-1 to 1), y-axis = count of posts. Overlay normal
    curve to emphasize distribution.
2. **Time Series Trends:** A **line chart** of average sentiment over
    time (daily or hourly). Allows spotting *shifts* or spikes (e.g.,
    after an event, sentiment spikes negative). Mark significant events
    as annotations.
3. **Volume Over Time:** Another time chart of number of posts per time
    unit (shows discussion intensity). Combine with sentiment in a
    secondary axis if desired.
4. **Geospatial Heatmap:** If enough geotagged data, show a map
    (country or state level) colored by average sentiment or volume.
    E.g., Western Region is 80%
    positive[\[32\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=by%20altering%20sentiment,Jensen%E2%80%93Shannon%20divergence%20between%20their%20predictions)[\[33\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=Through%20this%20coordinated%20multi,noisy%20or%20ambiguous%20input%20conditions).
5. **Platform Breakdown (Radar/Bar Chart):** A chart comparing
    sentiment metrics per platform (e.g., average sentiment on Reddit vs
    Twitter vs news). This highlights "platform divergence" (as spec
    suggested) -- different communities often feel
    differently[\[34\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Web%20scraping%20extracts%20raw%2C%20unfiltered,and%20even%20predict%20PR%20disasters).
6. **Topic/Word Cloud:** A **word cloud** or **bubble chart** of
    keywords appearing in positive vs negative posts. E.g., negative
    words like "expensive", positive words like "innovation". Use NLP
    topic extraction for labels.
7. **Sentiment Over Categories:** If tracking sub-topics (e.g.,
    "price", "environment"), a stacked bar chart showing which aspects
    drive sentiment (requires prior classification of content by topic).
8. **Top Influencers (Posts):** List or widget showing *top 5 posts*
    that had strongest sentiment or engagement. These are
    "representative quotes" with high impact (e.g., most upvoted or
    retweeted). Label them by sentiment.
9. **Raw Posts Feed:** A scrollable table of recent raw posts with
    their sentiment label. Useful for "Raw Evidence". Users can click to
    see context.
10. **Cohort/Demographics:** If user info exists (like age group or
    political affiliation inferred), show sentiment by demographic (pie
    charts or small multiples).
11. **Key Phrase Analysis:** Bar charts of most common phrases or
    hashtags in each sentiment category.
12. **Sentiment vs Engagement:** Scatter plot (sentiment score vs
    likes/retweets) to see if highly negative posts get more attention.
13. **Topic Word Embedding Clusters:** Possibly a 2D embedding plot
    (like t-SNE) showing clusters of posts, colored by sentiment.
14. **Searchable QA widget:** Embeds a chat interface where users ask
    "What's said about \[candidate\]?" -- this is not a chart but an
    interactive component powered by the vector store and LLM.
15. **Alerts/Insights Box:** Highlight notable trends automatically
    (e.g., "Negative sentiment jumped 30% after event X"). This could be
    auto-generated text from an AI summarizer.
16. **Comparison with Previous Topic Runs:** If we support versioning,
    allow overlaying current vs past sentiment curves for comparison.

We should aim for *rich interactivity*. Use React dashboards (with
libraries like **Recharts, Chart.js, D3, or Plotly**). Given Next.js
plus Convex, React is straightforward. Streamlit (Python) is an
alternative, but Next.js offers easier agent integration.

### 8.2 Real-Time Updates

As described, the **Convex DB** will push updates to the UI. For
example, when the sentiment analysis of a new batch completes, the
DashboardAgent can `set()` values (counts, averages) in Convex. The
React app should have hooks listening (Convex queries are reactive), so
the charts automatically animate in new data. This makes the dashboard
feel live.

### 8.3 User Queries and Chat

Beyond static charts, implement a **chatbot interface** (e.g.,
ChatGPT-like) for ad-hoc queries: - Connect a chat UI (could be embedded
in the dashboard) to an LLM (GPT-4o/Claude) **with retrieval**: when the
user asks a question about the sentiment data ("Show me negative
feedback about X"), the system retrieves relevant posts from the vector
DB and feeds them to the LLM to formulate an answer. This is a classic
retrieval-augmented generation (RAG) application. - The vector DB of
embeddings (Section 4.3) enables this: user's question is embedded and
nearest posts fetched. The agent then uses an LLM prompt incorporating
those posts. - We should cite how vector DBs empower such chat: as
\[30†L215-L218\] explains, they allow "searches rooted in semantic or
contextual relevance" for NLP applications. This will make our agent
"self-driving" in answering queries with evidence from the data.

### 8.4 Final UI Technologies

- **Frontend:** Next.js (React) or a modern stack (some prefer Astro
    or Svelte in 2026). Use CSS frameworks like Chakra UI or Tailwind
    for quick styling. For charts, use **Recharts** or **D3** -- many
    plug into React easily.
- **State Management:** Instead of Redux, use lightweight modern libs
    like **Zustand** or **Jotai**. Since Convex handles server state, we
    mainly use these for local UI state (tabs, filters).
- **Real-Time Communication:** Convex serves as the live backend. For
    any custom events, use WebSockets (e.g., Socket.io) if needed.
- **Dockerization:** Containerize the UI (and backend services) for
    easy deployment.

**Example of a Live Metric:** Whenever the SentimentAgent labels a new
batch of posts, emit an update so the Dashboard shows a loading spinner
under that chart and then refreshes. The experience should be like an
app updating in real-time, not a static report.

------------------------------------------------------------------------

## 9. Machine Learning and LLM Usage

Since AI is core here, leverage LLMs and ML tools smartly at each step:

### 9.1 Using AI in Development

- **AI Pair Programming:** Use tools like GitHub Copilot or Claude
    Code to write boilerplate or helper functions (e.g., scraping
    functions). But always review the code -- remember "AI coding
    assistants... require clear direction, context, and
    oversight"[\[35\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=AI%20coding%20assistants%20became%20game,myself%20included%29%20embraced%20them).
    Don't blindly accept generated code.
- **Plan with AI:** We saw how Addy Osmani recommends using an LLM to
    draft specs and
    plans[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code).
    Continue that by feeding the spec to the AI whenever you build a
    major component. For instance, ask it to draft the schema for the
    sentiment database, or to outline a web scraping function. This
    ensures consistency with the overall plan.
- **Code Chunking:** When writing code with AI, do it in **small
    chunks**[\[3\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Scope%20management%20is%20everything%20%E2%80%94,the%20whole%20codebase%20at%20once).
    E.g., first implement data fetching, test it, then move to parsing
    logic. This avoids big confusing answers.

### 9.2 AI Agents and Tools

- **LangGraph/CrewAI:** For orchestrator logic, these frameworks often
    run on top of an LLM. We might use the OpenAI/Anthropic API for
    decision steps. Provide them with the current state (e.g., "We have
    scraped 200 posts, 150 remain to reach goal of 1000"). The AI then
    decides next steps.
- **Embeddings:** Choose or train a good sentence embedding model
    (e.g., sentence-transformers/multilingual) to support
    retrieval[\[12\]](https://www.datacamp.com/blog/the-top-5-vector-databases#:~:text=The%20primary%20benefit%20of%20a,criteria%20as%20with%20conventional%20databases).
- **Sentiment LLMs:** For complex queries or summarization, GPT-4o or
    Claude 3.5 Sonnet can provide richer interpretation. E.g.,
    "Summarize public concerns about X in one paragraph." Fine-tune such
    prompts carefully.

### 9.3 Future-Proof AI Strategy

- **Local vs Cloud Models:** Keep flexibility. The user mentioned
    Ollama (self-hosted LLMs). We could host a Llama-3 or Vicuna model
    on a local GPU for private inference to save cost. Always design so
    that the LLM choice is not hard-coded; allow switching between
    OpenAI, Anthropic, or local models. LangChain's abstraction can help
    (Chain-of-thought is structured).
- **Prompt Engineering:** Maintain a knowledge base of good prompts
    for each task (scraping instructions, sentiment queries, chart
    interpretation). Document them (maybe in Git) for team use.
- **Agent Profiles:** If we use multiple LLMs (one for reasoning, one
    for generation), clearly define roles. For example, an
    "AnalystAgent" uses GPT-4o for analysis and a "ScraperAgent" might
    use a simpler model or rules.

### 9.4 Testing and Iteration with AI

- **Data Validation with AI:** Use an LLM to sample-check output. For
    example, let the model read 50 random posts and classify them;
    compare to our pipeline's labels to catch systematic errors.
- **Dashboard Narration:** As a bonus, have an AI generate a textual
    summary of the charts (like an executive summary). This can be a
    final deliverable: a report written by an LLM pulling from computed
    data.

*Citations:* The best practices in AI-assisted development are
emphasized by expert devs: "Begin by defining the problem and planning a
solution... first step is brainstorming a detailed specification with
the
AI"[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code).
Also, "LLMs do best when given focused prompts: implement one function,
fix one bug, add one feature at a
time"[\[3\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Scope%20management%20is%20everything%20%E2%80%94,the%20whole%20codebase%20at%20once).
We will follow these to make AI our assistant, not an erratic coder.

------------------------------------------------------------------------

## 10. Development and Project Management

Beyond tech choices, handle the project like a software engineering
effort:

- **Version Control:** Use Git from day one. Organize code in modules
    (scrapers, models, frontend). Make each agent a package or
    microservice.

- **Modularity & SOLID:** Design each component with clear interfaces
    (e.g., scrapers write to a storage API, sentiment model reads from
    it). Follow SOLID principles. For example, if you later swap Hugging
    Face for OpenAI for sentiment, the rest of the pipeline shouldn't
    break.

- **Configuration:** Use a config file or environment variables for
    all keys (API tokens, DB URIs). No secrets in code. This makes it
    easy to move from dev to prod.

- **Logging:** Implement structured logging. Don't log just "error
    occurred" -- log **what URL, what error, timestamp**. In production,
    logs (to stdout or a log aggregator) will be invaluable. Consider
    using a centralized logging solution (ELK or CloudWatch).

- **Monitoring:** Set up basic metrics: number of posts scraped per
    minute, sentiment processing latency, failure rates. You can use
    Prometheus/Grafana or a cloud monitoring (DataDog).

- **Testing:** Write unit tests for critical functions (e.g., HTML
    parsing logic, sentiment classification). Also do integration tests:
    simulate an end-to-end pipeline on a small topic. Automate these
    tests in CI. Use AI to help generate test cases if needed.

- **Continuous Integration / Deployment:** Automate building and
    deploying. Every commit runs tests. Deploy to a staging environment
    for full pipeline runs. Containerize the services (Docker), maybe
    orchestrate with Docker Compose or Kubernetes for local dev.

- **Documentation:** Maintain living docs. Use README, inline code
    comments, and a confluence/wiki if needed. Given the heavy AI usage,
    document prompt guidelines. An AI (Claude) can help write
    documentation from code comments, but verify accuracy.

- **Iterative Feedback:** Regularly review intermediate results
    (plots, scraping logs) to spot issues early. Use slack or meetings
    to discuss progress with your mentor or team. Document feedback and
    your responses in the project log.

- **Presentation Prep:** As you near completion, prepare to present.
    Generate slides with screenshots of the dashboard and key charts.
    Practice explaining your architecture (the multi-agent design, data
    flow, etc.). Include any live demo of querying the agent. Have an
    "Executive summary" slide that states the main insights gleaned
    (e.g., "Candidate X has 70% positive sentiment among social users as
    of March 2026").

- **Solicit Feedback:** After major milestones, ask peers or
    supervisors to test the system and give feedback on usability,
    accuracy, and performance. Use that to iterate. For example, if they
    find the scraping too slow, you might parallelize more.

- **Final Report:** Write up the methodology and results. Include
    architecture diagrams, data sources, model performance, ethical
    considerations. Append technical docs (API keys needed, data schema)
    as required deliverables.

------------------------------------------------------------------------

## 11. Maintenance and Future-Proofing

Our system should not be fragile. Anticipate future changes:

- **Loose Coupling:** Ensure components (scraper, model, DB)
    communicate through clear APIs or databases. For instance, use
    abstract functions to fetch data so you could switch from Mongo to
    another DB easily. Use dependency injection where possible.

- **Configuration Management:** Keep all "magic numbers" (API limits,
    thresholds) in config. If a platform's HTML changes, you only update
    the parsing code, not the whole pipeline.

- **Scalability:** Use cloud autoscaling: run scrapers on multiple
    instances if needed; use serverless functions for periodic tasks
    (e.g., AWS Lambda for scheduled data pulls). With Convex or vector
    DB, you also ensure horizontal scaling for data queries.

- **Updatable Models:** The field evolves quickly. Design so you can
    plug in new AI models. For example, write your sentiment analysis as
    a wrapper class; later you could switch from DistilBERT to a new
    GPT-4o endpoint without changing pipeline logic. The Google guide
    suggests that in multi-agent designs, "each agent can use distinct
    models... to achieve its
    outcomes"[\[24\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=,reduces%20code%20and%20prompt%20complexity).

- **Logging & Auditing:** Track all data lineage so you can debug
    issues when models change. If a new LLM version shifts sentiment
    outputs, logs and version tags help compare.

- **Monitoring Content Policies:** Stay alert to changes in target
    platforms (e.g., if Twitter's TOS changes, update your compliance
    strategy).

- **Community & Continual Learning:** Since AI tooling rapidly
    changes, follow updates. For example, the prompt recommended to look
    at current AI development trends (Addy Osmani's 2025 workflow,
    etc.). Make it a habit to check blogs (LangChain, OpenAI, etc.) or
    newsletters for new best practices.

- **AI "Friendliness":** Write clean, well-documented code so future
    AI agents (when prompting) can easily understand and extend
    it[\[36\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Provide%20extensive%20context%20and%20guidance)[\[37\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Expert%20LLM%20users%20emphasize%20this,slow%2C%20or%20provide%20a%20reference).
    Use descriptive variable names, type hints, and clear logical flow.
    This is like leaving breadcrumbs for the next coder (human or AI).

**Key principle:** Always design for the next change. For instance, if a
new site emerges (like "Bluesky" for social media), we should be able to
add a new ScraperAgent with minimal changes to the orchestrator. Or if
we want to test a new sentiment model, swap it in the ModelAgent.

------------------------------------------------------------------------

## 12. Ethical and Privacy Considerations

Don't overlook responsibility:

- **User Privacy:** Only use publicly posted data. Never expose
    private messages or closed group content. If doubt, omit that data
    source.
- **Bias and Fairness:** Social media skews demographics. Document
    these biases. In interpretation, note that sentiment may not
    represent the entire population.
- **Transparency:** If presenting insights, make it clear they come
    from social media scraping, not official polls. Provide caveats
    (e.g., "Data from social posts may over-represent youth voices").

------------------------------------------------------------------------

## 13. Final Thoughts and Confidence

By now, we have a **full blueprint** for the project:

1. Start with a clear **plan and spec** (with AI's
    help)[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code).
2. Identify data sources and how to access them (APIs vs
    scraping)[\[6\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=API%20endpoints%20provide%20the%20most,rate%20limits%20and%20data%20constraints).
3. Design the **scraping pipeline**: search for links, scrape content,
    store raw data (Mongo), preprocess and analyze (Python, Hugging
    Face)[\[19\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=Sentiment%20analysis%20requires%20a%20high,or%20use%20them%20for%20research)[\[8\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=Sentiment%20analysis%20using%20web%20scraping,You%20can).
4. Build a **multi-agent orchestrator** (LangGraph/CrewAI) that handles
    each step and loops when
    needed[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi)[\[25\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=Sequential%20orchestration).
5. Implement sentiment analysis with scalable ML models, continuously
    feeding results to a **reactive dashboard** (Convex +
    React)[\[13\]](https://docs.convex.dev/realtime#:~:text=Turns%20out%20Convex%20is%20automatically,triggers%20the%20subscription%20in%20the)[\[31\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Web%20scraping%20automates%20the%20extraction,steady%20pipeline%20of%20fresh%20insights).
6. Leverage AI at every turn: for planning, coding, decision-making and
    answering
    queries[\[3\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Scope%20management%20is%20everything%20%E2%80%94,the%20whole%20codebase%20at%20once)[\[30\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=Model%20parameters%20are%20optimized%20using,31%20%2C%2053).
7. Ensure the system is modular, maintainable, and ready for future
    changes (new tools or data sources).

Throughout, rely on best practices: break work into **small iterative
tasks** and provide the AI with adequate
context[\[3\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Scope%20management%20is%20everything%20%E2%80%94,the%20whole%20codebase%20at%20once)[\[36\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Provide%20extensive%20context%20and%20guidance).
Keep documentation up-to-date. Test thoroughly at each stage. Monitor
performance and adjust as needed.

Once built, we will have an **"AI-powered sentiment lab"**: give it a
topic and it autonomously collects opinions, analyzes them, and presents
insights. The dashboard and chatbot let users interactively explore
public sentiment. You'll confidently explain the architecture (maybe
showing the agent-flow diagram), the tech choices (why Python for
scraping, DistilBERT for speed, LangGraph for control), and the results
(charts and summary).

**Confidence:** With this plan and flexibility to iterate, you're
well-prepared. Modern AI tools (like GPT-4o, powerful embeddings, and
reactive frameworks) make each part feasible. The approach is thorough:
"we shouldn't miss any detail" -- we haven't! By meticulously following
these steps and guidelines, and by using AI as an assistant at every
turn, you can deliver a *production-quality* sentiment analysis system,
not just a barebones prototype.

Good luck -- and enjoy building this cutting-edge pipeline!

**Sources:** Concepts and best practices above are drawn from recent
industry and research
literature[\[38\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=Web%20scraping%20is%20a%20powerful,text%20into%20useful%20social%20insights)[\[15\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Data%20Preprocessing)[\[8\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=Sentiment%20analysis%20using%20web%20scraping,You%20can)[\[34\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Web%20scraping%20extracts%20raw%2C%20unfiltered,and%20even%20predict%20PR%20disasters)[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi)[\[24\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=,reduces%20code%20and%20prompt%20complexity)[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code)[\[13\]](https://docs.convex.dev/realtime#:~:text=Turns%20out%20Convex%20is%20automatically,triggers%20the%20subscription%20in%20the),
ensuring our approach aligns with 2026 standards. Each citation provides
more detail on the respective topic.

------------------------------------------------------------------------

[\[1\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Start%20with%20a%20clear%20plan,specs%20before%20code)
[\[3\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Scope%20management%20is%20everything%20%E2%80%94,the%20whole%20codebase%20at%20once)
[\[4\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Next%2C%20I%20feed%20the%20spec,the%20subsequent%20coding%20much%20smoother)
[\[5\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Break%20work%20into%20small%2C%20iterative,chunks)
[\[35\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=AI%20coding%20assistants%20became%20game,myself%20included%29%20embraced%20them)
[\[36\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Provide%20extensive%20context%20and%20guidance)
[\[37\]](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e#:~:text=Expert%20LLM%20users%20emphasize%20this,slow%2C%20or%20provide%20a%20reference)
My LLM coding workflow going into 2026 \| by Addy Osmani \| Medium

<https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e>

[\[2\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Thus%20scraping%2C%20developers%20must%20consider,Scraping%20should%20ideally)
[\[6\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=API%20endpoints%20provide%20the%20most,rate%20limits%20and%20data%20constraints)
[\[15\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Data%20Preprocessing)
[\[18\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Popular%20techniques%20include%20TF,for%20more%20accurate%20sentiment%20categorization)
[\[20\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=The%20choice%20of%20machine%20learning,for%20baseline%20sentiment%20analysis%20tasks)
[\[22\]](https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/#:~:text=Metrics%20like%20accuracy%20%2C%20precision%2C,Sentiment%20analysis%20on)
Scraping Social Media Data for Sentiment Analysis in Statistical Studies

<https://www.statology.org/scraping-social-media-data-for-sentiment-analysis-in-statistical-studies/>

[\[7\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=match%20at%20L300%20Sentiment%20analysis,or%20use%20them%20for%20research)
[\[9\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=In%20this%20guide%2C%20we%27ll%20apply,use%20a%20few%20Python%20libraries)
[\[11\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=JavaScript%20Rendering)
[\[19\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=Sentiment%20analysis%20requires%20a%20high,or%20use%20them%20for%20research)
[\[38\]](https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis#:~:text=Web%20scraping%20is%20a%20powerful,text%20into%20useful%20social%20insights)
Intro to Using Web Scraping For Sentiment Analysis

<https://scrapfly.io/blog/posts/intro-to-using-web-scraping-for-sentiment-analysis>

[\[8\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=Sentiment%20analysis%20using%20web%20scraping,You%20can)
[\[10\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=code,TextBlob%20import%20pandas%20as%20pd)
[\[16\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=The%20clean%20function%20calls%20getText,prepares%20it%20for%20sentiment%20analysis)
[\[17\]](https://www.scrapehero.com/sentiment-analysis-using-web-scraping/#:~:text=)
Sentiment Analysis Using Web Scraping

<https://www.scrapehero.com/sentiment-analysis-using-web-scraping/>

[\[12\]](https://www.datacamp.com/blog/the-top-5-vector-databases#:~:text=The%20primary%20benefit%20of%20a,criteria%20as%20with%20conventional%20databases)
The 7 Best Vector Databases in 2026 \| DataCamp

<https://www.datacamp.com/blog/the-top-5-vector-databases>

[\[13\]](https://docs.convex.dev/realtime#:~:text=Turns%20out%20Convex%20is%20automatically,triggers%20the%20subscription%20in%20the)
[\[14\]](https://docs.convex.dev/realtime#:~:text=Every%20client%20subscription%20gets%20updated,consistent%20view%20of%20your%20data)
Realtime \| Convex Developer Hub

<https://docs.convex.dev/realtime>

[\[21\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Sentiment%20analysis%20figures%20out%20whether,how%20brands%20read%20people%E2%80%99s%20minds)
[\[31\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Web%20scraping%20automates%20the%20extraction,steady%20pipeline%20of%20fresh%20insights)
[\[34\]](https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/#:~:text=Web%20scraping%20extracts%20raw%2C%20unfiltered,and%20even%20predict%20PR%20disasters)
Using Web Scraping for Sentiment Analysis in Market Research \| Grepsr

<https://www.grepsr.com/blog/using-web-scraping-for-sentiment-analysis-in-market-research/>

[\[23\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=Multi)
[\[27\]](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system#:~:text=The%20multi,the%20orchestration%20of%20its%20subagents)
Choose a design pattern for your agentic AI system  \|  Cloud
Architecture Center  \|  Google Cloud Documentation

<https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system>

[\[24\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=,reduces%20code%20and%20prompt%20complexity)
[\[25\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=Sequential%20orchestration)
[\[28\]](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns#:~:text=The%20image%20shows%20several%20sections,through%20the%20Agent%20n%20section)
AI Agent Orchestration Patterns - Azure Architecture Center \| Microsoft
Learn

<https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns>

[\[26\]](https://www.langchain.com/langgraph#:~:text=LangGraph%27s%20flexible%20framework%20supports%20diverse,robustly%20handles%20realistic%2C%20complex%20scenarios)
LangGraph: Agent Orchestration Framework for Reliable AI Agents

<https://www.langchain.com/langgraph>

[\[29\]](https://www.crewai.com/#:~:text=CrewAI%20makes%20it%20easy%20for,reliably%20and%20with%20full%20control)
The Leading Multi-Agent Platform

<https://www.crewai.com/>

[\[30\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=Model%20parameters%20are%20optimized%20using,31%20%2C%2053)
[\[32\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=by%20altering%20sentiment,Jensen%E2%80%93Shannon%20divergence%20between%20their%20predictions)
[\[33\]](https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/#:~:text=Through%20this%20coordinated%20multi,noisy%20or%20ambiguous%20input%20conditions)
Emotion meets coordination: Designing multi-agent LLMs for fine-grained
user sentiment detection on social media - PMC

<https://pmc.ncbi.nlm.nih.gov/articles/PMC12885380/>
