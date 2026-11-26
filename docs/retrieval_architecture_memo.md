# ARCHITECTURE MEMO: Why Most AI Startups Pick the Wrong Database on Day 1

**Author:** Purnima Prajapati  
**Focus:** Retrieval Architecture for AI Workflows (SQL vs. FAISS vs. Milvus)  
**Core Thesis:** Most early-stage AI teams either choke their app on a standard SQL database or waste weeks babysitting heavy vector infrastructure they don't need yet. Here is the pragmatic middle path.

---

## 1. The Trap: Why Standard Databases Quietly Fail at AI Search
Relational databases (SQLite, MySQL, PostgreSQL) are unbeatable for structured records—user logins, billing, timestamps, and exact filters (`WHERE city = 'Mumbai'`). 

The moment you ask them to handle **semantic similarity** (e.g., matching *"automated outbound NDR calls"* with *"voice AI for D2C delivery verification"*), they hit a wall:
* **Keyword Blindness:** Traditional `LIKE` queries miss meaning entirely unless exact words overlap.
* **Brute-Force Slowdowns:** Storing 512- or 1536-dimensional embeddings as raw blobs and scanning every row forces $O(N)$ math—turning a snappy 80ms search into a multi-second lag as records grow.
* **Messy Schemas:** Jamming unstructured text chunks, JSON payloads, and vector arrays into transactional tables slows down routine app queries.

---

## 2. The Real-World Tradeoffs (No Hype)

Every retrieval engine solves one problem while creating another:

| What Matters in Production | Relational DB (SQLite / MySQL) | FAISS (In-Memory Vector Library) | Milvus (Dedicated Vector Database) |
| :--- | :--- | :--- | :--- |
| **Best At** | Exact filters, ACID transactions, zero setup | Blazing-fast similarity search inside Python | Scale, live updates, hybrid vector + metadata filters |
| **Operational Headache** | Almost none | Manual disk saves; deleting rows requires rebuilding indexes | Heavy (Docker/cluster setup, RAM/disk tuning) |
| **Live Data Updates** | Instant inserts/updates/deletes | Great for batch reads; clunky for constant single-row edits | Native real-time upserts and background compaction |
| **Metadata Filtering** | Native multi-column SQL | Weak (requires separate ID lookup in SQL) | Built-in hybrid filtering in a single query |

---

## 3. The Two Mistakes Early Teams Make
1. **The "SQL-Only" Bottleneck:** Running cosine similarity in Python loops over a MySQL table. Fine at 500 records; painful at 25,000.
2. **The "Day-1 Kubernetes" Overkill:** Spinning up a full containerized vector database cluster for 2,000 company profiles—spending more time debugging Docker memory limits than talking to users.

---

## 4. The Two-Stage Blueprint: Build Fast Now, Scale Without Rewriting

Keep your retrieval layer behind a clean `Retriever` interface so you can upgrade the engine without touching your app logic:

### Stage 1: MVP & Fast Iteration (< 50,000 Vectors) → `SQLite/MySQL + FAISS`
* **How it works:** Store structured metadata (company URLs, status, timestamps) in **SQLite or MySQL**, and run similarity search in a local **FAISS** index mapped by primary ID.
* **Why it wins:** Zero background servers, runs inside a single Python process, and delivers sub-second semantic search and lead deduplication out of the box.
* **Pro-tip:** Save FAISS index snapshots to disk after batch imports instead of rewriting the index on every single API call.

### Stage 2: Multi-User Scale & Hybrid Queries (> 50,000 Vectors) → `Milvus`
* **When to switch:** The day you need concurrent writes, real-time deletions without index rebuilds, or combined queries (*"Find the top 10 startups similar to X, filtered by `stage = Seed` and `country = India`"*).
* **Why it wins:** Separates compute from storage, handles hybrid scalar + vector search natively, and removes the need to manually sync two separate databases.