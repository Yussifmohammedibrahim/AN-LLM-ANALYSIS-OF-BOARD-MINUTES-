import os
import sys

# Add itds_env directory to the path so python can import the app modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'itds_env'))

from app.model_manager import get_model_cache, authenticate_hf_hub_once

def main():
    print("=====================================================================")
    print("Warming up ITDS AI Models (downloading and caching locally)")
    print("=====================================================================")
    
    # Try to authenticate Hugging Face Hub (checks HF_TOKEN env variable)
    authenticate_hf_hub_once()
    
    cache = get_model_cache()
    
    models_to_warm = [
        ("Sentiment Analysis Model", cache.get_sentiment_pipeline),
        ("Named Entity Recognition (NER) Model", cache.get_ner_pipeline),
        ("Zero-shot Classifier Model", cache.get_zero_shot_pipeline),
        ("Summarization Model", cache.get_summarization_pipeline),
        ("ASR Speech-to-Text Model", cache.get_asr_pipeline),
        ("Topic Embedding Model", cache.get_embedding_model)
    ]
    
    failed = 0
    for name, load_func in models_to_warm:
        print(f"\n[+] Loading {name}...")
        try:
            load_func()
            print(f"[OK] {name} initialized and cached successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to load {name}: {e}")
            failed += 1
            
    print("\n=====================================================================")
    if failed == 0:
        print("[SUCCESS] All AI models pre-downloaded and warmed up successfully.")
    else:
        print(f"[WARNING] Model warming complete with {failed} failure(s). Check messages above.")
    print("=====================================================================")

if __name__ == "__main__":
    main()
