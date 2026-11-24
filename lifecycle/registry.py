"""Local registry for a single deployment target. SQLite serializes pointer changes."""

from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    dataset_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    evaluation_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    gate: Literal["hold", "pass"]
    policy: str = Field(min_length=1, max_length=120)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sign(evidence: Evidence, secret: bytes) -> str:
    if len(secret) < 32:
        raise ValueError("Use at least 32 bytes of secret material")
    body = json.dumps(evidence.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


class Registry:
    def __init__(self, path: Path, secret: bytes):
        if len(secret) < 32:
            raise ValueError("Missing release signing key")
        self.path, self.secret = path, secret
        with self.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY, artifact BLOB NOT NULL,evidence TEXT NOT NULL,signature TEXT NOT NULL,stage TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS deployment(slot TEXT PRIMARY KEY,release_id TEXT REFERENCES releases(id))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,at TEXT DEFAULT CURRENT_TIMESTAMP,action TEXT,release_id TEXT,previous TEXT)"
            )

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        finally:
            db.close()

    def register(self, artifact: bytes, e: Evidence, signature: str) -> str:
        if digest(artifact) != e.artifact_sha256 or not hmac.compare_digest(sign(e, self.secret), signature):
            raise ValueError("Artifact or attestation mismatch")
        rid = digest((e.artifact_sha256 + signature).encode())
        with self.transaction() as db:
            added = db.execute(
                "INSERT OR IGNORE INTO releases VALUES(?,?,?,?,?)",
                (rid, artifact, e.model_dump_json(), signature, "development"),
            )
            if added.rowcount:
                self.event(db, "registered", rid)
        return rid

    @staticmethod
    def event(db, action, rid, previous=None):
        db.execute("INSERT INTO audit(action,release_id,previous) VALUES(?,?,?)", (action, rid, previous))

    def verified(self, db, rid):
        row = db.execute(
            "SELECT artifact,evidence,signature,stage FROM releases WHERE id=?", (rid,)
        ).fetchone()
        if not row:
            raise KeyError(rid)
        raw, evidence, signature, stage = row
        e = Evidence.model_validate_json(evidence)
        if digest(raw) != e.artifact_sha256 or not hmac.compare_digest(sign(e, self.secret), signature):
            raise ValueError("Integrity verification failed")
        return raw, e, stage

    def promote(self, rid, stage):
        before = {"testing": "development", "staging": "testing", "production-like": "staging"}
        if stage not in before:
            raise ValueError("Unknown stage")
        with self.transaction() as db:
            _, e, current = self.verified(db, rid)
            if stage == current:
                return
            if before[stage] != current or (stage != "testing" and e.gate != "pass"):
                raise ValueError("Release gate blocked transition")
            previous = None
            if stage == "production-like":
                previous = self.active(db)
                db.execute("INSERT OR REPLACE INTO deployment VALUES('local',?)", (rid,))
            db.execute("UPDATE releases SET stage=? WHERE id=?", (stage, rid))
            self.event(db, stage, rid, previous)

    @staticmethod
    def active(db):
        row = db.execute("SELECT release_id FROM deployment WHERE slot='local'").fetchone()
        return row[0] if row else None

    def rollback(self, expected_current):
        with self.transaction() as db:
            current = self.active(db)
            if not current or current != expected_current:
                raise ValueError("Deployment changed")
            prior = db.execute(
                "SELECT previous FROM audit WHERE action='production-like' AND release_id=? ORDER BY seq DESC LIMIT 1",
                (current,),
            ).fetchone()
            if not prior or not prior[0]:
                raise ValueError("No earlier deployment")
            target = prior[0]
            _, e, stage = self.verified(db, target)
            if stage != "production-like" or e.gate != "pass":
                raise ValueError("Unqualified rollback target")
            db.execute("UPDATE deployment SET release_id=? WHERE slot='local'", (target,))
            self.event(db, "rollback", target, current)
            return target

    def audit(self):
        with self.transaction() as db:
            return db.execute("SELECT seq,at,action,release_id,previous FROM audit ORDER BY seq").fetchall()
