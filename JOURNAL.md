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
