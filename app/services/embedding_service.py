"""
Embedding Service

Compute embeddings using sentence-transformers (MiniLM).
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_model = None


def get_model():
    """Load MiniLM model (singleton pattern)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _model


class EmbeddingService:
    """Service for computing text embeddings."""

    @staticmethod
    def compute_embedding(text: str) -> list[float]:
        """
        Compute 384-dim embedding for text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of 384 floats representing the embedding
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding, returning zero vector")
            return [0.0] * 384

        model = get_model()
        embedding = model.encode(text)
        return embedding.tolist()

    @staticmethod
    def compute_embeddings_batch(texts: list[str]) -> list[list[float]]:
        """
        Compute embeddings for multiple texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of embeddings (each is list of 384 floats)
        """
        if not texts:
            return []

        model = get_model()
        embeddings = model.encode(texts)
        return embeddings.tolist()
