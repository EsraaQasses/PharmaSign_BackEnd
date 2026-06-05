import os
import json
import numpy as np
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModel
from src.sign_retrieval.utils import get_logger
from src.sign_retrieval import config

logger = get_logger("semantic_matcher")

class SemanticMatcher:
    def __init__(self, model_name: str = config.TRANSFORMER_MODEL):
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = None
        self.model = None
        self.vocab_embeddings = None
        self.vocab_list = []
        
    def load_model(self):
        """Loads the Hugging Face model and tokenizer."""
        if self.model is not None and self.tokenizer is not None:
            return
            
        logger.info(f"Loading transformer model '{self.model_name}' on {self.device}...")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name).to(self.device)
            self.model.eval()
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model from Hugging Face: {e}")
            raise e

    def get_embeddings(self, texts: list[str]) -> np.ndarray:
        """Computes embeddings for a list of texts using mean pooling."""
        self.load_model()
        
        # Batch size for tokenization/embedding
        batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            encoded_input = self.tokenizer(
                batch_texts, 
                padding=True, 
                truncation=True, 
                max_length=128, 
                return_tensors="pt"
            ).to(self.device)
            
            with torch.no_grad():
                model_output = self.model(**encoded_input)
                
            # Perform mean pooling
            attention_mask = encoded_input['attention_mask']
            token_embeddings = model_output[0] # First element of model_output contains all token embeddings
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            batch_embeddings = (sum_embeddings / sum_mask).cpu().numpy()
            
            # Normalize embeddings to unit length for easy cosine similarity (dot product)
            norms = np.linalg.norm(batch_embeddings, axis=1, keepdims=True)
            batch_embeddings = batch_embeddings / np.maximum(norms, 1e-9)
            
            all_embeddings.append(batch_embeddings)
            
        return np.vstack(all_embeddings)

    def build_and_cache_vocab_embeddings(self, vocabulary: list[str]):
        """Computes embeddings for all vocabulary items and caches them on disk."""
        if not vocabulary:
            logger.warning("Empty vocabulary list. Embeddings index not built.")
            return
            
        logger.info(f"Building semantic embeddings for vocabulary of size {len(vocabulary)}...")
        embeddings = self.get_embeddings(vocabulary)
        
        # Save embedding matrix
        np.save(config.TOKEN_EMBEDDINGS_PATH, embeddings)
        # Save corresponding vocab list
        with open(config.TOKEN_EMBEDDINGS_VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(vocabulary, f, ensure_ascii=False, indent=2)
            
        self.vocab_embeddings = embeddings
        self.vocab_list = vocabulary
        logger.info("Vocabulary embeddings built and cached successfully.")

    def load_cached_embeddings(self) -> bool:
        """Loads cached embeddings from disk. Returns True if successful, False otherwise."""
        if config.TOKEN_EMBEDDINGS_PATH.exists() and config.TOKEN_EMBEDDINGS_VOCAB_PATH.exists():
            try:
                self.vocab_embeddings = np.load(config.TOKEN_EMBEDDINGS_PATH)
                with open(config.TOKEN_EMBEDDINGS_VOCAB_PATH, "r", encoding="utf-8") as f:
                    self.vocab_list = json.load(f)
                logger.info(f"Loaded {len(self.vocab_list)} cached vocabulary embeddings.")
                return True
            except Exception as e:
                logger.error(f"Failed to load cached embeddings: {e}")
        return False

    def match(self, normalized_phrase: str, threshold: float = config.SEMANTIC_THRESHOLD) -> tuple[str, float]:
        """
        Computes embedding for query phrase and returns the closest vocabulary item
        if the similarity score is above the threshold.
        Returns: (matched_token, similarity_score) or (None, 0.0)
        """
        if not self.vocab_list or self.vocab_embeddings is None:
            # Try to load cached embeddings
            success = self.load_cached_embeddings()
            if not success:
                logger.warning("No vocabulary embeddings loaded. Semantic matching disabled.")
                return None, 0.0
                
        # Compute embedding for the query (normalized and length 1)
        query_embedding = self.get_embeddings([normalized_phrase])[0]
        
        # Calculate cosine similarity (dot product of normalized vectors)
        similarities = np.dot(self.vocab_embeddings, query_embedding)
        
        max_idx = np.argmax(similarities)
        score = float(similarities[max_idx])
        
        if score >= threshold:
            matched_vocab = self.vocab_list[max_idx]
            logger.info(f"Semantic match: '{normalized_phrase}' -> '{matched_vocab}' (score={score:.4f})")
            return matched_vocab, score
            
        logger.info(f"No semantic match above threshold {threshold} for: '{normalized_phrase}' (best score={score:.4f})")
        return None, score
