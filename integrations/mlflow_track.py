"""Persist a measured local run to an offline SQLite-backed MLflow installation."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def track(root, run_path, report_path, adapter):
    from mlflow import MlflowClient

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = run_path.read_bytes()
    run = json.loads(source)
    verdict = json.loads(report_path.read_bytes())
    weights = adapter / "adapter_model.safetensors"
    if hashlib.sha256(weights.read_bytes()).hexdigest() != run["adapters"]["dpo"]:
        raise ValueError("Adapter hash mismatch")
    uri = "sqlite:///" + str(root / "mlflow.sqlite")
    client = MlflowClient(tracking_uri=uri, registry_uri=uri)
    name = "thermal-lab-choice"
    exp = client.get_experiment_by_name(name)
    eid = (
        exp.experiment_id
        if exp
        else client.create_experiment(name, artifact_location=(root / "artifacts").as_uri())
    )
    record = client.create_run(
        eid, tags={"source_sha256": hashlib.sha256(source).hexdigest(), "scope": "independent-portfolio"}
    )
    rid = record.info.run_id
    try:
        client.log_param(rid, "base_revision", run["config"]["revision"])
        client.log_param(rid, "test_sha256", run["test_sha256"])
        for stage, accuracy in run["choices_accuracy"].items():
            client.log_metric(rid, stage + "_accuracy", accuracy)
        client.log_artifact(rid, str(report_path), "evaluation")
        for file in ("adapter_config.json", "adapter_model.safetensors"):
            client.log_artifact(rid, str(adapter / file), "adapter")
        if not any(m.name == name for m in client.search_registered_models()):
            client.create_registered_model(name)
        ver = client.create_model_version(
            name, record.info.artifact_uri + "/adapter", run_id=rid, tags={"qualification": verdict["gate"]}
        )
        client.set_registered_model_alias(name, "candidate", ver.version)
        client.set_terminated(rid)
        return dict(
            run_id=rid,
            model=name,
            version=ver.version,
            alias="candidate",
            gate=verdict["gate"],
            registry_backend="local SQLite",
            metrics=client.get_run(rid).data.metrics,
        )
    except Exception:
        client.set_terminated(rid, status="FAILED")
        raise


if __name__ == "__main__":
    os.environ["MLFLOW_ENABLE_ASYNC_LOGGING"] = "false"
    p = argparse.ArgumentParser()
    for k in ("root", "run", "report", "adapter", "output"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    a.output.write_text(json.dumps(track(a.root, a.run, a.report, a.adapter), indent=2) + "\n")
