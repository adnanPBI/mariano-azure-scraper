"""Walmart v0.5.7 publication lessons adapted to local Mariano's storage.

Offline fault-injection only: no Mariano's requests, paid requests, or Azure.
The synchronous OS rename is NOT claimed to be a hard-bounded deadline.
"""
import os
import threading
from hashlib import sha256
from datetime import datetime, timezone
import pytest

from marianos_scraper.storage import LocalStorage
from marianos_scraper.publication import require_positive_publication


def manifest(store="test-store", slot="2026-11-02", data=b"offline fixture"):
    digest = sha256(data).hexdigest()
    return {
        "status": "passed", "published": True, "records": 1,
        "store_id": store, "slot": slot, "sha256": digest,
        "dataset_key": f"exports/{store}/{slot}/catalog-{digest[:16]}.json",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def test_pending_failed_or_incomplete_manifest_never_publishes(tmp_path):
    db = LocalStorage(str(tmp_path))
    key = "published/test-store/latest.json"
    old = manifest(data=b"previous")
    db.publish_pointer(key, old, None)
    for changes in (
        {"status": "PENDING"}, {"status": "failed"}, {"published": False},
        {"records": 0}, {"sha256": "bogus"}, {"dataset_key": "wrong"},
        {"published_at": ""},
    ):
        bad = {**manifest(data=b"new"), **changes}
        with pytest.raises(ValueError):
            db.publish_pointer(key, bad, None)
        assert db.get_json(key) == old


def test_before_rename_exception_preserves_last_success(tmp_path, monkeypatch):
    db = LocalStorage(str(tmp_path))
    key = "published/test-store/latest.json"
    old = manifest(data=b"previous")
    db.publish_pointer(key, old, None)
    real = os.replace

    def fail_before_replace(src, dst):
        if str(dst).endswith("latest.json"):
            raise OSError("offline injected pre-rename filesystem failure")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", fail_before_replace)
    with pytest.raises(OSError, match="pre-rename"):
        db.publish_pointer(key, manifest(data=b"new"), None)
    assert db.get_json(key) == old


def test_sync_before_rename_stall_does_not_publish_early(tmp_path, monkeypatch):
    db = LocalStorage(str(tmp_path))
    key = "published/test-store/latest.json"
    old = manifest(data=b"previous")
    new = manifest(data=b"new")
    db.publish_pointer(key, old, None)
    real = os.replace
    reached, proceed = threading.Event(), threading.Event()
    results = []

    def stalled_replace(src, dst):
        if str(dst).endswith("latest.json"):
            reached.set()
            assert proceed.wait(3), "fixture timeout"
        return real(src, dst)

    monkeypatch.setattr(os, "replace", stalled_replace)
    thread = threading.Thread(target=lambda: (db.publish_pointer(key, new, None), results.append("done")))
    thread.start()
    try:
        assert reached.wait(3)
        assert db.get_json(key) == old
        assert thread.is_alive()
    finally:
        proceed.set()
        thread.join(4)
    assert not thread.is_alive()
    assert results == ["done"]
    assert db.get_json(key) == new


def test_sync_after_rename_stall_does_not_claim_hard_runtime_limit(tmp_path, monkeypatch):
    db = LocalStorage(str(tmp_path))
    key = "published/test-store/latest.json"
    new = manifest(data=b"new")
    reached, proceed = threading.Event(), threading.Event()
    real = os.replace
    results = []

    def after_real_replace(src, dst):
        real(src, dst)
        if str(dst).endswith("latest.json"):
            reached.set()
            assert proceed.wait(3), "fixture timeout"

    monkeypatch.setattr(os, "replace", after_real_replace)
    thread = threading.Thread(target=lambda: (db.publish_pointer(key, new, None), results.append("done")))
    thread.start()
    try:
        assert reached.wait(3)
        assert thread.is_alive()
        # The atomic rename occurred, but the caller has not returned.
        # Unlike Walmart's paid diagnostic, this is a synchronous publication
        # with no cancellation/deadline claim; do not invent a timeout.
        assert db.get_json(key) == new
    finally:
        proceed.set()
        thread.join(4)
    assert not thread.is_alive()
    assert results == ["done"]


def test_strict_dataset_key_binds_store_slot_and_digest():
    good = manifest()
    require_positive_publication(good)
    for value in ("exports/other/2026-11-02/catalog-" + good["sha256"][:16] + ".json",
                  "../../published/another/latest.json"):
        with pytest.raises(ValueError):
            require_positive_publication({**good, "dataset_key": value})