import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokenize(value):
    return [t for t in re.findall(r"[a-z0-9-]+", _normalize_text(value).lower()) if t]


def _token_f1(predicted, reference):
    pred_tokens = _tokenize(predicted)
    ref_tokens = _tokenize(reference)
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


def _safe_label(value):
    return _normalize_text(value).lower()


def _load_records(dataset_path):
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    if dataset_path.suffix.lower() == ".jsonl":
        records = []
        with dataset_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
        return records

    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]

    raise ValueError("Dataset must be a JSON array, JSON object with 'records', or JSONL file")


def _ner_pairs_from_gold(gold_entities):
    pairs = set()
    for item in gold_entities or []:
        text = _normalize_text(item.get("text") or item.get("word"))
        label = _safe_label(item.get("label") or item.get("entity_group") or item.get("entity"))
        if text and label:
            pairs.add((text.lower(), label.upper()))
    return pairs


def _ner_pairs_from_pred(pred_entities):
    pairs = set()
    for item in pred_entities or []:
        text = _normalize_text(item.get("word") or item.get("text"))
        label = _safe_label(item.get("entity_group") or item.get("label") or item.get("entity"))
        if text and label:
            pairs.add((text.lower(), label.upper()))
    return pairs


def _split_for_topics(text):
    chunks = [
        _normalize_text(part)
        for part in re.split(r"(?<=[.!?])\s+", _normalize_text(text))
        if _normalize_text(part)
    ]
    if len(chunks) >= 3:
        return chunks

    words = _tokenize(text)
    if len(words) < 15:
        return []

    size = max(8, math.ceil(len(words) / 3))
    synthesized = []
    for idx in range(0, len(words), size):
        chunk = " ".join(words[idx:idx + size]).strip()
        if chunk:
            synthesized.append(chunk)
        if len(synthesized) >= 3:
            break
    return synthesized


def main():
    parser = argparse.ArgumentParser(description="Quick benchmark for current pretrained ITDS AI stack")
    parser.add_argument("--dataset", required=True, help="Path to JSON/JSONL benchmark dataset")
    parser.add_argument(
        "--tasks",
        default="summarization,sentiment,ner,zero_shot,topics",
        help="Comma-separated tasks: summarization,sentiment,ner,zero_shot,topics",
    )
    parser.add_argument("--out", default="scripts/benchmark_report.json", help="Path to write report JSON")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / "itds_env" / ".env")

    requested_tasks = {task.strip().lower() for task in args.tasks.split(",") if task.strip()}

    from itds_env.app.ai.summarizer import summarize_text
    from itds_env.app.ai.ner import extract_entities
    from itds_env.app.ai.semantic_topics import extract_semantic_topics
    from itds_env.app.model_manager import get_model_cache
    from itds_env.app.ai.classifier import DOCUMENT_TYPES

    cache = get_model_cache()

    records = _load_records(args.dataset)
    if not records:
        raise ValueError("Dataset is empty")

    results = {
        "dataset_size": len(records),
        "tasks": {},
        "errors": [],
    }

    summary_scores = []
    sentiment_total = sentiment_correct = 0
    zs_total = zs_correct = 0

    ner_tp = ner_fp = ner_fn = 0
    topic_precisions = []
    topic_recalls = []

    for index, record in enumerate(records, start=1):
        text = _normalize_text(record.get("text"))
        if not text:
            results["errors"].append({"record": index, "error": "missing text"})
            continue

        try:
            if "summarization" in requested_tasks and record.get("reference_summary"):
                predicted = summarize_text(text)
                score = _token_f1(predicted, record.get("reference_summary"))
                summary_scores.append(score)

            if "sentiment" in requested_tasks and record.get("sentiment_label"):
                pred = cache.get_sentiment_pipeline()(text[:512])[0]
                pred_label = _safe_label(pred.get("label"))
                gold_label = _safe_label(record.get("sentiment_label"))
                sentiment_total += 1
                if pred_label == gold_label:
                    sentiment_correct += 1

            if "zero_shot" in requested_tasks and record.get("zero_shot_label"):
                labels = record.get("zero_shot_labels") or DOCUMENT_TYPES
                pred = cache.get_zero_shot_pipeline()(text[:1024], candidate_labels=labels, multi_label=False)
                pred_label = _safe_label((pred.get("labels") or [""])[0])
                gold_label = _safe_label(record.get("zero_shot_label"))
                zs_total += 1
                if pred_label == gold_label:
                    zs_correct += 1

            if "ner" in requested_tasks and record.get("ner_entities"):
                pred_entities = extract_entities(text)
                gold_pairs = _ner_pairs_from_gold(record.get("ner_entities"))
                pred_pairs = _ner_pairs_from_pred(pred_entities)

                ner_tp += len(gold_pairs & pred_pairs)
                ner_fp += len(pred_pairs - gold_pairs)
                ner_fn += len(gold_pairs - pred_pairs)

            if "topics" in requested_tasks and record.get("topic_keywords"):
                topic_texts = record.get("topic_texts") or _split_for_topics(text)
                pred_topics = extract_semantic_topics(topic_texts, max_topics=6, min_topic_size=2) if topic_texts else []

                pred_keywords = set()
                for topic in pred_topics:
                    for kw in topic.get("keywords", []):
                        norm = _safe_label(kw)
                        if norm:
                            pred_keywords.add(norm)

                gold_keywords = {_safe_label(k) for k in (record.get("topic_keywords") or []) if _safe_label(k)}
                if gold_keywords:
                    overlap = len(pred_keywords & gold_keywords)
                    precision = overlap / max(1, len(pred_keywords))
                    recall = overlap / max(1, len(gold_keywords))
                    topic_precisions.append(precision)
                    topic_recalls.append(recall)

        except Exception as exc:
            results["errors"].append({"record": index, "error": str(exc)})

    if "summarization" in requested_tasks and summary_scores:
        results["tasks"]["summarization"] = {
            "count": len(summary_scores),
            "token_f1_avg": round(sum(summary_scores) / len(summary_scores), 4),
        }

    if "sentiment" in requested_tasks and sentiment_total > 0:
        results["tasks"]["sentiment"] = {
            "count": sentiment_total,
            "accuracy": round(sentiment_correct / sentiment_total, 4),
        }

    if "zero_shot" in requested_tasks and zs_total > 0:
        results["tasks"]["zero_shot"] = {
            "count": zs_total,
            "accuracy": round(zs_correct / zs_total, 4),
        }

    if "ner" in requested_tasks and (ner_tp + ner_fp + ner_fn) > 0:
        precision = ner_tp / max(1, ner_tp + ner_fp)
        recall = ner_tp / max(1, ner_tp + ner_fn)
        f1 = (2 * precision * recall) / max(1e-12, precision + recall)
        results["tasks"]["ner"] = {
            "tp": ner_tp,
            "fp": ner_fp,
            "fn": ner_fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    if "topics" in requested_tasks and topic_recalls:
        results["tasks"]["topics"] = {
            "count": len(topic_recalls),
            "keyword_precision_avg": round(sum(topic_precisions) / len(topic_precisions), 4),
            "keyword_recall_avg": round(sum(topic_recalls) / len(topic_recalls), 4),
        }

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("=== PRETRAINED BENCHMARK REPORT ===")
    print(f"Dataset records: {results['dataset_size']}")
    for task_name, task_result in results["tasks"].items():
        print(f"- {task_name}: {task_result}")
    if results["errors"]:
        print(f"Errors: {len(results['errors'])} (see report)")
    print(f"Saved report: {output_path}")


if __name__ == "__main__":
    main()
