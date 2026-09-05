"""
Centralized Model Management for AI Pipelines
Handles model loading, caching, and inference with optimization.
"""
import logging
import os
import threading
import ssl
import urllib3
from transformers import pipeline
from transformers import logging as transformers_logging
import torch
from datetime import datetime, timedelta

try:
    from huggingface_hub import login as hf_login
except Exception:
    hf_login = None

logger = logging.getLogger(__name__)
logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)

# Keep transformer logs concise in production and CI terminals.
transformers_logging.set_verbosity_error()
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# Configure SSL and timeout for HuggingFace Hub connections
os.environ.setdefault("HF_HUB_TIMEOUT", "120")  # Increase timeout to 120 seconds
os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFY", "1")  # Disable SSL verification for development

# Disable SSL warnings from urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Use GPU if available for faster inference
DEVICE = 0 if torch.cuda.is_available() else -1
BATCH_SIZE = 32  # Process multiple items at once


def _required_env(env_var):
    """Read a required environment variable, raising an explicit error when missing."""
    value = os.getenv(env_var, '').strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {env_var}")
    return value


def _model_candidates(primary_env_var, fallback_env_var=None):
    """Return deduplicated model candidates from env vars only (strict mode)."""
    candidates = [_required_env(primary_env_var)]
    if fallback_env_var:
        raw_fallbacks = os.getenv(fallback_env_var, '')
        if raw_fallbacks:
            candidates.extend([item.strip() for item in raw_fallbacks.split(',') if item.strip()])

    deduped = []
    seen = set()
    for model_name in candidates:
        if model_name and model_name not in seen:
            deduped.append(model_name)
            seen.add(model_name)
    return deduped

class ModelCache:
    """Cache models and their inference results."""
    
    def __init__(self):
        self.models = {}
        self.results_cache = {}
        self.cache_timeout = timedelta(hours=1)
        self._lock = threading.RLock()
    
    def get_sentiment_pipeline(self):
        """Get or load sentiment analysis pipeline."""
        with self._lock:
            if 'sentiment' not in self.models:
                logger.info("Loading sentiment model...")
                try:
                    last_error = None
                    for model_name in _model_candidates(
                        'SENTIMENT_MODEL',
                        'SENTIMENT_MODEL_FALLBACKS',
                    ):
                        try:
                            self.models['sentiment'] = pipeline(
                                "sentiment-analysis",
                                model=model_name,
                                device=DEVICE,
                                batch_size=BATCH_SIZE
                            )
                            logger.info(f"[OK] Sentiment model loaded: {model_name}")
                            break
                        except Exception as exc:
                            last_error = exc

                    if 'sentiment' not in self.models:
                        raise RuntimeError(last_error or "Failed to load sentiment model")
                except Exception as e:
                    logger.error(f"Failed to load sentiment model: {e}")
                    raise
        return self.models['sentiment']
    
    def get_zero_shot_pipeline(self):
        """Get or load zero-shot classification pipeline."""
        with self._lock:
            if 'zero_shot' not in self.models:
                logger.info("Loading zero-shot classification model...")
                try:
                    last_error = None
                    for model_name in _model_candidates(
                        'ZERO_SHOT_MODEL',
                        'ZERO_SHOT_MODEL_FALLBACKS',
                    ):
                        try:
                            self.models['zero_shot'] = pipeline(
                                "zero-shot-classification",
                                model=model_name,
                                device=DEVICE
                            )
                            logger.info(f"[OK] Zero-shot model loaded: {model_name}")
                            break
                        except Exception as exc:
                            last_error = exc

                    if 'zero_shot' not in self.models:
                        raise RuntimeError(last_error or "Failed to load zero-shot model")

                except Exception as e:
                    logger.error(f"Failed to load zero-shot model: {e}")
                    raise
        return self.models['zero_shot']
    
    def get_ner_pipeline(self):
        """Get or load NER pipeline."""
        with self._lock:
            if 'ner' not in self.models:
                logger.info("Loading NER model...")
                try:
                    self.models['ner'] = pipeline(
                        "ner",
                        model=_required_env('ITDS_NER_MODEL'),
                        device=DEVICE,
                        aggregation_strategy="simple"
                    )
                    logger.info("[OK] NER model loaded")
                except Exception as e:
                    logger.error(f"Failed to load NER model: {e}")
                    raise
        return self.models['ner']
    
    def get_summarization_pipeline(self):
        """Get or load summarization pipeline."""
        with self._lock:
            if 'summarize' not in self.models:
                logger.info("Loading summarization model...")
                try:
                    # Compatibility fallback across transformers versions.
                    last_error = None
                    for model_name in _model_candidates(
                        'SUMMARIZER_MODEL',
                        'SUMMARIZER_MODEL_FALLBACKS',
                    ):
                        for task_name in ("summarization", "text2text-generation", "text-generation"):
                            try:
                                self.models['summarize'] = pipeline(
                                    task_name,
                                    model=model_name,
                                    device=DEVICE
                                )
                                logger.info(f"[OK] Summarization model loaded: {model_name}")
                                break
                            except Exception as exc:
                                last_error = exc
                        if 'summarize' in self.models:
                            break

                    if 'summarize' not in self.models:
                        raise RuntimeError(last_error or "Failed to initialize summarization pipeline")

                    logger.info("[OK] Summarization model loaded")
                except Exception as e:
                    logger.error(f"Failed to load summarization model: {e}")
                    raise
        return self.models['summarize']

    def get_asr_pipeline(self):
        """Get or load automatic speech recognition pipeline."""
        with self._lock:
            if 'asr' not in self.models:
                logger.info("Loading ASR model...")
                try:
                    model_name = _required_env('ITDS_ASR_MODEL')
                    self.models['asr'] = pipeline(
                        "automatic-speech-recognition",
                        model=model_name,
                        device=DEVICE
                    )
                    logger.info(f"[OK] ASR model loaded: {model_name}")
                except Exception as e:
                    logger.error(f"Failed to load ASR model: {e}")
                    raise
        return self.models['asr']

    def get_embedding_model(self, model_name=None):
        """Get or load sentence-transformers embedding model."""
        with self._lock:
            if 'embedding' not in self.models:
                if not model_name:
                    model_name = os.getenv('TOPIC_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
                
                logger.info(f"Loading embedding model: {model_name}...")
                try:
                    from sentence_transformers import SentenceTransformer
                    self.models['embedding'] = SentenceTransformer(model_name)
                    self.models['embedding_name'] = model_name
                    logger.info(f"[OK] Embedding model loaded: {model_name}")
                except Exception as e:
                    logger.error(f"Failed to load embedding model: {e}")
                    raise
        return self.models['embedding']
    
    def get_topic_model(self, model_name=None):
        """
        Get or load BERTopic model instance.
        Note: BERTopic is usually fitted per meeting, but we cache the class/component 
        definitions here if needed.
        """
        with self._lock:
            # We don't cache the fitted model because it's data-specific,
            # but we return the class for standardized initialization.
            try:
                from bertopic import BERTopic
                return BERTopic
            except ImportError:
                logger.error("BERTopic not installed")
                raise
    
    def batch_analyze_sentiment(self, texts, truncate=True):
        """
        Analyze sentiment for multiple texts in batch for efficiency.
        
        Args:
            texts: List of text strings
            truncate: Truncate texts to 512 tokens (model limit)
        
        Returns:
            List of sentiment results
        """
        if not texts:
            return []
        
        # Truncate texts if needed
        if truncate:
            texts = [text[:512] if len(text) > 512 else text for text in texts]
        
        pipeline_instance = self.get_sentiment_pipeline()
        
        try:
            results = pipeline_instance(texts)
            return results
        except Exception as e:
            logger.error(f"Batch sentiment analysis failed: {e}")
            # Fallback to single processing
            return [pipeline_instance(text)[0] if text else {'label': 'NEUTRAL', 'score': 0.5} for text in texts]
    
    def batch_classify(self, texts, labels, truncate=True):
        """
        Classify multiple texts with zero-shot model in batch.
        
        Args:
            texts: List of text strings
            labels: List of possible classification labels
            truncate: Truncate texts to max length
        
        Returns:
            List of classification results
        """
        if not texts:
            return []
        
        # Truncate texts
        if truncate:
            texts = [text[:1024] if len(text) > 1024 else text for text in texts]
        
        pipeline_instance = self.get_zero_shot_pipeline()
        
        try:
            results = []
            for text in texts:
                if text.strip():
                    result = pipeline_instance(text, labels, multi_class=False)
                    results.append(result)
                else:
                    results.append({'labels': labels, 'scores': [0.0] * len(labels)})
            return results
        except Exception as e:
            logger.error(f"Batch classification failed: {e}")
            return []
    
    def batch_extract_entities(self, texts):
        """
        Extract entities from multiple texts in batch.
        
        Args:
            texts: List of text strings
        
        Returns:
            List of entity extraction results
        """
        if not texts:
            return []
        
        pipeline_instance = self.get_ner_pipeline()
        
        try:
            results = [pipeline_instance(text) if text.strip() else [] for text in texts]
            return results
        except Exception as e:
            logger.error(f"Batch NER extraction failed: {e}")
            return [[] for _ in texts]
    
    def clear_cache(self):
        """Clear cached results (but keep models loaded)."""
        self.results_cache.clear()
        logger.info("Results cache cleared")


# Global model cache instance
_model_cache = None
_model_cache_lock = threading.Lock()
_models_initialized = False
_hf_auth_attempted = False


def authenticate_hf_hub_once():
    """Authenticate with Hugging Face Hub once if HF_TOKEN is provided."""
    global _hf_auth_attempted
    if _hf_auth_attempted:
        return

    _hf_auth_attempted = True
    hf_token = os.getenv("HF_TOKEN", "").strip()

    if not hf_token:
        logger.warning("HF_TOKEN not set. Continuing in unauthenticated Hugging Face mode.")
        return

    if hf_login is None:
        logger.warning("huggingface_hub is unavailable. Continuing without HF authentication.")
        return

    try:
        hf_login(token=hf_token, add_to_git_credential=False)
        logger.info("[OK] Hugging Face Hub authentication successful")
    except Exception as exc:
        logger.warning(f"Hugging Face authentication failed. Continuing unauthenticated: {exc}")

def get_model_cache():
    """Get or create global model cache."""
    global _model_cache
    if _model_cache is None:
        with _model_cache_lock:
            if _model_cache is None:
                _model_cache = ModelCache()
    return _model_cache

def initialize_models():
    """Pre-load all models once on application startup."""
    global _models_initialized
    if _models_initialized:
        return

    logger.info("Pre-loading AI models...")
    cache = get_model_cache()
    try:
        authenticate_hf_hub_once()
        # Preload only the lightweight model to keep startup fast and stable.
        cache.get_sentiment_pipeline()
        # Keep heavier models lazy to speed startup and reduce terminal noise.
        _models_initialized = True
        logger.info("[OK] Core models pre-loaded successfully (heavy models remain lazy)")
    except Exception as e:
        logger.error(f"Model pre-loading failed: {e}")
        # Non-blocking - models will load on demand
