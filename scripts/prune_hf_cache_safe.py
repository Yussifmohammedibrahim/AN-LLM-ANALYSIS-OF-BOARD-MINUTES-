import argparse
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / "itds_env" / ".env"

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "Lib",
    "Scripts",
    "site-packages",
    "dist",
    "build",
}

TEXT_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".jsonl", ".env", ".md", ".txt", ".yaml", ".yml"
}

MODEL_ENV_KEYS = [
    "SENTIMENT_MODEL",
    "SENTIMENT_MODEL_FALLBACKS",
    "ZERO_SHOT_MODEL",
    "ZERO_SHOT_MODEL_FALLBACKS",
    "SUMMARIZER_MODEL",
    "SUMMARIZER_MODEL_FALLBACKS",
    "ITDS_NER_MODEL",
    "ITDS_QA_MODEL",
    "ITDS_ASR_MODEL",
    "TOPIC_EMBEDDING_MODEL",
]


def parse_env_models():
    load_dotenv(ENV_PATH)
    models = set()
    for key in MODEL_ENV_KEYS:
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        parts = [x.strip() for x in raw.split(",") if x.strip()]
        models.update(parts)
    return models


def model_id_from_cache_dir(name):
    if not name.startswith("models--"):
        return ""
    raw = name[len("models--"):]
    return raw.replace("--", "/")


def workspace_text_files(root_dir):
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            path = Path(root) / filename
            if path.suffix.lower() in TEXT_EXTS or path.name == ".env":
                yield path


def collect_workspace_text_blob(root_dir):
    chunks = []
    for path in workspace_text_files(root_dir):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n".join(chunks)


def find_cache_root():
    # Priority: explicit env vars, then default Windows HF cache path.
    explicit_hub = os.getenv("HUGGINGFACE_HUB_CACHE", "").strip()
    if explicit_hub:
        hub = Path(explicit_hub)
        if hub.exists():
            return hub

    hf_home = os.getenv("HF_HOME", "").strip()
    if hf_home:
        hub = Path(hf_home) / "hub"
        if hub.exists():
            return hub

    default_hub = Path.home() / ".cache" / "huggingface" / "hub"
    if default_hub.exists():
        return default_hub

    raise FileNotFoundError("Could not find HuggingFace hub cache directory")


def format_size_bytes(num_bytes):
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def dir_size(path):
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except Exception:
                continue
    return total


def main():
    parser = argparse.ArgumentParser(description="Safely prune clearly unused HuggingFace cached models")
    parser.add_argument("--delete", action="store_true", help="Actually delete candidates (default is dry run)")
    parser.add_argument("--verbose", action="store_true", help="Print keep reasons")
    args = parser.parse_args()

    env_models = parse_env_models()
    workspace_blob = collect_workspace_text_blob(ROOT_DIR)
    cache_root = find_cache_root()

    model_dirs = [p for p in cache_root.iterdir() if p.is_dir() and p.name.startswith("models--")]

    keep = []
    delete = []

    for model_dir in sorted(model_dirs, key=lambda x: x.name.lower()):
        model_id = model_id_from_cache_dir(model_dir.name)
        size_bytes = dir_size(model_dir)
        in_env = model_id in env_models
        in_workspace = model_id in workspace_blob

        entry = {
            "model_id": model_id,
            "dir": str(model_dir),
            "size_bytes": size_bytes,
            "size": format_size_bytes(size_bytes),
            "in_env": in_env,
            "in_workspace": in_workspace,
        }

        # Conservative rule: delete only if model is in neither env config nor workspace references.
        if (not in_env) and (not in_workspace):
            delete.append(entry)
        else:
            keep.append(entry)

    print("=== SAFE HF CACHE PRUNE PLAN ===")
    print(f"Cache root: {cache_root}")
    print(f"Total cached model dirs: {len(model_dirs)}")
    print(f"Keep: {len(keep)}")
    print(f"Delete candidates (clearly unused): {len(delete)}")

    if args.verbose:
        print("\n-- KEEP --")
        for item in keep:
            reason = []
            if item["in_env"]:
                reason.append("env")
            if item["in_workspace"]:
                reason.append("workspace")
            print(f"KEEP  {item['model_id']}  [{item['size']}]  reason={'+'.join(reason)}")

    print("\n-- DELETE CANDIDATES --")
    for item in delete:
        print(f"DELETE {item['model_id']}  [{item['size']}]  path={item['dir']}")

    if not args.delete:
        print("\nDry run only. Re-run with --delete to remove candidates.")
        return

    reclaimed = 0
    for item in delete:
        target = Path(item["dir"])
        try:
            shutil.rmtree(target)
            reclaimed += item["size_bytes"]
            print(f"REMOVED {item['model_id']}")
        except Exception as exc:
            print(f"FAILED  {item['model_id']} -> {exc}")

    print(f"\nPotential reclaimed space: {format_size_bytes(reclaimed)}")


if __name__ == "__main__":
    main()
