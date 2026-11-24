"""Attest externally generated evidence after verifying its binding to the run."""

import argparse
import json
import os
from pathlib import Path
from .registry import Registry, Evidence, digest, sign


def attest(run_path, report_path, artifact_path, predictions_path, baseline_path, score):
    run = json.loads(run_path.read_bytes())
    raw = report_path.read_bytes()
    report = json.loads(raw)
    artifact = artifact_path.read_bytes()
    if run["adapters"]["dpo"] != digest(artifact):
        raise ValueError("Adapter mismatch")
    if report["input_sha256"] != {
        "baseline": digest(baseline_path.read_bytes()),
        "candidate": digest(predictions_path.read_bytes()),
    }:
        raise ValueError("Prediction inputs changed")
    if report["n"] != run["test_n"] or report["gate"] not in {"hold", "pass"}:
        raise ValueError("Invalid evaluation reference")
    if (
        run["prediction_sha256"]["base"] != report["input_sha256"]["baseline"]
        or run["prediction_sha256"]["dpo"] != report["input_sha256"]["candidate"]
    ):
        raise ValueError("Run and scorer identify different predictions")
    rows = json.loads(predictions_path.read_bytes())
    recomputed = score(json.loads(baseline_path.read_bytes()), rows)
    if recomputed != {k: v for k, v in report.items() if k != "input_sha256"}:
        raise ValueError("Policy replay disagrees with report")
    reconstructed = [{k: r[k] for k in ("id", "group", "kind", "prompt", "target", "rejected")} for r in rows]
    if (
        digest(json.dumps(reconstructed, sort_keys=True, separators=(",", ":")).encode())
        != run["test_sha256"]
    ):
        raise ValueError("Evaluation data differs from run")
    e = Evidence(
        artifact_sha256=digest(artifact),
        dataset_sha256=run["test_sha256"],
        evaluation_sha256=digest(raw),
        gate=report["gate"],
        policy="engineering-choice/v1",
    )
    return artifact, e


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("run", "report", "adapter", "candidate", "baseline", "database"):
        p.add_argument(key, type=Path)
    args = p.parse_args()
    secret = os.environ["RELEASE_KEY"].encode()
    from evaluation.score import compare

    artifact, e = attest(args.run, args.report, args.adapter, args.candidate, args.baseline, compare)
    reg = Registry(args.database, secret)
    rid = reg.register(artifact, e, sign(e, secret))
    reg.promote(rid, "testing")
    if e.gate == "pass":
        reg.promote(rid, "staging")
        reg.promote(rid, "production-like")
    print(json.dumps(dict(gate=e.gate, audit=reg.audit()), indent=2))
