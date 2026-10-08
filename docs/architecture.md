# Blind Tuner — CodeUtsava X.0 PS4 Architecture

Oct 3, 2026 · @Anurag

## Overview

Blind Tuner finds fixes for slow database queries while its AI sees only disguised metadata, and it proves both the privacy and the speedup. The whole system fits in 24 hours if the scope cuts in the build plan are followed.

**The problem, in one example.** QuickMart's `sales` table has 50 million rows of purchases. Its weekly dashboard asks for total sales in region 7 since 26 Sept 2026. With no index, Postgres reads all 50 million rows to keep about 20,000, which takes 40 seconds, so the dashboard times out.

**The fix.** A composite index on `(region_id, transaction_date)` lets Postgres jump straight to those 20,000 rows, cutting the query to about 0.2 seconds. Finding fixes like this is a DBA's daily work, and PS4 wants an AI to do it.

**The catch.** The rows hold customer emails and revenue, so they cannot be sent to an outside AI. PS4 says the AI may see only metadata: facts about the data, never the data itself.

**Why it still works.** The fix depends on the *shape* of the query, not on what is inside the rows. Which column uses `=`, which uses `>=`, how many rows exist and how many were read: all of that survives disguise, and it is exactly what a DBA uses.

**The pitch line.** "Everyone else asks you to trust their AI with your data. We prove it never saw it, and we prove every change works before you apply it."

**Can it be built in 24 hours?** Yes, under three conditions:

1. The Docker image and the training data are prepared before hour 6.
2. One hero query works end to end before any extra feature is started.
3. Partitioning is tested only on the twin, and sharding is given as written advice, not simulated.

## Glossary

Every term in this doc, explained with the QuickMart example.

| Term | What it means (QuickMart example) |
| --- | --- |
| Table | A giant spreadsheet. `sales` has 50M rows, one per purchase. |
| Query | A question in SQL, e.g. "total sales in region 7 since 26 Sept". |
| Sequential scan (Seq Scan) | Reading every row of a table. Slow on 50M rows. |
| Index | A separate sorted list of (column values, row pointer) that lets Postgres jump to matching rows. |
| Composite index | An index on several columns together, e.g. `(region_id, transaction_date)`. Put `=` columns first. |
| B-tree | Postgres's default index type: a tree-shaped sorted list, reached in 3–4 hops. |
| Write cost | Every new sale must also be added to each index, so more indexes mean slower inserts. |
| Partitioning | Splitting one big table into pieces, e.g. one per month, so a March query reads only March. |
| Sharding | Splitting a table across separate servers. Advice only in this project. |
| DBA | Database administrator: the person who finds and applies these fixes today. |
| Planner | The part of Postgres that decides how to run a query. |
| Plan tree | The planner's steps as a tree. Data flows from table-reading nodes at the bottom up to the root. |
| Node | One step in the plan tree, e.g. "Seq Scan on sales" or "Aggregate (SUM)". |
| Bottleneck | The node that takes most of the time, e.g. the Seq Scan's 39.8 of 40 seconds. |
| EXPLAIN | Shows the plan *without running* the query. All numbers are guesses. |
| EXPLAIN ANALYZE | Runs the query and adds real row counts and times beside the guesses. |
| pg\_stat\_statements | Postgres's built-in log of query shapes with how often and how slowly they ran. Values are replaced by `$1`. |
| auto\_explain | A Postgres setting that logs the plan of any query slower than a threshold. |
| pg\_stats | Postgres's notes about the data, e.g. "region has 12 distinct values". Some fields contain real values. |
| Metadata | Facts about the data, never the data: row counts, distinct counts, query shapes. |
| Hash | A one-way scramble: `sales` becomes `t_7a3f`. You cannot get the name back from the code. |
| HMAC | A hash mixed with a secret key, so nobody can guess names by hashing common words like "email". |
| Lookup vault | QuickMart's private table mapping `t_7a3f` back to `sales`. Never leaves QuickMart. |
| Bitmask | A row of yes/no flags packed into bits, e.g. "is a date, is filtered with =, has no index". |
| Literal | A real value inside a query or plan, e.g. `7` or `'2026-09-26'`. Must be stripped. |
| Trust boundary | The line between QuickMart's private side (raw data allowed) and the AI side (metadata only). |
| FP-Growth / Apriori | Data mining algorithms that find items appearing together often, like bread and butter in shopping baskets. |
| Support | How often an item set appears, e.g. region and date filtered together in 40% of slow queries. |
| Neural network | A function with adjustable weights that learns patterns from examples. |
| GNN | Graph neural network: a neural network that works on connected things, like plan-tree nodes. |
| Message passing | Each node updates its description from its children's, so after 2–3 rounds it knows its whole subtree. |
| Learned cost model | A model that predicts real runtime from an estimated plan. Our GNN's job. |
| q-error | How many times off a prediction is. 1 is perfect; 2 means off by a factor of two either way. |
| XGBoost | A fast, strong non-neural model, used as our baseline to beat. |
| RL | Reinforcement learning: an agent tries actions, gets rewards, and learns which actions pay off. |
| Agent / state / action / reward | Tuner / current indexes and workload / add or drop one index / speedup minus write and storage penalties. |
| Multi-armed bandit | The simplest RL: a row of slot machines (candidate fixes), learning which pays best. |
| Exploration vs. exploitation | Mostly picking the best-known option, sometimes trying others in case they are better. |
| LLM | Large language model, like GPT or Gemini. Used as-is, never trained by us. |
| Tool calling | The LLM calls our functions, e.g. `get_plan()` or `simulate()`, and reads their results. |
| RAG | Retrieval-augmented generation: feeding the LLM reference material, e.g. known rewrite rules. |
| Query rewrite | Changing SQL to run faster while returning exactly the same answer. |
| HypoPG | Postgres extension that answers "what would the plan cost if this index existed?" without building it. |
| Statistical twin | A copy of QuickMart's schema filled with fake rows that match its statistics. Safe to test on. |
| Twin fidelity | How closely speedups on the twin match speedups on the real data. |
| Equivalence check | Proving a rewritten query returns the same answers as the original. |
| VeriEQL | An open-source tool that checks query equivalence up to a size bound. |
| Checksum | A fingerprint of a result set. Same checksum means same rows. |
| Canary token | A fake value like `CANARY_7731@corp.com` planted in the data. If it ever reaches the AI, privacy failed. |
| Workload drift | The mix of queries changing over time, e.g. new reports appearing. |
| DSB | Microsoft's benchmark database and queries, used to generate our realistic workload. |
| CREATE INDEX CONCURRENTLY | Builds an index without locking the table, so production keeps running. |
| SHA-256 | The hash function the gateway uses. Unlike SHA-1, nobody can deliberately craft two inputs with the same code. |
| Dictionary attack | Guessing hidden names by hashing likely ones (sales, orders, email) and comparing codes. HMAC blocks it. |
| Secret key | A long random string that HMAC mixes in. It lives only in QuickMart's gateway. |
| Collision | Two different names getting the same code. Deliberate collisions break SHA-1; accidental ones come from shortening codes. |
| Birthday paradox | With 23 people, two probably share a birthday. Likewise, 300 names squeezed into 65,536 short codes probably collide. |
| ANALYZE | The Postgres command that refreshes its statistics, fixing badly wrong row estimates. |
| Query template | All queries that differ only in their values, e.g. Q1 for region 7 and for region 3. Postgres labels each with a queryid. |
| Jensen–Shannon distance | A 0-to-1 score of how different two distributions are. 0 means the query mix is unchanged; 1 means completely different. |
| GAT | Graph attention network: a GNN layer where each node learns how much to listen to each neighbour. |
| Docker Compose | One file that starts all our services together, each in its own container, with its own network access. |
| JSON Schema | A formal description of a JSON object's fields, used to test that every hand-off matches its contract. |
| Non-sargable condition | A filter that wraps a column in a function, like date\_trunc, so no index on that column can be used. Q2's rewrite fixes one. |

## Architecture at a glance

Everything that touches raw data stays inside QuickMart; the four AI components sit on the other side of a trust boundary and see only hashed metadata.

&#91;embedded content: Blind Tuner architecture · 8 components, 1 trust boundary\]

The gateway is the only door out, and it lets through only disguised metadata. Fixes come back up to be tested in the sandbox, and answers are translated back into real names before the DBA reads them.

**End-to-end flow, using QuickMart**

1. Postgres logs the 40-second dashboard query and its plan.
2. The gateway hashes it to `t_7a3f`, `c_19c2`, `c_88b1` and strips the values.
3. The miner proposes `(c_19c2, c_88b1)` among about 30 candidates.
4. The RL agent tries combinations; HypoPG builds hypothetical plans and the GNN predicts their real runtime.
5. The best configuration is measured on the twin: 40 s down to about 0.2 s, plus its insert cost.
6. The LLM agent explains the result in hashed names, citing the tools' numbers.
7. The gateway translates the answer back: `(region_id, transaction_date)`.
8. The DBA approves, and the dashboard generates the migration and rollback scripts.

**The trust boundary** is the line between QuickMart's private side, where raw data is allowed, and the AI zone, where only metadata is. The gateway, twin and dashboard run inside QuickMart; nothing in the AI zone ever holds a real name or value.

## Demo database: QuickMart

QuickMart is our own retail schema and the demo's "production" database; DSB and TPC-H only supply extra training plans. Using a custom schema keeps the adversarial leak test honest, because public benchmark schemas are famous enough for an AI to recognise.

**Tables**

| Table | Columns | Rows | Sensitive columns |
| --- | --- | --- | --- |
| `regions` | region\_id (PK), region\_name | 12 | — |
| `stores` | store\_id (PK), region\_id (FK), city, opened\_on | 500 | — |
| `customers` | customer\_id (PK), email, full\_name, phone, city, signup\_date, segment | 2M | email, full\_name, phone |
| `products` | product\_id (PK), name, category, brand, unit\_price | 50k | — |
| `sales` | order\_id (PK), customer\_id (FK), product\_id (FK), store\_id (FK), region\_id (FK), transaction\_date, quantity, amount, payment\_method | 50M (fallback 10M) | amount (revenue) |
| `returns` | return\_id (PK), order\_id (FK), return\_date, reason | 2M | — |

**Data generation rules** (Agent 1)

1. Generate parents before children: regions, stores, products, customers, then sales, then returns.
2. Skew on purpose, so indexes matter: region 7 holds 30% of sales; 20% of products earn 80% of revenue; dates run 2024-01-01 to 2026-09-30, denser in recent months.
3. Correlate on purpose, so the twin is tested: each store's sales carry that store's region\_id; returns follow their sale's date by 1–30 days.
4. Create only primary keys and foreign keys at first. No other indexes, so the slow queries are genuinely slow.
5. Load with `COPY`, then run `ANALYZE` so `pg_stats` is filled.

**Canary placement** (Agent 2, about 20 in total)

- 5 customer emails such as `CANARY_7731@corp.com`, plus 3 names and 2 phone numbers.
- 3 distinctive sale amounts such as `7731.77`, and 2 product names.
- 2 query comments containing a canary, and 2 queries filtering on a canary value.
- 1 canary inside the DBA's chat question.

**Demo queries**

Q1, the hero query: needs a composite index.

```sql
SELECT SUM(amount) FROM sales
WHERE region_id = 7 AND transaction_date >= '2026-09-26';
```

Q2, the join query: needs a rewrite plus an index. Wrapping the date column in `date_trunc` stops Postgres from using any index on it.

```sql
SELECT p.category, SUM(s.amount)
FROM sales s
JOIN products p ON p.product_id = s.product_id
JOIN stores st ON st.store_id = s.store_id
WHERE st.region_id = 7
  AND date_trunc('month', s.transaction_date) = '2026-09-01'
GROUP BY p.category;
```

The expected rewrite replaces the `date_trunc` line with `s.transaction_date >= '2026-09-01' AND s.transaction_date < '2026-10-01'`.

Q3, the partition query: a monthly report that reads one month of `sales`, which monthly partitioning speeds up.

Q4, the drift query: a new report on customer segment plus date, introduced mid-demo so the RL agent must adapt.

**Write workload.** A `pgbench` script inserts sales rows at a steady rate (starting value 200 per second) so write cost is measured, not guessed.

## Threat model

We guarantee that no raw value or real name crosses the trust boundary; we do not claim that zero information crosses. This section is what we say when a judge asks "is it really zero exposure?"

**Who we defend against**

- The AI provider, who stores or reads everything sent to its model.
- Anyone who later obtains the AI's logs or the payload ledger.
- The model itself, if it tries to infer real names from what it sees.

**What the AI sees, never sees, and what still leaks**

| Category | Examples | Status |
| --- | --- | --- |
| Raw values | Customer emails, amounts, dates, filter values | Never sent; stripped and canary-checked |
| Real names | `sales`, `customers`, `email` | Never sent; HMAC codes only |
| `pg_stats` value lists | Most common values, histogram bounds | Never sent; replaced by a skew score |
| Query shape | Which column uses `=`, joins, grouping | Sent: the fix depends on it |
| Sizes | Row counts, index sizes | Sent, rounded to 2 significant figures |
| Column roles | "date", "foreign key", "measure" | Sent as role tags |
| Workload rhythm | How often each template runs | Sent, as weights |
| Schema shape | How many tables, how they link | Leaks; can hint at the kind of business |

**Mitigations for what still leaks**

1. Round all counts and sizes.
2. Run the adversarial leak test and publish its score.
3. Offer air-gapped mode, where even metadata never leaves the building.

**Out of scope**

- A compromised gateway machine: whoever controls it already holds the raw data.
- Insiders at QuickMart with database access.

## Component 1: Obfuscation gateway

The gateway runs inside QuickMart and turns logs, plans and statistics into disguised metadata. It is plain code, not AI, and it is the only thing that touches raw data.

**How it works**

1. Read slow query shapes from `pg_stat_statements`, where values are already `$1`.
2. Parse each query with `sqlglot` and rename every table and column with HMAC-SHA256: `sales.region_id` becomes `t_7a3f.c_19c2`. Strip literals and comments. Keep at least 8 hex characters per code; the 4-character codes in this doc are shortened for readability.
3. Read plans from `auto_explain`. Keep node types, estimated rows, actual rows and times. Hash names and strip literals from filter lines.
4. Read `pg_stats`. Keep distinct counts and null fractions. Drop `most_common_vals` and `histogram_bounds`, which contain real values, and send only a skew score.
5. Attach a bitmask and a role tag to each column: type class (date, number, text, id), primary key, foreign key, indexed, used in joins, used in ranges.
6. Round row counts to two significant figures, e.g. 49,812,334 becomes 50M.
7. Log every outgoing payload and scan it for canary tokens before it leaves.

**Unique points**

- Spots the `pg_stats` leak that most "metadata-only" designs miss.
- HMAC instead of a plain hash, which blocks dictionary guessing.
- Role tags give the AI meaning ("this is a date") without names.
- A payload ledger: an exportable record of every byte the AI received.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| Real values leak through plans | `auto_explain` prints filters like `city = 'Raipur'`; comments and CTE strings leak too | Strip with the `sqlglot` parse tree, not regex; run the canary scan from hour 1 |
| The AI reasons worse on hashes | Names like `order_date` carry meaning the AI relies on | Role tags in the bitmask; measure hashed vs. plaintext quality and show the gap |
| "Zero exposure" gets challenged | Table sizes and join shapes still reveal something about a business | Claim "zero raw data", show a threat-model slide, round counts |
| One name hashes two ways | Plans use aliases like `s` for `sales` | Resolve aliases to real names before hashing; one shared hashing function |
| `sqlglot` cannot parse a query | Rare Postgres-only syntax | Fail closed: log it as "unparsed, not sent" instead of sending it raw |
| Rounded counts hurt GNN accuracy | Coarser numbers carry less signal | Round to two significant figures, not wide buckets; report the accuracy cost |
| Outsiders guess names (dictionary attack) | Plain SHA-256 is public, so anyone can hash "sales" and compare codes | HMAC with a secret key: guesses cannot be checked without the key |
| Two names get the same code | 4 hex characters leave only 65,536 codes, so 300 names collide about half the time (birthday paradox) | Keep at least 8 characters: about 4.3 billion codes, roughly a 1-in-100,000 chance |
| The HMAC key leaks | Key committed to the repo, printed or logged by an agent | Store it as a secret in the gateway's environment; every AGENTS.md forbids committing, printing or logging it |

*Fail closed* means: when unsure, send nothing.

## Component 2: Pattern miner (FP-Growth)

The miner turns the hashed slow-query log into about 30 candidate indexes for the RL agent. It is a data mining algorithm, so it needs no training and runs in seconds.

**How it works**

1. Treat each hashed query as a shopping basket. Its items are column-plus-role pairs, e.g. `c_19c2:EQ` (filtered with `=`) and `c_88b1:RANGE` (filtered with `>=`).
2. Weight each basket by total time (runs × average seconds), so one 40-second query outweighs a hundred 1 ms queries.
3. Run FP-Growth (`mlxtend`) to find column sets that appear together often. QuickMart: `{c_19c2:EQ, c_88b1:RANGE}` appears in 40% of slow time.
4. Turn each frequent set on one table into a candidate index: `=` columns first, then range columns, then `ORDER BY` columns, at most three columns.
5. Drop candidates already covered by an existing index. An index on `(a, b)` already covers `(a)`.
6. Cluster queries into templates and track how often each template runs per hour. A shift in that mix is workload drift and triggers re-tuning.

**Unique points**

- Produces composite candidates, which Supabase's open-source `index_advisor` cannot (single-column only).
- Every candidate carries evidence: "appears in 40% of slow query time".
- Shrinks the RL agent's choices from thousands of possible indexes to about 30.
- Applies the team's data mining coursework directly.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| Too many candidates | Column combinations grow fast | Minimum support threshold, at most 3 columns, keep the top 30 |
| Frequent does not mean useful | A yes/no column filters almost nothing | Skip columns with very few distinct values in the leading position; HypoPG and the GNN judge the rest |
| Cheap frequent queries dominate | Plain counts reward quick queries | Weight baskets by total time, not count |
| Judges call Apriori trivial | It is a classic algorithm | Frame it as candidate generation for RL and show the action space shrinking |
| Drift false alarms | Normal hour-to-hour noise | Trigger only when the shift lasts two windows in a row |

## Component 3: Plan GNN

The GNN predicts a query's real runtime, node by node, from an estimated plan, before anything runs. Its per-node predictions are also the "GNN-generated reason" that PS4 requires.

**Why it is needed.** HypoPG only gives *estimated* plans for indexes that do not exist yet, and Postgres's estimates are often badly wrong. The GNN corrects them, so the RL agent can rank fixes accurately without building anything.

**How it works**

1. Input: one estimated plan tree from `EXPLAIN`, as a graph. Each node's features: operator type, estimated rows (log scale), estimated cost, row width, and the role bits of the columns it touches. No names are needed, so it fits the privacy design naturally.
2. Model: a 3-layer graph network (GAT or GCN in PyTorch Geometric), hidden size 64–128, about 100k weights.
3. Output: each node's own time (time minus its children's time) and the total runtime.
4. Labels: real per-node times from `EXPLAIN ANALYZE` runs on the training workload.
5. Training: about 10,000 plans, split by query template, about 15 minutes per run on a Colab T4.
6. Use A: score HypoPG's hypothetical plans, giving the RL agent its reward.
7. Use B: explanations, e.g. "Node 4 is predicted to take 82% of the time. Postgres expected 200 rows here; we predict 80,000." When the gap is 100× or more, the dashboard also recommends running ANALYZE, which refreshes Postgres's statistics.

Optional shortcut: start from the pretrained zero-shot cost model (Hilprecht & Binnig, VLDB 2022) and fine-tune it on our plans.

**Unique points**

- The GNN has a real job: correcting Postgres's own estimates, measured against them.
- One model serves two PS requirements: cost prediction for RL and the GNN-generated reason.
- Honest evaluation: unseen-template q-error, 95th-percentile error, and an XGBoost baseline.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| A judge asks "why a GNN if `EXPLAIN ANALYZE` shows the bottleneck?" | `EXPLAIN ANALYZE` must run the query first | Answer: the GNN predicts for plans that have never run, like hypothetical indexes |
| It does not beat XGBoost | Small data, strong baseline | Report it honestly; use the better one for rewards; keep the GNN for node-level explanations, which XGBoost cannot give |
| It memorises the training queries | Few distinct query shapes | Split by template, deduplicate plans, add a second database |
| Rare predictions are wildly off | Tail errors are common in learned cost models | Report the 95th percentile; use the GNN only to rank; final speedups come from the twin |
| Noisy labels | Cold cache on first runs | Run each query twice, keep the second |
| Timed-out queries | 10-second statement timeout | Label them "at least 10 s" instead of dropping them |
| PyTorch Geometric will not install on Colab | Version mismatches | Pin versions on day 0; fallback: hand-written message passing in plain PyTorch (plans are tiny trees) |

## Component 4: RL agent

The RL agent chooses the best *combination* of fixes under a write and storage budget, and keeps adapting when the workload drifts. PS4 assigns index, partitioning and SQL-rewrite decisions to this engine.

**How it works**

1. Actions: add one candidate index from the miner, drop an unused index, pick a partition key for a big table, or apply one rewrite rule to one query.
2. State: the current set of indexes plus how often each query template runs.
3. Reward: workload time saved (predicted by the GNN on HypoPG plans), minus a write-cost penalty, minus a storage penalty. HypoPG estimates each index's size.
4. Algorithm: tabular Q-learning with epsilon-greedy exploration. An episode builds a configuration of up to 5 actions, and a few hundred episodes take seconds.
5. Rewrite actions come from a fixed rule library (R-Bot's rules), and only rules that match a query's shape are offered.
6. Partition actions are scored on the twin only, for at most two candidate keys, after the index search.
7. On drift, learning continues with the new template weights instead of restarting.

*Q-learning* keeps a score for each (state, action) pair and updates it after every reward. *Epsilon-greedy* picks the best-scored action most of the time and a random one, say 10% of the time.

**Unique points**

- Handles index interactions: two overlapping indexes are worth less than the sum of their parts.
- Budget-aware: it trades speed against write cost and storage, not speed alone.
- Adapts live to drift, which covers PS4's "unseen, evolving patterns" requirement.
- Rewrites through rule selection, matching PS4's deliverable wording.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| "Why not a simple greedy loop?" | With few candidates, greedy can find the same answer | Show RL vs. greedy on overlapping indexes and on drift; if they tie, say so and stress adaptation |
| The agent exploits GNN mistakes | It finds configs the GNN wrongly rates as great | Verify the top 3 configs with HypoPG cost and twin runs; penalise disagreement |
| Write cost is guessed during search | Real write cost needs real inserts | Use a simple per-index penalty in search; measure the final choice on the twin |
| Too many rewrite actions | Every rule on every query | Offer only rules that match the query's shape |
| Search feels slow | Repeated HypoPG calls | Cache costs per configuration; identical configs are never re-costed |
| Partitioning cannot be hypothesised | HypoPG covers indexes only | Score partition keys on the twin, after the index search |

## Component 5: LLM agent

The LLM agent is the DBA's conversational interface. It calls our tools, then turns their evidence into plain-English answers. It never sees raw data, and we never train it.

**How it works**

1. The DBA asks: "Why is the weekly sales dashboard timing out?" That question itself contains real names, so a local resolver inside QuickMart maps it to query template `q_12` first. The LLM receives only `q_12`.
2. The LLM calls tools: `get_slow_templates`, `get_plan`, `gnn_explain`, `mine_candidates`, `run_rl`, `simulate`, `rewrite_candidates`, `verify`.
3. RAG supplies R-Bot's rewrite rule library (67 verified rule specs and 2,091 rewrite Q&As), so rewrites follow known-safe patterns.
4. The answer is written in hashed names, then translated back to real names inside QuickMart before the DBA sees it.
5. Model: any API model with tool calling, or a local model through Ollama for air-gapped mode.

**LLM providers** (added 2026-10-03)

The agent talks to its model through one provider adapter (`agent/llm.py`). Every provider has the same `generate()` contract, so the tool loop, the number checker and the payload ledger do not change with the model. Switching provider is one value, `llm.provider` in `config.yaml`. When the provider fails, `llm.fallback` names the providers tried next, in order (see Fallback below).

| Provider | API | Model | Key | Notes |
| --- | --- | --- | --- | --- |
| `gemini` | Gemini REST `generateContent` with function declarations | `llm.model` | `GEMINI_API_KEY` | Default |
| `nim` | NVIDIA NIM, OpenAI-compatible `POST {base_url}/chat/completions` with `tools` and `tool_choice: auto`; `base_url` is `https://integrate.api.nvidia.com/v1` | `llm.nim.model`, chosen by `make llm-bench` | `NVIDIA_API_KEY` | Tool results go back as `role: tool` messages with the call's `tool_call_id` |
| `openai` | OpenAI chat completions, same adapter as `nim`; `base_url` is `https://api.openai.com/v1`; the token cap is sent as `max_completion_tokens` | `llm.openai.model` (PENDING) | `OPENAI_API_KEY` | Not yet run live |
| `ollama` | Local Ollama `POST /api/chat`, JSON-constrained replies | `llm.ollama.model` | none | Air-gapped mode only |

For every hosted provider, each request body is first sent to the gateway's `POST /v1/ledger/outbound`, which scans it for canaries and writes it to the ledger; the body is sent only on verdict allow (fail closed). HTTP 429, 500, 503 and 504 are retried with exponential backoff. The ai container reaches only the hosts in `egress.allowed_hosts` (the Gemini, NIM and OpenAI API hosts) through the egress allowlist proxy. `make llm-bench` chooses the NIM model: it lists `GET {base_url}/models`, probes candidates with one synthetic tool-call request each, runs the Q1 flow on the first few that return a tool call, and records each passing run as a replay fixture.

Fallback (added 2026-10-03): when the provider fails (rate limited after every retry, host unreachable, timeout, an HTTP error such as a revoked key, a malformed reply, or no key or model configured), `/ai/ask` asks the whole question again of the next provider in `llm.provider` then `llm.fallback`. The tool results already computed are reused, and every new request body goes through the outbound scan again. A canary block is never failed over (fail closed). Air-gapped mode and a request that names its provider (the benchmark, the per-provider end-to-end test) are never failed over. Providers are not switched in the middle of a conversation: Gemini 3 checks thought signatures on function calls, which calls made by another model do not carry. An answer the number checker blocks is not an API failure and does not fail over. The reply names the provider that answered and lists each failover.

Example answer (after translation): "The scan on `sales` takes 39.8 of 40 seconds. A composite index on `(region_id, transaction_date)` is predicted to cut it to 0.2 seconds. On the twin it measured 0.19 seconds, with inserts 1.8 ms slower."

**Unique points**

- Even the DBA's question is sanitised before reaching the AI.
- Every number in an answer comes from a tool result, never from the model's own guess.
- Air-gapped mode on the offline Quadro machine: zero bytes leave the building.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| The DBA's question leaks names | People type real names like "sales dashboard" | Local resolver maps questions to template IDs before the LLM |
| The LLM invents numbers | Models like confident round figures like "85%" | A checker rejects any answer containing a number absent from tool results |
| A rewrite changes the query's answer | LLMs write plausible but wrong SQL | Rewrites only through library rules, always verified, never auto-applied |
| Slow or dead wifi on stage | Venue networks fail | Cache the hero query's full run; local model as backup |
| The agent loops on tool calls | Unclear tool results | Cap at 8 tool calls per question; return what it has |
| A local 7B model calls tools badly | Small models are weaker at tool use | Keep the tool list short; scripted fallback for the hero query |

## Component 6: Simulation sandbox (HypoPG and the twin)

The sandbox tests every fix without touching QuickMart's real database. It has two tools: HypoPG for instant what-if estimates, and the statistical twin for real measurements.

**What the twin is.** The twin is a second Postgres database with exactly QuickMart's tables and columns, but every row is fake. The fake rows are generated to match QuickMart's statistics:

- Same row counts (or a fixed fraction, e.g. 20%).
- Same distinct counts: 12 regions, not 11 or 13.
- Same skew: if region 7 has 30% of real sales, it has 30% of fake sales.
- Same null fractions and the same links between tables.
- Fake values: `user48213@example.com`, random amounts in the real range.

Because it is shaped like the real data, Postgres plans and runs queries on it much the same way. So we can build real indexes there, run real inserts and measure real numbers, with zero customer data involved.

**How it works**

1. HypoPG, for every candidate during the RL search: create a hypothetical index, run `EXPLAIN`, send the estimated plan to the GNN. This takes milliseconds and builds nothing.
2. Build the twin once: copy the table definitions with `pg_dump --schema-only` (definitions, no rows), then generate fake rows with a Python generator and load them with `COPY`.
3. Test the RL agent's final choice on the twin: build the real indexes or partitions, replay the query workload, and measure latency before and after (median of 5 runs).
4. Measure write cost with `pgbench` (Postgres's built-in load tester) running an insert script, and measure each index's size on disk.
5. Report twin fidelity: our demo's "production" is benchmark data, so we can also measure the real speedup once and show how close the twin's prediction was.

**Unique points**

- Write-latency and storage costs are measured, not guessed.
- Twin fidelity is reported openly; almost no team will measure it.
- Builds on published research: a 2011 UMass paper proposed synthetic databases for outsourced tuning. We cite it.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| Twin plans differ from real plans | Per-column statistics lose links between columns, e.g. region and date moving together | Preserve correlation for column pairs the miner flagged; report plan agreement and fidelity |
| A scaled-down twin picks different plans | Small tables tempt Postgres into full scans | Keep the hero table at full scale, or check plan shape matches before trusting a number |
| Twin build is slow | Generating 50M rows takes time | Build it before the demo; scale other tables to 20%; load with `COPY`, not `INSERT` |
| Hypothetical indexes vanish | HypoPG indexes live only in one connection | Create and `EXPLAIN` on the same connection |
| Noisy timings | Cache and background load | Warm runs, median of 5, same machine for before and after |
| Partitioning cannot be hypothesised | HypoPG covers indexes only | Test partitioning on the twin only, at most two keys |

## Component 7: Verification and privacy proof

This component turns three claims into evidence: the rewritten query is correct, the speedup is real, and no raw data reached the AI.

**Proof 1: correctness of rewrites**

1. Run VeriEQL on the original and rewritten query. It checks they return the same answers on every database up to a size bound.
2. Run both queries on the twin and compare result checksums.
3. Label every rewrite in the dashboard: **Verified** (both pass), **Tested only** (checksum passes, VeriEQL cannot handle the SQL), or **Rejected**.

**Proof 2: the speedup**

Every speedup shown comes from a twin measurement (Component 6), never from a prediction or the LLM.

**Proof 3: privacy**

1. **Canary tokens.** Plant fake values in about 20 places: rows (`CANARY_7731@corp.com`), a query comment, a filter value, a number like `7731.77`. The gateway scans every outgoing payload for them. The dashboard shows "2,140 payloads sent, 0 canaries found".
2. **Negative control.** Switch the gateway off for one run and show the counter light up. This proves the detector works, so the zero means something.
3. **Adversarial leak test.** Give a second LLM everything our AI received and ask it to guess the real table names, column names and any values. Score its guesses, and compare with a plaintext control.
4. **Payload ledger.** Export every payload with its scan result as an audit file.

**Unique points**

- Privacy is demonstrated live, with a control, not claimed on a slide.
- The adversarial leak test is novel and quick to build.
- Rewrites carry an honest status instead of a blanket "correct".

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| VeriEQL rejects some queries | It does not support every SQL feature | "Tested only" label plus human review; never hide these cases |
| Checksums match on fake data but not real edge cases | The twin may lack NULLs or extreme values | Generate NULLs and edge values in the twin; state the bound honestly |
| Canaries slip through in another form | The scanner looks for exact strings | Plant canaries in several forms; scan case-insensitively and for fragments |
| The adversarial LLM recognises the schema | DSB and TPC-H schemas are public and famous | Run the adversarial test on our own custom QuickMart schema; say so openly |
| "0 canaries" impresses nobody | A zero can mean the detector is broken | Show the negative control first |

## Component 8: Dashboard and demo flow

The dashboard is where the DBA asks questions, sees evidence and approves changes. Every panel maps to a PS4 deliverable.

**Panels**

- Chat box for natural-language questions.
- Slow query list, ranked by total time.
- Plan tree with GNN heat colouring on each node.
- A "What the AI sees / What the DBA sees" toggle.
- Candidate indexes with their mining support.
- The RL agent's chosen configuration, with each action's contribution.
- Twin results: latency before and after, write cost in ms, storage in MB.
- Rewrite status: Verified, Tested only, or Rejected.
- Privacy panel: canary counter, negative-control button, ledger export.
- Approve button: generates a migration script using `CREATE INDEX CONCURRENTLY`, a rollback script, and a post-deploy check that reverts if latency worsens.

**Demo flow (about 6 minutes)**

1. The weekly sales dashboard query takes 40 seconds and times out.
2. Ask: "Why is the weekly sales dashboard timing out?"
3. Flip the toggle: the AI saw only `t_7a3f`, `c_19c2` and `?`.
4. The GNN heat map marks the Seq Scan as 99% of the time.
5. The miner and RL agent recommend the composite index plus one rewrite, each with its contribution.
6. The twin measures 40 s down to about 0.2 s, with a small insert cost.
7. The rewrite shows **Verified**.
8. Privacy: run the negative control, then show 0 canaries and the adversarial test score.
9. Drift: switch the workload mix and watch the RL agent adapt.
10. Approve: the migration and rollback scripts appear.

**Failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| Too much to show in 6 minutes | Ten panels, one pitch slot | Rehearse a fixed script three times; skip panels judges did not ask about |
| Streamlit feels slow | It reruns the whole script on each click | Cache results with `st.cache_data`; precompute the hero query |
| Plan trees are hard to draw | Streamlit has no tree widget | Render with Graphviz via `st.graphviz_chart` |
| The live demo crashes | Many moving parts | Freeze a golden path by hour 18; record a backup video |

## Repository layout and environment

One repo, one folder per owner, one Docker Compose file that every agent and human runs. An agent edits only its own folders.

```text
blind-tuner/
  contracts/      JSON Schemas + contract tests        (humans, frozen at hour 0)
  infra/          docker-compose, Dockerfiles, Postgres config   (Agent 1)
  db/             QuickMart schema and generator, DSB/TPC-H loaders,
                  plan generation, twin builder, pgbench scripts (Agent 1)
  gateway/        hashing, literal stripping, stats, canaries,
                  payload ledger, question resolver, de-hashing  (Agent 2)
  miner/          FP-Growth, template clustering, drift          (Agent 2)
  privacy_tests/  adversarial leak test, negative control        (Agent 2)
  models/gnn/     plan-to-graph, GNN, XGBoost, training scripts  (Agent 3)
  rl/             Q-learning agent                               (Agent 3)
  agent/          LLM tools, RAG over R-Bot rules, number checker (Agent 4)
  verify/         VeriEQL wrapper, checksum comparison           (Agent 4)
  dashboard/      Streamlit app                                  (Agent 4)
  e2e/            scenario tests, demo script                    (humans)
  docs/           this doc, exported as markdown
```

**Docker Compose services**

| Service | Contents | Network |
| --- | --- | --- |
| `pg-prod` | Postgres 16 with QuickMart, `pg_stat_statements`, `auto_explain`, HypoPG | private |
| `pg-twin` | Postgres 16 with the statistical twin, HypoPG | private |
| `gateway` | Gateway API, ledger, HMAC key | private + boundary |
| `ai` | Miner, GNN, RL, LLM agent, verification | boundary only |
| `dashboard` | Streamlit | private + boundary |

**Environment rules**

1. Postgres 16 and Python 3.11 everywhere. Pin every Python package in a lockfile on day 0, and test the image on the Quadro before the event.
2. The HMAC key lives only in the gateway's environment file, which is never committed.
3. Each agent works on its own git branch; humans merge at gates after reviewing test diffs.
4. Each folder has a `AGENTS.md` with the agent rules from the build plan, plus a `NOTES.md` recording decisions.
5. This doc is exported to `docs/architecture.md` and is the single source of truth. If the code and this doc disagree, ask a human.

## Interface contracts

Every hand-off between components is one of these JSON objects, defined as a JSON Schema in `contracts/` and frozen at hour 0. Anything crossing the trust boundary uses hashed codes only: `t_` tables, `c_` columns, `i_` indexes, `q_` templates, each with 8 hex characters.

| Contract | Producer → consumer | Key fields |
| --- | --- | --- |
| `HashedQuery` | Gateway → miner, LLM | `template_id`, `sql` (hashed, `?` for values), `calls`, `mean_ms`, `total_ms`, `columns[]` of `{table, col, role}` with role = EQ, RANGE, JOIN, GROUP, ORDER or SELECT |
| `HashedPlan` | Gateway → GNN, LLM | `plan_id`, `template_id`, `setup_id`, `source` (auto\_explain, explain or hypopg), `nodes[]` |
| `ColumnMeta` | Gateway → miner, GNN, LLM | `table`, `col`, `type_class` (date, number, text, id), `bits` (pk, fk, indexed, nullable, join, range, eq), `n_distinct` (rounded), `null_frac`, `skew` |
| `TableMeta` | Gateway → RL | `table`, `rows` (rounded), `size_mb` (rounded), `writes_per_s` |
| `Candidate` | Miner → RL | `cand_id`, `table`, `columns[]` in index order, `support`, `evidence` |
| `Config` | RL → sandbox | `config_id`, `actions[]` of add\_index, drop\_index, partition or rewrite |
| `Prediction` | GNN → RL, LLM | `plan_id`, `total_ms`, `nodes[]` of `{node_id, self_ms, share}` |
| `SimResult` | Sandbox → RL, LLM, dashboard | `config_id`, `source` (hypopg or twin), per-template `before_ms` and `after_ms`, `write_ms_delta`, `storage_mb_delta`, `runs` |
| `Rewrite` | Rewriter → verifier, dashboard | `rewrite_id`, `template_id`, `rule_id`, `sql` (hashed), `status` (Verified, TestedOnly, Rejected), `checks` |
| `LedgerEntry` | Gateway → privacy panel | `payload_id`, `time`, `destination`, `bytes`, `sha256`, `canary_hits[]` |
| `Answer` | LLM → gateway → dashboard | `question_id`, `text` (hashed), `numbers[]` of `{value, tool_call_id}`; real names added only inside QuickMart |

**Example: `HashedPlan` for Q1 before the index**

```json
{
  "plan_id": "p_000412",
  "template_id": "q_5c1e09ab",
  "setup_id": "s_baseline",
  "source": "auto_explain",
  "nodes": [
    {"node_id": 0, "parent_id": null, "op": "Aggregate",
     "est_rows": 1, "est_cost": 1250000, "width": 32,
     "actual_rows": 1, "self_ms": 10},
    {"node_id": 1, "parent_id": 0, "op": "Seq Scan",
     "relation": "t_7a3f91c2", "filter_cols": ["c_19c2d04e", "c_88b1a7f3"],
     "est_rows": 18000, "est_cost": 1240000, "width": 8,
     "actual_rows": 20000, "rows_removed": 50000000, "self_ms": 39800}
  ]
}
```

Rules: `actual_rows`, `rows_removed` and `self_ms` are present only for plans that ran; HypoPG plans carry estimates only. No field may ever hold a raw value or a real name.

## Services, APIs and network isolation

The trust boundary is enforced by Docker networking, not just by convention: the `ai` container has no route to either Postgres, so it can only see what the gateway's API returns.

**Networks**

- `private`: `pg-prod`, `pg-twin`, `gateway`, `dashboard`. No internet access.
- `boundary`: `gateway`, `ai`, `dashboard`, plus an optional `ollama` service for air-gapped mode.
- Only `ai` may reach the internet, and only to the LLM API. In air-gapped mode it has no internet access at all.

This gives the pitch a strong line: the AI cannot leak the data, because it cannot even connect to the database.

**Gateway API** (private side; every response is a hashed contract)

| Endpoint | Input → output | Called by |
| --- | --- | --- |
| `GET /v1/templates/slow` | → `HashedQuery[]` ranked by total time | ai |
| `GET /v1/templates/{id}/plans` | → `HashedPlan[]` | ai |
| `GET /v1/meta/columns`, `GET /v1/meta/tables` | → `ColumnMeta[]`, `TableMeta[]` | ai |
| `POST /v1/simulate/hypopg` | `Config` → estimated `HashedPlan[]` (runs `EXPLAIN` with hypothetical indexes on `pg-prod`) | ai (RL) |
| `POST /v1/simulate/twin` | `Config` → `SimResult` measured on `pg-twin` | ai (RL), dashboard |
| `POST /v1/twin/checksum` | original + rewritten hashed SQL → match or mismatch | ai (verify) |
| `POST /v1/ask/resolve` | DBA's question → `question_id` + template IDs | dashboard |
| `POST /v1/answers/dehash` | `Answer` → text with real names | dashboard |
| `GET /v1/ledger` | → `LedgerEntry[]` | dashboard |
| `POST /v1/privacy/negative-control` | → canary hits from an unfiltered payload sent to a local scanner only, never to any model | dashboard |
| `POST /v1/approve` | `config_id` → `migration.sql`, `rollback.sql`, post-deploy check | dashboard |

**AI service API** (boundary side; hashed data only)

| Endpoint | Input → output |
| --- | --- |
| `POST /ai/mine` | → `Candidate[]` and the current drift state |
| `POST /ai/gnn/predict` | `HashedPlan[]` → `Prediction[]` |
| `POST /ai/rl/run` | template weights → best `Config` with each action's contribution |
| `POST /ai/rewrite/candidates` | `template_id` → `Rewrite[]` from matching rules |
| `POST /ai/verify/equivalence` | `Rewrite` → VeriEQL result on hashed SQL and hashed schema |
| `POST /ai/ask` | `question_id` → `Answer` (hashed) |

Every request from `ai` to the gateway and every LLM call is written to the payload ledger and canary-scanned.

## LLM tools and system rules

The LLM agent has exactly eight tools, each a thin wrapper over one endpoint, and a fixed set of rules in its system prompt.

| Tool | Wraps | Returns |
| --- | --- | --- |
| `get_slow_templates()` | `GET /v1/templates/slow` | Top templates by total time |
| `get_plan(template_id)` | `GET /v1/templates/{id}/plans` | Latest plan with actual times |
| `gnn_explain(plan_id)` | `POST /ai/gnn/predict` | Per-node predicted share and estimate gaps |
| `mine_candidates()` | `POST /ai/mine` | Candidate indexes with support |
| `run_rl(template_ids)` | `POST /ai/rl/run` | Best configuration and each action's contribution |
| `simulate(config_id)` | `POST /v1/simulate/twin` | Measured before/after, write cost, storage |
| `rewrite_candidates(template_id)` | `POST /ai/rewrite/candidates` | Rule-based rewrites |
| `verify(rewrite_id)` | `POST /ai/verify/equivalence` + `POST /v1/twin/checksum` | Verified, TestedOnly or Rejected |

**System rules** (written into the prompt)

1. You see hashed codes only. Never guess, ask for or speculate about real names or values.
2. Every number you write must come from a tool result in this conversation. Tag it with that tool call's ID.
3. Say "predicted" for GNN numbers and "measured" for twin numbers; never mix them up.
4. Propose rewrites only through `rewrite_candidates`, and report each one's verification status.
5. Use at most 8 tool calls per question; if evidence is missing, say what is missing.
6. Answer in this order: the bottleneck, the recommended fix, its measured effect, its cost, and the verification status.
7. Temperature 0.

**Number checker** (Agent 4). Before an answer is shown, a script extracts every number in it and confirms each one appears in a tagged tool result. Any unmatched number blocks the answer and triggers one retry.

**RAG.** The R-Bot rule specifications and rewrite Q&As are indexed locally in the `ai` container. `rewrite_candidates` retrieves the rules whose patterns match the template's shape, so the model never invents a rule.

## Detailed component specs

These are the exact algorithms and formulas each agent implements; the component sections above explain why, this section says precisely what.

**Gateway (Agent 2)**

- Codes: prefix + the first 8 hex characters of HMAC-SHA256(key, name). Tables hash `"table"`; columns hash `"table.column"`, so two `id` columns in different tables get different codes.
- Key: 32 random bytes, generated once per engagement and kept for its whole length. If it must be rotated, re-hash all stored history (logs, plans, miner baskets, training data) with the new key in one batch before anything else runs. Otherwise old and new codes for the same column look like two different columns.
- Literal stripping: parse SQL with `sqlglot` (Postgres dialect), replace every literal node with `?`, and delete comments.
- Plan filters: parse each `Filter`, `Index Cond`, `Recheck Cond`, `Join Filter` and `Hash Cond` string as an expression the same way. If a string will not parse, drop it and mark the node `filter_redacted`.
- Aliases: map each plan alias to its relation name before hashing.
- Skew score: the sum of the top 5 most-common-value frequencies from `pg_stats`, a number from 0 to 1. The values themselves never leave.
- Rounding: every count and size to 2 significant figures.
- Question resolver: match the DBA's words against a local map of dashboard names and real table names to templates; return the top 3 template IDs.

**Miner (Agent 2)**

- Templates: use `pg_stat_statements`' `queryid`, which already groups queries that differ only in values.
- Baskets: one per template, with items like `c_19c2d04e:EQ`, weighted by total time.
- Weighted support: `mlxtend`'s FP-Growth does not take weights, so run it unweighted with a low threshold, then recompute each found item set's support as its share of total time, and keep those at or above the threshold.
- Candidate order: `=` columns first, then range columns, then `ORDER BY` columns; at most 3 columns; no leading column with fewer distinct values than the threshold.
- Drift: per time window, the share of total time held by each template. Compare consecutive windows with Jensen–Shannon distance (0 = identical mix, 1 = completely different); trigger when it stays above the threshold for 2 windows.

**GNN (Agent 3)**

- Graph: one node per plan node, edges from child to parent.
- Node features: operator type (one-hot), log(1 + estimated rows), log(1 + estimated cost), log(1 + width), index-scan flag, number of filter columns, the OR of their role bits, and log(1 + table rows).
- Targets: log(1 + self time in ms) per node; predicted total = sum of nodes.
- Loss: mean squared error on the log targets, which directly optimises the ratio that q-error measures.
- Model: 3 GAT layers, hidden size 128, ReLU, dropout 0.1, and a small per-node output layer.
- Training: Adam, learning rate 0.001, batch 64, up to 150 epochs, early stopping after 15 epochs without validation improvement.
- Split: 70% / 15% / 15% of templates for training, validation and test.
- q-error = the larger of predicted ÷ actual and actual ÷ predicted.
- XGBoost baseline features: counts per operator type plus sums of the log features over the plan.

**RL agent (Agent 3)**

- State: the set of actions chosen so far; Q-values are kept in a dictionary keyed by that set.
- Workload time: the sum over templates of template weight × GNN-predicted total time of its HypoPG plan.
- Reward per step: the fractional drop in workload time, minus λ\_write × added write ms, minus λ\_storage × added MB ÷ storage budget.
- An episode ends after 5 actions or a "stop" action.
- Greedy baseline: keep adding the single best action until nothing improves.
- Final choice: re-score the top 3 configurations with raw HypoPG cost, measure them on the twin, and pick the best measured.

**Twin (Agent 1)**

- The generator runs inside QuickMart and reads `pg_stats` locally, but writes no real values: each most-common value is replaced by a synthetic value of the same type and length, keeping only its frequency.
- Numbers and dates: sampled uniformly inside each histogram bucket, keeping bucket proportions.
- Foreign keys: parent IDs sampled with the real children-per-parent distribution, measured locally.
- Correlations: for column pairs the miner flags, sample the second column from a local bucketed table conditioned on the first.
- NULLs at each column's null fraction; minimum and maximum values included as edge cases.
- Scale: the hero table at full size, other tables at 20%; `ANALYZE` after loading.
- Plan agreement: for Q1 to Q4, the operator sequence on the twin must match production before any twin number is trusted.
- Fidelity: twin speedup ÷ production speedup, reported per query.

**Verification (Agent 4)**

- VeriEQL with a bound of 5 rows per table and a 60-second timeout; unsupported SQL becomes TestedOnly.
- Checksum: an MD5 of the sorted result rows on the twin, for the original and the rewritten query.

**Privacy tests (Agent 2)**

- Canary scanner: case-insensitive search for every canary and for any 6-character fragment of one, on every payload.
- Adversarial test: give a fresh LLM session the full ledger of one run and ask it to name the real table and column behind each code. A script scores exact and synonym matches and compares with random guesses from a list of common names.

**Approve and deploy (Agent 4)**

- `migration.sql`: one `CREATE INDEX CONCURRENTLY` per index; partitioning as documented manual steps; rewrites as a suggested code change.
- `rollback.sql`: `DROP INDEX CONCURRENTLY` for each new index.
- Post-deploy check: replay templates for 10 minutes; if median latency is more than 10% worse, run the rollback.

## Configuration values

Every tunable number lives in one `config.yaml` at the repo root, starting from these values. They are starting points to tune, not results; change them only in that file, never in code.

| Parameter | Starting value | Used by |
| --- | --- | --- |
| HMAC code length | 8 hex characters | Gateway |
| HMAC key size | 32 random bytes | Gateway |
| Count and size rounding | 2 significant figures | Gateway |
| `pg_stat_statements.track` | `all` | Postgres |
| `auto_explain.log_min_duration` | 500 ms | Postgres |
| `auto_explain.log_analyze` | on (production would sample with `auto_explain.sample_rate`) | Postgres |
| `statement_timeout` during plan generation | 10 s | Plan generation |
| Parameter sets per query | 30 | Plan generation |
| Index setups per query | 4–5 | Plan generation |
| Target plan count | about 10,000 (DSB + TPC-H + QuickMart) | Plan generation |
| Early sample size | 200 plans | Plan generation |
| Minimum weighted support | 5% of total query time | Miner |
| Maximum index columns | 3 | Miner |
| Candidates kept | top 30 | Miner |
| Minimum distinct values for a leading column | 3 | Miner |
| Drift window | 1 hour in production; 2 minutes in the demo | Miner |
| Drift threshold | Jensen–Shannon distance above 0.2 for 2 windows | Miner |
| GNN layers / hidden size / dropout | 3 / 128 / 0.1 | GNN |
| Learning rate / batch / max epochs / patience | 0.001 / 64 / 150 / 15 | GNN |
| Template split | 70 / 15 / 15 | GNN, evaluation |
| Q-learning rate α / discount γ | 0.1 / 0.9 | RL |
| Exploration ε | 0.1, decaying to 0.02 | RL |
| Episodes / actions per episode | 300 / 5 | RL |
| λ\_write | 1.0 per added ms of insert latency | RL |
| λ\_storage / storage budget | 1.0 / 25% of the table's size | RL |
| Configs verified on the twin | top 3 | RL, sandbox |
| Twin scale | hero table 100%, others 20% | Twin |
| Timing runs | median of 5 warm runs | Sandbox |
| `pgbench` insert rate | 200 rows per second | Sandbox |
| VeriEQL bound / timeout | 5 rows per table / 60 s | Verification |
| LLM temperature / max tool calls | 0 / 8 | LLM agent |
| LLM provider (added 2026-10-03) | `gemini`, `openai`, `nim` or `ollama` (`llm.provider`) | LLM agent |
| LLM fallback order (added 2026-10-03) | `openai`, then `nim` (`llm.fallback`) | LLM agent |
| OpenAI base URL / model (added 2026-10-03) | `https://api.openai.com/v1` / PENDING (`llm.openai.model`) | LLM agent |
| NIM base URL / model (added 2026-10-03) | `https://integrate.api.nvidia.com/v1` / chosen by `make llm-bench` (`llm.nim.model`) | LLM agent |
| NIM reply token cap / request timeout (added 2026-10-03) | 1024 tokens / 120 s | LLM agent |
| NIM minimum gap between requests (added 2026-10-03) | 1.5 s (free tier: about 40 requests per minute per model) | LLM agent |
| LLM retries (added 2026-10-03) | HTTP 429, 500, 503, 504; 5 attempts, backoff 2 s doubling to at most 30 s | LLM agent |
| Canaries planted | about 20 | Privacy |
| Post-deploy check | 10 minutes; roll back if median latency is over 10% worse | Approve |
| Fast test suite limit | 2 minutes per component | All agents |

## Nuances register

Facts learned while building that are easy to get wrong. Added 2026-10-03; append new rows.

| Nuance | Where it bites | What we do |
| --- | --- | --- |
| NIM's `GET /v1/models` lists the whole hosted catalogue, not what the account can call; most listed models answer 404 "Function not found for account" | Choosing a model from the list alone | `make llm-bench` probes each candidate with one synthetic tool-call request before any real run |
| A hosted NIM model returns tool calls only if its deployment has a tool-call parser; otherwise `tool_choice: auto` returns HTTP 400 ("requires --enable-auto-tool-choice and --tool-call-parser") | Tool use fails on models that chat fine | The probe keeps only models that return a real tool call |
| NIM (OpenAI format) sends tool arguments as a JSON string, Gemini as an object | Parsing arguments | The adapter parses the string; malformed arguments count as a tool-call error and reach the tool as empty arguments |
| Some NIM chat models wrap reasoning in `<think>...</think>` | Numbers inside the reasoning would fail the number checker | The adapter drops `<think>` blocks; only the rest is the answer |
| NIM's free tier allows about 40 requests per minute per model | Benchmarks and parallel tests hit 429 | At least 1.5 s between requests per provider, retries with backoff, live tests run one after another. Measured 2026-10-03: 50 requests at 49 per minute drew 4 429s, each cleared by one backoff; 30 requests to nemotron-3-ultra at 12 per minute drew no 429 but 6 5xx replies, all recovered |
| The egress proxy answers 502 when it cannot reach the LLM host; seen as bursts against `integrate.api.nvidia.com` on 2026-10-03 | One blip ended a whole answer | Connection and proxy errors are retried with the same backoff; a read timeout is not (the request may still run upstream) |
| Only two of about 80 listed NIM models returned a tool call for this key, and neither tags numbers reliably: on Q1, `google/diffusiongemma-26b-a4b-it` passed the number checker 1 run in 4 and `nvidia/nemotron-3-ultra-550b-a55b` 0 in 2, both with 0 tool-call errors | NIM as the main provider | NIM is last in `llm.fallback`; a blocked answer is never shown |
| OpenAI marks `max_tokens` deprecated for chat completions in favour of `max_completion_tokens`, and reasoning models accept only the default temperature | A request that NIM accepts can fail on OpenAI | The token field name and whether to send a temperature are per provider (`llm.<provider>.max_tokens_field`, `send_temperature`) |
| Gemini 3 checks thought signatures on function calls in the conversation (Gemini API thought-signature docs; UNVERIFIED here, no live cross-provider run) | A conversation started on another model cannot continue on Gemini | Fallback reruns the whole question on the next provider |
| `GET /v1/models` has no request body | The outbound ledger records request bodies | Nothing to scan; the response holds model IDs only |
| Gemini's free tier has a daily request quota per model (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`) | Retrying cannot help once it is used up | The dashboard shows the quota error in one line and still shows the twin result and the SQL from its own search |
| The canary scanner matches any 6-character fragment, case-insensitively | A canary built from English words blocks normal text (`commen` in "recommended") | Canary values avoid English words; `db/tests/test_canaries.py` checks every fragment |

## Acceptance criteria

A component is done only when every box below is ticked by a human after running the check in the shared Docker image. An agent's report alone never ticks a box.

**Infrastructure and data (Agent 1)**

- [ ] `docker compose up` starts all services on the Quadro with no manual steps.
- [ ] QuickMart loads with the stated row counts, skew and correlations; Q1 takes over 20 seconds with no extra indexes.
- [ ] The 200-plan sample is committed by hour 1; about 10,000 deduplicated plans exist by hour 4.
- [ ] The twin builds with zero real values (canary scan of the twin finds nothing) and matches production plans for Q1 to Q4.

**Gateway and privacy (Agent 2)**

- [ ] No contract field contains a raw value or real name, checked by the canary scan over a full test run.
- [ ] The negative control lights up the canary counter.
- [ ] Unparsable SQL is withheld and logged, never sent raw.
- [ ] The `ai` container cannot connect to either Postgres (connection attempt fails).
- [ ] The adversarial leak test runs and produces a score.

**Miner (Agent 2)**

- [ ] For Q1, `(region_id, transaction_date)` appears among the candidates, in that order.
- [ ] Switching to the Q4 workload triggers drift within 2 windows.

**GNN (Agent 3)**

- [ ] Median q-error on held-out templates beats Postgres's own estimates.
- [ ] Results for XGBoost and the GNN are reported side by side, including 95th-percentile q-error.
- [ ] Per-node shares mark the Seq Scan as the Q1 bottleneck.

**RL agent (Agent 3)**

- [ ] Recommends the Q1 composite index and, for Q2, an index plus the `date_trunc` rewrite.
- [ ] Its result is compared with greedy on an overlapping-index case and on drift.
- [ ] Adapts to Q4 without restarting.

**Sandbox (Agents 1 and 3)**

- [ ] Q1 measured on the twin drops by over 50% (expected about 99%).
- [ ] Q2 measured on the twin drops by over 50%.
- [ ] Write cost (ms) and storage (MB) are reported for the chosen configuration.
- [ ] Twin fidelity is reported for Q1 to Q3.

**LLM agent, verification and dashboard (Agent 4)**

- [ ] The Q2 rewrite shows Verified.
- [ ] The number checker blocks an answer containing a planted fake number.
- [ ] The DBA's question containing a canary does not leak it.
- [ ] Every dashboard panel listed in Component 8 renders with live data.
- [ ] Approve generates `migration.sql`, `rollback.sql` and the post-deploy check.

**Whole system (humans)**

- [ ] The full demo script runs clean three times in a row.
- [ ] Air-gapped mode answers Q1 with networking to the LLM API switched off.
- [ ] A backup video of the full demo is recorded.

## Open decisions

These choices need a human answer before hour 0; until then, agents build with the default.

| Decision | Options | Default until decided |
| --- | --- | --- |
| LLM for the agent | Any API model with tool calling | The team's preferred API model |
| Local model for air-gapped mode | Depends on the Quadro's GPU memory | A 4-bit 7B coding model via Ollama if it has 6 GB or more; otherwise a slide |
| GNN training location | Quadro or Colab T4 | Colab, until `nvidia-smi` confirms the Quadro's GPU is supported by current PyTorch |
| Work prepared before the event | Depends on hackathon rules | Prepare it, then regenerate a fresh data batch on-site and say so |
| Size of QuickMart's `sales` table | 50M or 10M rows | 50M if generation finishes within 30 minutes on the Quadro; otherwise 10M |
| Start from zero-shot model weights | Fine-tune or train our own | Train our own; try fine-tuning only if the weights download and load quickly |
| Agent tooling | AI coding agents on the Quadro, or elsewhere | AI coding agents on the Quadro, in the shared repo |

Already decided: sharding is written advice only; the dashboard is Streamlit; QuickMart is the demo database.

## PS4 requirement mapping

Every requirement and deliverable in PS4 maps to a component and to evidence judges can see.

| PS4 asks for | Where we meet it | What the judges see |
| --- | --- | --- |
| Never read raw data; attribute bitmasking and metadata hashing | Gateway (1) | AI-view toggle, canary counter, payload ledger |
| Ingest anonymised slow query logs and plans | Gateway (1) | Hashed query list and plan trees |
| Recommend composite indexes and partitioning or sharding via RL | Miner (2) + RL agent (4) | RL configuration panel; sharding as written advice |
| Automatically rewrite inefficient SQL | RL rule selection (4) + LLM (5) + verification (7) | Rewrite with a Verified label |
| GNN natural-language explanations of execution trees | GNN (3) + LLM (5) | Heat-coloured plan tree and its explanation |
| Simulate write-latency and storage impact via PostgreSQL hooks | HypoPG, which uses planner hooks, + twin (6) | Twin results: ms per insert, MB per index |
| Interactive AI-agent dashboard | Dashboard (8) | The live demo |
| Zero data exposure: 100% masked before AI processing | Gateway (1) + privacy proof (7) | Negative control, then 0 canaries; adversarial test score |
| Simulation accuracy | Twin (6) | Twin fidelity score |
| Over 50% faster on inefficient joins | Whole pipeline | QuickMart's join query Q2, measured on the twin |
| Explainability with metadata evidence | GNN (3) + miner (2) | Every recommendation card cites its node, support % and measurement |
| RL generalises to unseen, evolving patterns | RL agent (4) + evaluation | Held-out template results and the live drift demo |

## Unique and complete points

Our edge is not any single algorithm; every piece builds on published work. It is that each claim comes with live proof, which most teams will only assert. Ranked by impact on judges:

| # | Point | Why judges care | Component |
| --- | --- | --- | --- |
| 1 | Canary tokens with a negative control | Privacy proven live, not claimed | 7 |
| 2 | Adversarial leak test | A second AI tries and fails to recover names | 7 |
| 3 | Every speedup measured on the twin | No made-up percentages | 6 |
| 4 | Twin fidelity score | Shows how far simulated numbers can be trusted | 6 |
| 5 | The `pg_stats` leak insight | Proves deeper thinking than "mask the literals" | 1 |
| 6 | Even the DBA's question is sanitised | Closes a leak almost everyone misses | 5 |
| 7 | Composite candidates by data mining | Beats Supabase's single-column advisor | 2 |
| 8 | GNN as a learned cost model with honest q-error | A GNN with a real job, measured against Postgres and XGBoost | 3 |
| 9 | RL that handles index interactions and drift | Answers "why RL?" with a demo | 4 |
| 10 | Verified rewrites with honest status | No silent wrong answers | 7 |
| 11 | Measured write and storage cost | Shows the trade-off, not just the win | 6 |
| 12 | Safe deployment: concurrent build, rollback, auto-revert | Production thinking, as Azure does | 8 |
| 13 | Air-gapped mode on the offline Quadro | Zero bytes leave the building | 5 |
| 14 | Full PS4 coverage, one evidence item per requirement | Easy to score against the checklist | All |

## Master list of failures and fixes

Integration and environment problems, not algorithms, are the most likely way this project loses. Failures specific to one component are in that component's section; these cut across the whole project.

| Failure | What breaks | Fix |
| --- | --- | --- |
| Components do not connect | Eight parts built separately never meet | Agree JSON input/output formats in hour 0; every part ships a stub first |
| Environment setup eats hours | PyTorch Geometric, DSB compilation, HypoPG build | One prebuilt Docker image; pinned versions; tested on the Quadro before the event |
| Training data arrives late | No GNN until it exists | Start plan generation on the Quadro in hour 1 |
| The hero demo looks trivial | A single missing index is a first-week DBA fix | Pick a query where the index, a rewrite and partitioning each add something visible |
| No join example | PS4 targets over 50% on inefficient joins | Use QuickMart's join query Q2 in the demo |
| `EXPLAIN ANALYZE` on production is unsafe | It actually runs slow queries on the live database | Run it only on the benchmark data and the twin; in the production story, read `auto_explain` logs of queries that already ran |
| Wifi or the LLM API fails on stage | The agent cannot answer | Cached hero run plus a local Ollama model |
| Overclaiming "zero exposure" | A judge points out structure still leaks | Claim zero raw data; show a threat-model slide |
| Prior work raised by a judge | "Azure already does this" | A prior-work slide that names Azure, Bao, SWIRL and the zero-shot model, and our difference |
| Pre-built code questioned | Rules may limit work done before the event | Check the rules; regenerate a fresh data batch on-site and say so |
| Scope creep | Extras break the core | Follow the cut list; nothing new after hour 18 |
| Disk or memory runs out | DSB, the twin and the model on one machine | Check free space and RAM on day 0; scale non-hero tables to 20% |
| Exhaustion in the final hours | Bugs and a weak pitch | Freeze at hour 18; sleep in shifts; rehearse after the freeze |

## Data and training plan

We generate our own workload of about 10,000 plans from public benchmarks, because PS4 provides no dataset and real query logs are never published. Total machine time is about 2 hours, mostly running queries.

**Sources**

- DSB (Microsoft's benchmark, adapted from TPC-DS, 76 queries): the main workload. QuickMart adds about 2,000 plans so the GNN has seen the demo database.
- TPC-H: a second database for 2,000–3,000 plans, to test generalisation.
- Optional: the zero-shot cost model project's published plans from 20 databases, for pretraining.

**Generation settings (on the offline Quadro machine)**

1. Postgres 16 in Docker, DSB at scale factor 1.
2. Each query × 30 random parameter sets × 4–5 index setups, about 10,000 runs.
3. `EXPLAIN (ANALYZE, FORMAT JSON)`, run twice, keep the second (warm cache).
4. `statement_timeout = '10s'`; timed-out queries are labelled "at least 10 s".
5. Deduplicate by plan-structure hash, keeping a few copies of each shape.
6. Save one JSON line per plan: template ID, index setup, estimated plan, actual plan.

| Step | Where | Time |
| --- | --- | --- |
| Generate about 10,000 plans | Quadro, 4 to 8 workers | 20–40 min |
| Convert plans to graphs | CPU | 5–10 min |
| One GNN training run | Colab T4 | about 15 min |
| 3–4 runs to try settings | Colab T4 | about 1 hour |
| XGBoost baseline | CPU | about 1 min |

**Rules**

- Split train and test by query template, never at random.
- Save every checkpoint and the processed dataset to Google Drive; Colab disconnects.
- Never run Postgres on Colab; upload one dataset file instead.
- Train on the Quadro instead if PyTorch supports its compute capability (check with `nvidia-smi`).

## Evaluation and metrics

Every number on the results slide is measured against a baseline, on query templates the models never saw. The targets below are our goals, not results yet.

| Metric | What it measures | Baseline | Target |
| --- | --- | --- | --- |
| Median q-error, unseen templates | GNN runtime prediction | Postgres's own estimates; XGBoost | 1.5–2 |
| 95th-percentile q-error | Worst-case prediction | Postgres | Lower than Postgres |
| Pairwise ranking accuracy | Does the GNN order two index setups correctly? | Postgres cost | 80% or more |
| Hero query speedup | End-to-end result, measured on the twin | No index | Over 50% (expect about 99%) |
| Join query speedup | PS4's inefficient-join target | Postgres as is | Over 50% |
| Whole-workload time saved | All templates replayed | Postgres; Supabase `index_advisor`; greedy | Beat all three |
| Write cost added | Insert latency on the twin | No new index | Reported, in ms |
| Twin fidelity | Twin speedup vs. real speedup | — | Reported gap |
| Canaries leaked | Privacy | Gateway off (negative control) | 0 |
| Adversarial name guesses | Privacy | Plaintext control | Near zero on hashed |
| Rewrites verified | Correctness | — | Reported: Verified, Tested only, Rejected |
| LLM answer quality, hashed vs. plaintext | Cost of privacy | Plaintext names | Reported gap |

**Ablations.** An ablation removes one part and measures what is lost. Run four: no miner (RL picks from all columns), no GNN (RL uses raw Postgres costs), no RL (greedy), and no role tags (bare hashes).

## 24-hour build plan

Four AI coding agents write the code, so machine time and testing set the schedule, not typing. Plan generation starts at hour 0, the hero query must pass end-to-end tests by hour 12, and code freezes at hour 18. The human team coordinates, runs the gate tests and owns the pitch.

&#91;embedded content: 24-hour build plan · 5 phases, 4 gates\]

A gate passes only when its tests pass in the shared Docker environment, never because an agent reports it is done.

**Who does what**

Each agent owns one folder of the repo and never edits another's. All agents run on the offline Quadro machine, against one Docker image and one database.

| Owner | Builds | Tests it owns | Done by hour 2 |
| --- | --- | --- | --- |
| Agent 1 | Postgres, DSB, plan generation, twin, `pgbench` scripts | Twin matches statistics; plan agreement on hero queries; plan JSON validity | Plan generation running; a 200-plan sample committed |
| Agent 2 | Gateway, canaries, adversarial leak test, FP-Growth miner | Canary scan on every payload; literal stripping; fail-closed on unparsable SQL | Hashed log and candidate list from stubs |
| Agent 3 | Plan graphs, GNN, XGBoost baseline, RL agent | q-error on held-out templates; RL vs. greedy scenarios | Pipeline runs end to end on the 200-plan sample |
| Agent 4 | LLM tools and RAG, verification, Streamlit dashboard | VeriEQL plus checksum on rewrites; number checker on LLM answers | Dashboard shell showing stub data |
| Human team | Contracts, merges, gate checks, hero and join query choice, deck | The shared end-to-end suite, run at every gate | Contracts frozen; e2e script ready |

The 200-plan sample matters: it lets Agent 3 build and test the whole GNN pipeline while the full 10,000 plans are still generating. GNN training runs as a script on the Quadro if its GPU is supported; otherwise a human runs the same script on Colab.

**Testing plan**

Testing is built in from day 0, in layers. A test written against a fake Postgres proves nothing here, so every test above the unit level runs against the real database in Docker.

| Layer | What it checks | Owner | When it runs | Time limit |
| --- | --- | --- | --- | --- |
| Contract | Every component's JSON output matches the agreed format | Each agent | Every commit | Seconds |
| Unit | Single functions, e.g. one literal stripped, one index ordered correctly | Each agent | Every commit | Under 1 min |
| Component | One part working against real Postgres and HypoPG | Each agent | Every commit | Under 2 min |
| Privacy | Canary scan over every payload in every test run; any hit fails the run | Agent 2 | Every suite | Seconds |
| Correctness | Each rewrite passes VeriEQL and a twin checksum | Agent 4 | Every rewrite | Under 2 min |
| Model | GNN beats Postgres's estimates on held-out templates; RL vs. greedy on overlap and drift | Agent 3 | After each training run | Under 10 min |
| Scenario (end to end) | Hero query, join query, drift, negative control, unparsable query, invented-number check | Human team | Every gate | Under 15 min |
| Demo | The full demo script, three clean runs in a row | Human team | Before freeze | About 20 min |

**Rules that keep heavy testing useful**

The coding agents test thoroughly, which is good, but untamed they can spend hours polishing tests instead of shipping. These rules go in each folder's `AGENTS.md` instruction file:

1. "Done" means contract and component tests pass in the shared Docker image. Nothing else counts.
2. Never weaken a test to make it pass. Deleting an assertion or loosening a threshold needs human approval.
3. Never edit another agent's folder, tests or the shared contracts.
4. Keep each fast suite under the time limit above; slow tests go in a separate suite run only at gates.
5. After three failed fix attempts on one test, stop and ask a human instead of looping.
6. Run code before claiming it works, and check library functions against the installed version, not memory.
7. Record every decision in the folder's notes file, so a fresh agent session can pick up without losing context.

**Agent-specific failures and fixes**

| Failure | Why it happens | Fix |
| --- | --- | --- |
| Code looks done but never ran | Agents can report success from reading code | Rule 1: done means tests pass in Docker |
| Calls to functions that do not exist | APIs differ between library versions, e.g. HypoPG, PyTorch Geometric | Pinned versions; rule 6 |
| Tests quietly weakened | An agent edits a test until it passes | Rule 2; humans review test diffs at every merge |
| Agents collide in one file | Shared code with no owner | One folder per agent; humans merge at gates |
| Context lost in long sessions | Sessions get long or restart | Per-folder notes file (rule 7) |
| An agent waits idle for data | Full plan data takes about 40 minutes | The 200-plan sample from hour 1 |
| Endless test loops | Thorough testing with no stop rule | Time limits and rule 5 |
| The team cannot explain the system | Agents wrote it all | Humans finish the tutoring parts and rehearse Q&A during the freeze |

**Scope.** With agents writing the code, everything in this doc is in scope, including the adversarial leak test, partitioning on the twin, the live drift demo and air-gapped mode. If the hour-12 gate slips, cut in this order: air-gapped mode, then the drift demo, then partitioning.

**Never cut:** the gateway with canaries, a working GNN, a working RL agent (PS4 requires both), the twin measurement of the hero query, one verified rewrite, the dashboard, and the end-to-end test suite.

## Tech stack

Everything is open source and runs in Python plus Postgres, packed into one Docker image.

| Layer | Tool | Used for |
| --- | --- | --- |
| Database | PostgreSQL 16 in Docker | The "production" database and the twin |
| Postgres extensions | `pg_stat_statements`, `auto_explain`, HypoPG | Slow-query log, plan log, hypothetical indexes |
| Benchmark | DSB, TPC-H | Realistic schema, data and queries |
| Backend | Python, FastAPI, `psycopg` | API between all components |
| SQL parsing | `sqlglot` | Hashing names, stripping literals, extracting columns by clause |
| Hashing | Python `hmac` (SHA-256) | Keyed hashing of names |
| Data mining | `mlxtend`, `pandas`, `scikit-learn` | FP-Growth, template clustering, drift detection |
| GNN | PyTorch, PyTorch Geometric | Learned cost model |
| Baseline | XGBoost | Model to beat |
| RL | NumPy (tabular Q-learning) | Configuration search |
| LLM | Any API model with tool calling; Ollama locally | Agent and explanations |
| Rewrite rules | R-Bot rule library | RAG for safe rewrites |
| Verification | VeriEQL | Equivalence checking |
| Load testing | `pgbench` | Write-cost measurement on the twin |
| Dashboard | Streamlit, Graphviz | UI and plan-tree drawing |
| Training | Google Colab T4, Google Drive | GNN runs and checkpoints |
| Demo machine | Offline Quadro workstation | Postgres, twin, air-gapped mode |

## Prior work and how we differ

Automated database tuning is a field more than 25 years old, so we cite prior work openly. What none of these combines is AI tuning behind a provable privacy wall with measured, verified changes.

| Work | What it does | How we differ |
| --- | --- | --- |
| [Azure SQL automatic tuning](https://learn.microsoft.com/ro-ro/azure/sql-database/sql-database-automatic-tuning) | Creates and drops indexes automatically inside Microsoft's cloud | Works on Postgres, explains itself, and the AI never sees raw data |
| [OtterTune](https://dsdsd.da.cwi.nl/past_talks/ottertune/) | ML tuning of Postgres and MySQL settings (knobs); company no longer operating | We tune indexes, partitions and queries, not settings |
| [Supabase index\_advisor](https://github.com/supabase/index_advisor) | HypoPG-based advisor, single-column indexes only | Composite candidates from data mining, chosen by RL |
| [Bao](https://github.com/learnedsystems/baoforpostgresql) | Learned optimizer steering Postgres with query hints | We change the physical design and rewrite queries |
| [SWIRL](https://github.com/hyrise/rl_index_selection) | RL for index selection | Mined candidates shrink the search; privacy layer added |
| [Zero-shot cost models](https://github.com/DataManagementLab/zero-shot-cost-estimation) | GNN predicting plan runtime on unseen databases | Our GNN reads hashed plans and also drives explanations |
| [R-Bot](https://arxiv.org/pdf/2412.01661), [LLM-R2](https://github.com/DAMO-NLP-SG/LLM-R2), [ReSequel](https://github.com/CoDS-GCS/ReSequel) | LLM-assisted query rewriting | Rewrites run in hashed space and are verified |
| [Private database synthesis (UMass, 2011)](https://people.cs.umass.edu/~miklau/assets/pubs/dp/Gupta11Private.pdf) | Synthetic databases for outsourced tuning | Our twin applies the idea, with a measured fidelity score |
| [HypoPG](https://github.com/HypoPG/hypopg) | Hypothetical indexes in Postgres | We use it as our what-if engine |
| [VeriEQL](https://github.com/michaelmior/VeriEQL) | SQL equivalence checking | We use it to verify rewrites |
| [SQL-RewriteBench](https://arxiv.org/pdf/2607.09251) | Correctness-gated rewrite benchmark | Optional external evaluation of our rewrites |

The pitch line for this slide: "Every component stands on published research. Nobody has put them behind a verifiable privacy wall."

## Pitch flow and judge Q&A

The pitch opens with PS4's own example, runs the live demo in the middle, and closes on proof, not features.

**Pitch flow (about 8 minutes)**

1. Hook: "Why is the weekly sales dashboard timing out?" is PS4's own question, and we answer it live.
2. The tension: AI could fix it, but the data cannot leave the company.
3. The insight: the fix depends on the query's shape, not on the rows.
4. Architecture slide: the trust boundary and the four AI components.
5. Live demo (Component 8's flow).
6. Results slide: the metrics table against baselines.
7. Prior-work slide: what exists and our difference.
8. Close: "Everyone else asks you to trust their AI with your data. We prove it never saw it, and we prove every change works before you apply it."

**Questions judges are likely to ask**

| Question | Answer |
| --- | --- |
| Doesn't Azure already do this? | Inside Microsoft's own cloud, with Microsoft seeing your workload. We run on Postgres, behind a provable privacy wall, with explanations. |
| Is it really zero exposure? | Zero raw data. Structure is minimised and rounded, and our threat model lists what remains. |
| Why a GNN if `EXPLAIN ANALYZE` shows the bottleneck? | The GNN predicts plans that have never run, like hypothetical indexes. |
| Why RL and not greedy? | Index interactions and drift; here is RL vs. greedy on both. |
| How do you know the twin is right? | We measured its fidelity against real data, and here is the gap. |
| What if a rewrite is wrong? | It is verified first, labelled honestly, and never applied automatically. |
| Where does your data come from? | Real query logs are never public, so we generated them from Microsoft's DSB benchmark, the research standard. |
| What did you build vs. reuse? | Reused: HypoPG, VeriEQL, R-Bot's rules, benchmarks. Built: the gateway, miner, GNN, RL agent, twin, privacy proofs and dashboard. |
