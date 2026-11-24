from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from lifecycle.registry import Evidence, Registry, digest, sign
from lifecycle.qualify import attest


def item(reg, raw, gate="pass"):
    e = Evidence(
        artifact_sha256=digest(raw),
        dataset_sha256=digest(b"data"),
        evaluation_sha256=digest(b"eval"),
        gate=gate,
        policy="fixture",
    )
    return reg.register(raw, e, sign(e, reg.secret))


def test_qualified_rollback_and_cas(tmp_path):
    r = Registry(tmp_path / "db", b"x" * 32)
    ids = [item(r, b"one"), item(r, b"two")]
    for rid in ids:
        for stage in ("testing", "staging", "production-like"):
            r.promote(rid, stage)
    assert r.rollback(ids[1]) == ids[0]
    with pytest.raises(ValueError):
        r.rollback(ids[1])
    with pytest.raises(ValueError):
        r.rollback(ids[0])
    assert r.audit()[-1][2] == "rollback"


def test_idempotent_hold_and_integrity(tmp_path):
    r = Registry(tmp_path / "db", b"y" * 32)
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda _: item(r, b"held", "hold"), range(8)))
    assert len(set(ids)) == 1 and len(r.audit()) == 1
    rid = ids[0]
    r.promote(rid, "testing")
    r.promote(rid, "testing")
    for stage in ("staging", "other"):
        with pytest.raises(ValueError):
            r.promote(rid, stage)
    with r.transaction() as db:
        db.execute("UPDATE releases SET artifact=?", (b"modified",))
    with pytest.raises(ValueError):
        r.promote(rid, "staging")
    with pytest.raises(KeyError):
        r.promote("missing", "testing")
    with pytest.raises(ValueError):
        Registry(tmp_path / "bad", b"x")


def test_attestation_and_replay(tmp_path):
    row = dict(id="a", group="G", kind="W", prompt="question", target="A", rejected="B")
    pred = tmp_path / "pred"
    pred.write_text(json.dumps([{**row, "prediction": "A"}]))
    baseline = tmp_path / "base"
    baseline.write_bytes(pred.read_bytes())
    adapter = tmp_path / "adapter"
    adapter.write_bytes(b"trained-fixture")
    short = {"n": 1, "gate": "hold"}
    report = tmp_path / "report"
    report.write_text(
        json.dumps(
            {**short, "input_sha256": {k: digest(pred.read_bytes()) for k in ("baseline", "candidate")}}
        )
    )
    run = tmp_path / "run"
    run.write_text(
        json.dumps(
            dict(
                test_n=1,
                adapters={"dpo": digest(adapter.read_bytes())},
                prediction_sha256={k: digest(pred.read_bytes()) for k in ("base", "dpo")},
                test_sha256=digest(json.dumps([row], sort_keys=True, separators=(",", ":")).encode()),
            )
        )
    )
    raw, e = attest(run, report, adapter, pred, baseline, lambda a, b: short)
    assert e.gate == "hold" and raw == b"trained-fixture"
    with pytest.raises(ValueError):
        attest(run, report, adapter, pred, baseline, lambda a, b: {**short, "gate": "pass"})
    adapter.write_bytes(b"altered")
    with pytest.raises(ValueError):
        attest(run, report, adapter, pred, baseline, lambda a, b: short)
