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
