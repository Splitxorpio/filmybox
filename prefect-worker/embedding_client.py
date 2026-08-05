MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"

# Native output is 768-dim; truncated to 384 via Matryoshka Representation
# Learning to fit the existing movie_embeddings.embedding VECTOR(384) column
# without a schema migration / full corpus re-key.
EMBEDDING_DIM = 384

# nomic-embed-text-v1.5 requires a task-instruction prefix on every input -
# "clustering" matches our use case (grouping similar movies), not
# "search_query"/"search_document" (query-vs-document retrieval).
TASK_PREFIX = "clustering: "

# Stored in movie_embeddings.model_version - identifies both the base model
# and the truncation width, since those together determine the vector space.
MODEL_VERSION = f"{MODEL_NAME}@{EMBEDDING_DIM}d"

_model = None


def _get_model():
    global _model
    if _model is None:
        # Imported lazily so anything that doesn't need embeddings (the
        # TMDb/BOM backfills) doesn't pay the torch import cost.
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    import torch.nn.functional as F

    model = _get_model()
    prefixed = [TASK_PREFIX + t for t in texts]
    embeddings = model.encode(prefixed, batch_size=64, show_progress_bar=True, convert_to_tensor=True)

    # Matryoshka truncation: layer-norm on the full 768-dim vector, slice to
    # the target width, then re-normalize - per nomic's documented recipe.
    embeddings = F.layer_norm(embeddings, normalized_shape=(embeddings.shape[1],))
    embeddings = embeddings[:, :EMBEDDING_DIM]
    embeddings = F.normalize(embeddings, p=2, dim=1)

    return embeddings.tolist()
