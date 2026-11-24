# Local ML release qualification

Bind a candidate adapter to its dataset, predictions and an independently replayed qualification policy. Store the release record, gate transitions and audit history in a transactional local registry.

Independent, AI-assisted portfolio research milestone · v0.1.0 · Python 3.12 · CPU reference environment.

## Measured outcome

The actual DPO candidate registered and reached testing. The scoring policy prevented staging and production-like promotion. MLflow registered version 1 with the candidate alias and stored the hold verdict. Tests exercise concurrent idempotent registration, forged or altered evidence, stage skipping, two positive fixture promotions and compare-and-set rollback.

## Architecture and data flow

The release command verifies the adapter and both prediction hashes against the training run. It reconstructs the dataset digest, replays the external scorer and signs a canonical evidence statement using a local HMAC key. SQLite transactions serialize promotion and rollback. MLflow records the experiment metrics, artifact and candidate version. The portfolio runner catalogs outputs from all five upstream projects.

## Dataset and model usage contract

The integration consumes the genuine DPO artifact and report. Qualified versions used in rollback tests are synthetic fixtures. They establish state-transition behavior only. The local demonstration generates an ephemeral signing secret. An operating deployment needs a persistent managed secret and a documented rotation procedure.

The supported purpose is offline research and human-reviewed engineering decision support. Aviation design approval, operational aircraft decisions and regulated certification are outside the validated scope.

## Reproduce

Run from this checkout on Linux x86-64. The reference CPU was an AMD EPYC 9V74. The portfolio index includes a downloader for the pinned models and UCI input.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints-cpu.txt -r requirements-dev.txt
python -m pytest -q
# From the index checkout, run tools/reproduce.py for the measured lifecycle.
```

## Testing and deployment

```bash
python -m pytest --cov=lifecycle --cov-report=term-missing
python -m ruff check .
python -m mypy lifecycle
```

For the qualification command install the sibling evaluation project in the same environment, or make its directory available on PYTHONPATH. Set RELEASE_KEY to at least 32 random bytes encoded as text. Run python -m lifecycle.qualify RUN_JSON SCORE_JSON DPO_SAFETENSORS DPO_PREDICTIONS BASE_PREDICTIONS REGISTRY_SQLITE. Registering the same signed input is idempotent. To enable the local MLflow mirror, install requirements-mlflow.txt and use python -m integrations.mlflow_track STORE RUN_JSON SCORE_JSON ADAPTER_DIRECTORY OUTPUT_JSON. Each explicit tracking invocation creates a new experiment run and model version.

## Operations and next validation

Stop promotion on a changed artifact digest, changed prediction file, failed policy replay or held evaluation. For an active deployment, call Registry.rollback with the expected current release ID. The operation verifies the previous artifact in the same transaction and records the transition. Limit filesystem and key access to the release operator. Network identity, independent approvers and disaster-recovery testing remain open.

See [decisions and interview guide](docs/review.md) and the measured files in [reports](reports/). Hosted CI and production qualification require their own evidence. For dependencies and known advisories see the portfolio index security report.

## Provenance and licensing

Original code and original fixtures use Apache-2.0. Upstream models, data and third-party executables retain their own licences. External weights and source archives are fetched separately. References follow.

- https://mlflow.org/docs/latest/ml/model-registry/
- https://www.sqlite.org/lang_transaction.html

## Local verification

3 tests passed. Statement coverage of the lifecycle package was 85.11%. Ruff and mypy passed. See [verification record](reports/verification.json).
