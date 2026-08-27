"""Extract per-case review data from a competition-evaluation run into a compact JSON.

Output fields are chosen to support the human review checklist:
facts, hallucination, difficulty, knowledge coverage, citations, system action.
"""
import argparse
import json
import os


def _brief(obj, limit=4000):
    s = json.dumps(obj, ensure_ascii=False, indent=1)
    return s if len(s) <= limit else s[:limit] + "\n...[truncated]"


def extract_run(run_dir):
    raw_dir = os.path.join(run_dir, "raw")
    results_dir = os.path.join(run_dir, "results")
    cases = []
    for name in sorted(os.listdir(raw_dir)):
        if not name.startswith("case-") or not name.endswith(".json"):
            continue
        case_id = name[len("case-"):-len(".json")]
        raw = json.load(open(os.path.join(raw_dir, name), encoding="utf-8"))
        res = json.load(open(os.path.join(results_dir, name), encoding="utf-8"))
        c = raw.get("case", {})

        # expected
        exp = c.get("expected", {})
        judgment = c.get("judgment", {})

        # actual output
        actual = res.get("actual_output", {}) or {}
        echo_reply = actual.get("echo_reply")
        degradation = actual.get("degradation") or []
        resource = actual.get("selected_resource")
        requested_resource_type = actual.get("requested_resource_type")

        citations = res.get("citations") or []
        resource_record = res.get("resource_record")
        human_review = res.get("human_review") or {}
        metric_flags = res.get("metric_flags") or {}
        metric_evidence = res.get("metric_evidence") or {}
        failure_reasons = res.get("failure_reasons") or []

        # resources payload in raw (resource generation evidence)
        resources_payload = raw.get("resources", {}).get("payload")
        turns_payload = raw.get("turns", {}).get("payload", {})
        turn_items = turns_payload.get("items") or []

        agent_records = res.get("agent_records") or {}

        cases.append({
            "case_id": case_id,
            "learner_type": c.get("learner_type"),
            "module": c.get("module"),
            "knowledge_point": c.get("knowledge_point"),
            "scenario_type": c.get("scenario_type"),
            "input": c.get("input"),
            "expected": exp,
            "judgment": judgment,
            "status": res.get("status"),
            "actual": {
                "intent": actual.get("intent"),
                "primary_action": actual.get("primary_action"),
                "echo_reply": echo_reply,
                "degradation": degradation,
                "requested_resource_type": requested_resource_type,
                "selected_resource": resource,
                "all_resource_count": actual.get("all_resource_count"),
            },
            "citations": citations,
            "resource_record": resource_record,
            "agent_records_keys": list(agent_records.keys()) if isinstance(agent_records, dict) else None,
            "human_review": {
                "status": human_review.get("status"),
                "reviewers": human_review.get("reviewers"),
            },
            "metric_flags": metric_flags,
            "metric_evidence": metric_evidence,
            "failure_reasons": failure_reasons,
            "resources_payload": _brief(resources_payload, 2500) if resources_payload else None,
            "turn_items": _brief(turn_items, 2500) if turn_items else None,
        })
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cases = extract_run(args.run_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=1)
    print(f"extracted {len(cases)} cases -> {args.out}")


if __name__ == "__main__":
    main()
