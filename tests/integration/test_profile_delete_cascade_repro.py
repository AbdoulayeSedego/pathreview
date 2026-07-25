"""Reproduction for issue #80: deleting a profile orphans its vector embeddings.

https://github.com/ascherj/pathreview/issues/80

`DELETE /profiles/{profile_id}` -> `core.services.profile_service.delete_profile`
removes the profile's `reviews` and `ingested_sources` rows from Postgres, but it
never touches the vector store. Each profile's embeddings live in a dedicated
ChromaDB collection named ``profile_{profile_id}`` (see
``rag/retriever/hybrid.py``), and nothing deletes that collection when the profile
is deleted. The embeddings are left behind forever, keyed to a profile ID that no
longer exists.

This test reproduces that gap at the vector-store layer, which is where the bug is
provable without a running Postgres. It is marked ``xfail(strict=True)`` because the
fix has not landed yet: it currently XFAILs, and it will XPASS (flipping the suite
red so the marker gets removed) once Week 9 wires vector cleanup into
``delete_profile``.
"""

from dataclasses import dataclass

import pytest

from rag.retriever.vector_store import VectorStore


@dataclass
class _Chunk:
    """Minimal stand-in for an ingested chunk, matching what add_chunks reads."""

    id: str
    source_id: str
    text: str
    chunk_index: int
    section: str | None = None


def _simulate_current_delete_profile(_profile_id: str) -> None:
    """Mirror what delete_profile does today.

    The real service deletes Review + IngestedSource rows from Postgres and commits.
    Crucially, it makes **zero** calls into the vector store — reproduced here as a
    deliberate no-op. This is the bug.
    """
    # intentionally empty: the current code path never removes embeddings
    return None


@pytest.mark.integration
@pytest.mark.xfail(
    strict=True,
    reason="issue #80: delete_profile does not remove vector embeddings yet; "
    "fix lands in Week 9 and will flip this to XPASS",
)
def test_deleting_profile_leaves_orphaned_embeddings(tmp_path) -> None:
    store = VectorStore(persist_dir=str(tmp_path / "chromadb"))

    profile_id = "11111111-1111-1111-1111-111111111111"
    collection_name = f"profile_{profile_id}"
    source_id = f"resume_{profile_id}_deadbeef"

    # --- Ingestion: this profile has embeddings in its collection. ---
    chunks = [
        _Chunk(
            id=f"{source_id}_chunk_0",
            source_id=source_id,
            text="Python and FastAPI experience.",
            chunk_index=0,
            section="skills",
        ),
        _Chunk(
            id=f"{source_id}_chunk_1",
            source_id=source_id,
            text="Built REST APIs at TechCorp.",
            chunk_index=1,
            section="experience",
        ),
    ]
    embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    store.add_chunks(list(zip(chunks, embeddings, strict=False)), collection_name)

    assert store.get_collection(collection_name).count() == 2, "setup: embeddings should exist"

    # --- Act: delete the profile the way the app does today. ---
    _simulate_current_delete_profile(profile_id)

    # --- Assert the DESIRED post-condition (issue #80): no orphaned embeddings. ---
    remaining = store.get_collection(collection_name).count()
    assert remaining == 0, (
        f"issue #80: {remaining} embeddings for deleted profile {profile_id} "
        f"remain orphaned in collection '{collection_name}'"
    )
