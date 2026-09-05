import argparse
import json
import os
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from transformers import pipeline


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / "itds_env" / ".env"


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def tokenize(value):
    return [t for t in re.findall(r"[a-z0-9-]+", normalize_text(value).lower()) if t]


def token_f1(predicted, reference):
    pred_tokens = tokenize(predicted)
    ref_tokens = tokenize(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0

    pred_counts = Counter(pred_tokens)
    ref_counts = Counter(ref_tokens)
    overlap = sum((pred_counts & ref_counts).values())
    if overlap == 0:
        return 0.0

    precision = overlap / max(1, len(pred_tokens))
    recall = overlap / max(1, len(ref_tokens))
    return (2 * precision * recall) / max(1e-12, precision + recall)


def safe_label(value):
    return normalize_text(value).lower()


def parse_model_candidates(primary_env_key, fallback_env_key=None):
    candidates = []
    primary = os.getenv(primary_env_key, "").strip()
    if primary:
        candidates.append(primary)

    if fallback_env_key:
        raw_fallbacks = os.getenv(fallback_env_key, "")
        if raw_fallbacks:
            candidates.extend([x.strip() for x in raw_fallbacks.split(",") if x.strip()])

    deduped = []
    seen = set()
    for model in candidates:
        if model not in seen:
            seen.add(model)
            deduped.append(model)
    return deduped


def load_records(dataset_path):
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    if dataset_path.suffix.lower() == ".jsonl":
        records = []
        with dataset_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                row = line.strip()
                if not row:
                    continue
                try:
                    records.append(json.loads(row))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL on line {line_number}: {exc}") from exc
        return records

    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]

    raise ValueError("Dataset must be JSON array, JSON object with records, or JSONL")


def evaluate_sentiment(model_name, records, device):
    clf = pipeline("sentiment-analysis", model=model_name, device=device)
    total = 0
    correct = 0
    latencies = []

    for item in records:
        if not item.get("sentiment_label"):
            continue
        text = normalize_text(item.get("text"))[:512]
        if not text:
            continue

        started = time.perf_counter()
        pred = clf(text)[0]
        latencies.append((time.perf_counter() - started) * 1000.0)

        total += 1
        if safe_label(pred.get("label")) == safe_label(item.get("sentiment_label")):
            correct += 1

    return {
        "count": total,
        "accuracy": round(correct / total, 4) if total else None,
        "latency_ms_avg": round(statistics.mean(latencies), 2) if latencies else None,
    }


def evaluate_zero_shot(model_name, records, device):
    clf = pipeline("zero-shot-classification", model=model_name, device=device)
    total = 0
    correct = 0
    latencies = []

    for item in records:
        if not item.get("zero_shot_label"):
            continue
        text = normalize_text(item.get("text"))[:1024]
        labels = item.get("zero_shot_labels") or []
        if not text or not labels:
            continue

        started = time.perf_counter()
        pred = clf(text, candidate_labels=labels, multi_label=False)
        latencies.append((time.perf_counter() - started) * 1000.0)

        predicted_label = safe_label((pred.get("labels") or [""])[0])
        total += 1
        if predicted_label == safe_label(item.get("zero_shot_label")):
            correct += 1

    return {
        "count": total,
        "accuracy": round(correct / total, 4) if total else None,
        "latency_ms_avg": round(statistics.mean(latencies), 2) if latencies else None,
    }


def ner_pairs_from_gold(gold_entities):
    pairs = set()
    for item in gold_entities or []:
        text = normalize_text(item.get("text") or item.get("word"))
        label = safe_label(item.get("label") or item.get("entity_group") or item.get("entity"))
        if text and label:
            pairs.add((text.lower(), label.upper()))
    return pairs


def ner_pairs_from_pred(pred_entities):
    pairs = set()
    for item in pred_entities or []:
        text = normalize_text(item.get("word") or item.get("text"))
        label = safe_label(item.get("entity_group") or item.get("label") or item.get("entity"))
        if text and label:
            pairs.add((text.lower(), label.upper()))
    return pairs


def evaluate_ner(model_name, records, device):
    clf = pipeline("ner", model=model_name, aggregation_strategy="simple", device=device)
    tp = fp = fn = 0
    calls = 0
    latencies = []

    for item in records:
        if not item.get("ner_entities"):
            continue
        text = normalize_text(item.get("text"))
        if not text:
            continue

        started = time.perf_counter()
        pred_entities = clf(text)
        latencies.append((time.perf_counter() - started) * 1000.0)

        gold = ner_pairs_from_gold(item.get("ner_entities"))
        pred = ner_pairs_from_pred(pred_entities)
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
        calls += 1

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = (2 * precision * recall) / max(1e-12, precision + recall)

    return {
        "count": calls,
        "precision": round(precision, 4) if calls else None,
        "recall": round(recall, 4) if calls else None,
        "f1": round(f1, 4) if calls else None,
        "latency_ms_avg": round(statistics.mean(latencies), 2) if latencies else None,
    }


def evaluate_summarization(model_name, records, device):
    candidate_tasks = ["summarization", "text2text-generation", "text-generation"]
    model_pipe = None
    for task_name in candidate_tasks:
        try:
            model_pipe = pipeline(task_name, model=model_name, device=device)
            break
        except Exception:
            continue

    if model_pipe is None:
        raise RuntimeError(f"No supported summarization pipeline task for {model_name}")

    scores = []
    latencies = []

    for item in records:
        if not item.get("reference_summary"):
            continue
        text = normalize_text(item.get("text"))
        if not text:
            continue

        started = time.perf_counter()
        pred = model_pipe(text[:1600], max_length=120, min_length=20, do_sample=False)
        latencies.append((time.perf_counter() - started) * 1000.0)

        if isinstance(pred, list) and pred:
            predicted = pred[0].get("summary_text") or pred[0].get("generated_text") or ""
        else:
            predicted = ""
        scores.append(token_f1(predicted, item.get("reference_summary")))

    return {
        "count": len(scores),
        "token_f1_avg": round(sum(scores) / len(scores), 4) if scores else None,
        "latency_ms_avg": round(statistics.mean(latencies), 2) if latencies else None,
    }


def evaluate_qa(model_name, records, device):
    qa = pipeline("question-answering", model=model_name, device=device)
    scores = []
    latencies = []

    for item in records:
        if not item.get("qa_question") or not item.get("qa_context") or not item.get("qa_answer"):
            continue

        started = time.perf_counter()
        pred = qa(question=item.get("qa_question"), context=item.get("qa_context"))
        latencies.append((time.perf_counter() - started) * 1000.0)

        predicted_answer = pred.get("answer", "")
        scores.append(token_f1(predicted_answer, item.get("qa_answer")))

    return {
        "count": len(scores),
        "token_f1_avg": round(sum(scores) / len(scores), 4) if scores else None,
        "latency_ms_avg": round(statistics.mean(latencies), 2) if latencies else None,
    }


def maybe_trim_records(records, max_records):
    if max_records and max_records > 0:
        return records[:max_records]
    return records


def main():
    parser = argparse.ArgumentParser(description="Quick per-model evaluation before fine-tuning")
    parser.add_argument("--dataset", default="scripts/benchmark_dataset_example.jsonl", help="JSON/JSONL dataset path")
    parser.add_argument("--max-records", type=int, default=50, help="Max records to evaluate for speed")
    parser.add_argument(
        "--tasks",
        default="sentiment,zero_shot,ner,summarization,qa",
        help="Comma-separated tasks: sentiment,zero_shot,ner,summarization,qa",
    )
    parser.add_argument("--device", type=int, default=-1, help="Transformers device: -1 CPU, 0 GPU")
    parser.add_argument("--out", default="scripts/model_eval_report.json", help="Output JSON path")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    records = maybe_trim_records(load_records(args.dataset), args.max_records)
    requested_tasks = {x.strip().lower() for x in args.tasks.split(",") if x.strip()}

    task_models = {
        "sentiment": parse_model_candidates("SENTIMENT_MODEL", "SENTIMENT_MODEL_FALLBACKS"),
        "zero_shot": parse_model_candidates("ZERO_SHOT_MODEL", "ZERO_SHOT_MODEL_FALLBACKS"),
        "summarization": parse_model_candidates("SUMMARIZER_MODEL", "SUMMARIZER_MODEL_FALLBACKS"),
        "ner": parse_model_candidates("ITDS_NER_MODEL"),
        "qa": parse_model_candidates("ITDS_QA_MODEL"),
    }

    evaluators = {
        "sentiment": evaluate_sentiment,
        "zero_shot": evaluate_zero_shot,
        "summarization": evaluate_summarization,
        "ner": evaluate_ner,
        "qa": evaluate_qa,
    }

    report = {
        "dataset": str(args.dataset),
        "records_evaluated": len(records),
        "requested_tasks": sorted(requested_tasks),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": {},
        "errors": [],
    }

    for task_name in sorted(requested_tasks):
        if task_name not in evaluators:
            report["errors"].append({"task": task_name, "error": "unsupported task"})
            continue

        models = task_models.get(task_name, [])
        if not models:
            report["errors"].append({"task": task_name, "error": "no model configured in .env"})
            continue

        report["results"][task_name] = []

        for model_name in models:
            try:
                metric = evaluators[task_name](model_name, records, args.device)
                metric["model"] = model_name
                report["results"][task_name].append(metric)
                print(f"[OK] {task_name}: {model_name} -> {metric}")
            except Exception as exc:
                report["errors"].append({"task": task_name, "model": model_name, "error": str(exc)})
                print(f"[ERR] {task_name}: {model_name} -> {exc}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== QUICK MODEL EVALUATION COMPLETE ===")
    print(f"Saved report: {out_path}")
    if report["errors"]:
        print(f"Warnings/Errors: {len(report['errors'])}")


if __name__ == "__main__":
    main()
