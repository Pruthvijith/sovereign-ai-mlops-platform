# Design decision and review guide

## Decision record 001

Use a transactional state machine because evidence arrives from multiple local stages. The database is also the local artifact store for these small adapter files. Its HMAC detects inconsistent artifacts under a trusted signer. The demonstration does not isolate a malicious database administrator or offer independent signing authority. MLflow is a tracking mirror. The transactional registry owns promotion decisions.

## Operational response

Stop promotion on a changed artifact digest, changed prediction file, failed policy replay or held evaluation. For an active deployment, call Registry.rollback with the expected current release ID. The operation verifies the previous artifact in the same transaction and records the transition. Limit filesystem and key access to the release operator. Network identity, independent approvers and disaster-recovery testing remain open.

## Interview practice

Use these answers after reproducing the experiment. Describe the work as an AI-assisted independent portfolio project.

### Why verify twice?

A written report can be replaced between training and promotion. I verify the input digests, replay the scorer and sign the canonical result before registration.

### What protects concurrent rollback?

BEGIN IMMEDIATE serializes the writer. The API compares the active ID to the expected current version, verifies the target and records the pointer change and audit event in the same transaction.

### What is missing for a sovereign production deployment?

Separate signing and serving identities, audited key management, backups with restoration tests, independent operators and load tests. Running offline establishes only one part of the requirement.

