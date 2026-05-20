import os
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient, models

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "hmrc_pages"
DENSE_DIM = 768


class QdrantStore:
    """Singleton wrapper for the Qdrant vector database."""

    def __init__(self):
        self.client: AsyncQdrantClient | None = None

    def connect(self):
        if not self.client:
            self.client = AsyncQdrantClient(url=QDRANT_URL)

    async def ensure_collection(self):
        """Creates the collection and ensures indexes exist."""
        self.connect()
        collections_resp = await self.client.get_collections()
        collections = collections_resp.collections
        
        if not any(c.name == COLLECTION for c in collections):
            await self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config={
                    "dense": models.VectorParams(
                        size=DENSE_DIM,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "bm25": models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    )
                },
            )
            print(f"Created Qdrant collection '{COLLECTION}'.")

        # Ensure payload indexes exist
        info = await self.client.get_collection(COLLECTION)
        existing_indexes = info.payload_schema.keys()

        if "section_id" not in existing_indexes:
            await self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="section_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        
        if "manual_slug" not in existing_indexes:
            await self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="manual_slug",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

        if "audience_level" not in existing_indexes:
            await self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="audience_level",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

        if "source_type" not in existing_indexes:
            await self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="source_type",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            
        if "title" not in existing_indexes:
            await self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="title",
                field_schema=models.TextIndexParams(
                    type="text",
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=15,
                    lowercase=True,
                ),
            )
            print(f"Created 'title' text index for collection '{COLLECTION}'.")

    async def upsert_batch(self, points: list[models.PointStruct]):
        """Upsert a batch of points. Idempotent by ID."""
        self.connect()
        await self.client.upsert(collection_name=COLLECTION, points=points)

    async def hybrid_search(
        self,
        dense_vector: list[float],
        sparse_vector: models.SparseVector,
        limit: int = 10,
        manual_filter: str | None = None,
    ) -> list:
        """Hybrid search with RRF fusion across dense + BM25 vectors."""
        self.connect()

        query_filter = None
        if manual_filter:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="manual_slug",
                        match=models.MatchValue(value=manual_filter),
                    )
                ]
            )

        results = await self.client.query_points(
            collection_name=COLLECTION,
            prefetch=[
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=limit * 3,
                    filter=query_filter,
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using="bm25",
                    limit=limit * 3,
                    filter=query_filter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return results.points

    async def search_by_title(self, query: str, limit: int = 10) -> list:
        """Scroll through points matching a title substring (for autocomplete)."""
        self.connect()
        results = await self.client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="title",
                        match=models.MatchText(text=query),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )
        return results[0]  # (points, next_offset)

    async def get_by_section_id(self, section_id: str) -> list:
        """Get all chunks for a given section_id."""
        self.connect()
        results = await self.client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="section_id",
                        match=models.MatchValue(value=section_id),
                    )
                ]
            ),
            limit=20,
            with_payload=True,
        )
        return results[0]

    async def get_sections_for_manual(self, manual_slug: str) -> list:
        """Get all unique sections for a manual (for the tree navigator)."""
        self.connect()
        results = await self.client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="manual_slug",
                        match=models.MatchValue(value=manual_slug),
                    )
                ]
            ),
            limit=5000,
            with_payload=["section_id", "title", "breadcrumb"],
        )
        return results[0]

    async def count(self) -> int:
        """Total points in the collection."""
        self.connect()
        info = await self.client.get_collection(COLLECTION)
        return info.points_count

    async def wipe(self):
        """Delete and recreate the collection."""
        self.connect()
        try:
            await self.client.delete_collection(COLLECTION)
            print(f"Deleted collection '{COLLECTION}'.")
        except Exception:
            pass
        await self.ensure_collection()


store = QdrantStore()
