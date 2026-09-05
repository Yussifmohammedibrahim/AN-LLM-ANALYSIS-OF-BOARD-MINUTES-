import time
import sys
import os
import logging
import threading

def trace_startup():
    results = {}
    
    # 1) sys.path/logging setup
    start = time.time()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "itds_env"))
    import logging.config
    logging.getLogger("torch._subclasses.fake_tensor").disabled = True
    logging.getLogger("torch").setLevel(logging.ERROR)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    results["1_setup"] = time.time() - start
    
    # 2) logging.config.fileConfig
    start = time.time()
    if os.path.exists("itds_env/app/logging.conf"):
        logging.config.fileConfig("itds_env/app/logging.conf", disable_existing_loggers=False)
    else:
        print("Warning: itds_env/app/logging.conf not found")
    results["2_log_config"] = time.time() - start
    
    # 3) importing app.app
    start = time.time()
    from app.app import app
    results["3_import_app"] = time.time() - start
    
    # 4) starting the warm_models_async thread
    start = time.time()
    def dummy_warm():
        pass
    threading.Thread(target=dummy_warm, daemon=True).start()
    results["4_thread_start"] = time.time() - start
    
    # 5) invoking app.run() up to the point before blocking
    # We can't really call app.run() as it blocks. 
    # But we can measure the prep for it if there is any visible in run.py.
    # In run.py it's just the print statements and then app.run().
    # We will simulate the print and skip app.run().
    start = time.time()
    port = 5001
    # print(f"Starting ITDS Backend on http://localhost:{port}")
    results["5_pre_run"] = time.time() - start
    
    # Separately time importing app.model_manager and calling initialize_models()
    # This is what's inside the thread in run.py.
    
    from app.model_manager import initialize_models
    
    start_import_mm = time.time()
    # Already imported often by app.app but let's check
    import app.model_manager
    results["extra_import_mm"] = time.time() - start_import_mm
    
    start_init = time.time()
    print("Starting initialize_models (this may take a while)...")
    initialize_models()
    results["extra_initialize_models"] = time.time() - start_init
    
    print("\n--- Timing Results (seconds) ---")
    for k, v in results.items():
        print(f"{k}: {v:.4f}s")
    
    slowest = max(results, key=results.get)
    print(f"\nSlowest step: {slowest} ({results[slowest]:.4f}s)")

if __name__ == "__main__":
    trace_startup()
