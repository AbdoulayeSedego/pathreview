# PathReview — Module 3 Journal

## Week 7 — Issue selection

**Issue link:** https://github.com/ascherj/pathreview/issues/80

**Issue title:** `DELETE /profiles/{profile_id}` doesn't cascade to delete associated reviews and embeddings

**Tier:** [ ] Tier 1  [x] Tier 2  [ ] Tier 3

**Problem summary:**
When a profile is deleted through the `DELETE /profiles/{profile_id}` endpoint, only the profile row itself is removed from the database. The reviews that were generated for that profile, and the vector store embeddings created from its resume/portfolio content, are never cleaned up — they stay behind as orphaned records keyed to a profile ID that no longer exists. This affects `api/routes/profiles.py` (the delete endpoint) and `core/services/profile_service.py` (the deletion logic), and likely also touches the RAG vector store client in `rag/retriever/vector_store.py` since embeddings live outside the relational database. A correct fix deletes (or cascades the deletion of) the associated reviews and embeddings whenever a profile is deleted, so no orphaned data is left querying against a nonexistent profile.

**Branch name:** fix/80-cascade-delete-profile-reviews

**Setup confirmation:** [x] App runs locally at localhost:5173

**Cohort ledger:** [ ] Issue added to cohort ledger

## Week 8 — Reproduction & solution planning

**Reproduction commit link:** https://github.com/AbdoulayeSedego/pathreview/commit/5327f961da922fd428dfb2644f76f3dc6ed2f007

**Reproduction summary:**
I added an integration test (`tests/integration/test_profile_delete_cascade_repro.py`) that ingests embeddings into a `profile_{id}` ChromaDB collection, runs the deletion path the way `delete_profile` does it today, then asserts the collection is empty. It XFAILs — the embeddings survive, proving the orphaning. Reproducing this also refined my Week 7 understanding: `delete_profile` already deletes the `reviews` and `ingested_sources` rows in Postgres (and the models declare `ondelete="CASCADE"` FKs), so the real gap is purely the vector store — the service never removes the `profile_{id}` collection, and `VectorStore` has no method to delete a whole collection.

**PLAN.md link:** https://github.com/AbdoulayeSedego/pathreview/blob/fix/80-cascade-delete-profile-reviews/PLAN.md

**Walkthrough video (recommended):** [not recorded]

**Blockers or open questions:**
- Cross-store atomicity: Postgres and ChromaDB can't share a transaction, so I need to decide the delete order and how to handle a partial failure (best-effort + logging vs. compensating retry).
- Which ChromaDB the running app actually writes to — the embedded `PersistentClient` (`.chromadb`) vs. the `vector_db_url` HTTP container — so the fix deletes from the same store ingestion wrote to.
- `_record_ingested_source` in `ingestion/pipeline.py` is currently a logging-only placeholder, so `ingested_sources` rows may not be populated on real data; I'll confirm this doesn't change the fix's scope.

## Week 9 — Solution building & PR submission

*Note: both check-ins below were completed in one working session rather than split Wednesday/Sunday — logging that here for transparency rather than implying a cadence that didn't happen.*

### Check-in 1 (mid-week)

**Current progress:**
All 5 sub-tasks from PLAN.md's "Plan" section are implemented:
1. Added `VectorStore.delete_collection()` in `rag/retriever/vector_store.py`, catching `chromadb.errors.NotFoundError` specifically (not a bare `except`) so it's a safe no-op when a profile was never ingested.
2. Wired it into `delete_profile` in `core/services/profile_service.py`, called *before* the Postgres deletes — resolves the Week 8 atomicity question: if the vector store throws, nothing in Postgres is touched and the whole request is safely retryable.
3. Converted the Week 8 `xfail` reproduction into a real regression test (renamed `test_profile_delete_cascade_repro.py` → `test_profile_delete_cascade.py`), plus added a cross-profile isolation test and a no-embeddings-profile edge case.
4. Ran `make test-unit`/`make check` before and after, diffed the failure lists — zero new failures.
5. Updated the endpoint/service docstrings to describe the embeddings cascade.

Also resolved the two Week 8 open questions: traced every call site and confirmed nothing in the app currently instantiates `VectorStore` or `IngestionPipeline` anywhere (ingestion is unwired scaffolding), so there's no existing pattern to match — `delete_profile` just constructs `VectorStore()` with its class default, with an optional `vector_store` param for test injection. Verified this for real: brought up a live server + Postgres, registered a user, created a profile, seeded embeddings directly into `.chromadb`, called the real `DELETE /profiles/{id}` endpoint, confirmed `204` → `GET` now `404` → ChromaDB collection gone.

**Next steps:**
Added unit tests for `delete_collection` and for `delete_profile`'s ordering/error-handling/default-vs-injected paths (8 new tests, all passing). Filled out PLAN.md's risk section with how each risk actually resolved. Opening a draft PR and sharing it in the course Slack for peer/mentor feedback before marking it ready for review.

**Blockers:**
None on the implementation itself. Caught and fixed one process mistake worth noting: an early `git add` with a bad pathspec silently staged nothing, so my first "fix" commit only contained the test files, not the actual code change — caught it by diffing my branch against `upstream/main` before opening the PR and seeing the production files weren't in the diff. Fixed with a follow-up commit rather than force-pushing over the already-pushed commit.

---

### Check-in 2 (end of week)

**PR link:** https://github.com/ascherj/pathreview/pull/662 (currently a **draft** — awaiting peer/mentor feedback in Slack before marking it ready for review; will update this entry and re-submit once it is)

**Branch:** `fix/80-cascade-delete-profile-reviews`

**What you built:**
`DELETE /profiles/{profile_id}` already cascaded to Postgres (`reviews`, `ingested_sources`) but never touched the vector store, leaving each deleted profile's embeddings orphaned forever in a ChromaDB collection named `profile_{profile_id}`. The fix adds `VectorStore.delete_collection()` and calls it from `delete_profile` before the Postgres deletes, so a vector-store failure aborts cleanly instead of leaving the two stores disagreeing.

**Tests added or updated:**
- `tests/unit/test_vector_store.py` (new) — `delete_collection` removes an existing collection, is a no-op on a missing one, and only touches the named collection.
- `tests/unit/test_profile_service.py` (new) — `delete_profile` calls `delete_collection` with the exact `profile_{id}` name, deletes reviews/sources/profile, aborts before touching Postgres if the vector store fails, and falls back to constructing its own `VectorStore()` when none is injected.
- `tests/integration/test_profile_delete_cascade.py` (renamed from the Week 8 repro, `xfail` removed) — real ChromaDB end-to-end: embeddings gone after delete, a second profile's collection untouched, no-embeddings profile is a safe no-op.

**Self-review confirmation:** [x] make check passes  [x] make test-unit passes
*(Both against a documented pre-existing baseline, per the Week 9 instructions: `make test-unit` has 53 pre-existing failures unrelated to this change — mostly an `AsyncMock`-attribute-chaining issue under Python 3.14 in `test_review_service.py`, plus unrelated assertion mismatches in `test_skill_extractor.py`/`test_tech_detector.py`/`test_resume_parser.py`/`test_structural_chunker.py`/`test_security.py`. I diffed the full failing-test list before and after my change — identical, plus 8 new passing tests. `make lint`/`make format` have pre-existing repo-wide findings (182→180 and 52→50 respectively, both improved by cleanup in files I touched); `make typecheck` hard-stops repo-wide on a pre-existing numpy/mypy-vs-Python-3.14 incompatibility before reaching any file I changed — confirmed byte-identical output before/after. Full details in the PR description.)*

**Draft PR feedback received from:** none yet — PR just opened as a draft; will update this once I get feedback in Slack and before marking it ready for review.
