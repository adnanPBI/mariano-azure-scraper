"""Crash-safe checkpoint and last-known-good publication for local and Azure Blob.

Only successful, versioned exports are referenced from /published/{store}/latest.json.
An interrupted or failed run cannot replace the pointer.
"""
from __future__ import annotations
import contextlib
try:
    import fcntl  # POSIX
except ImportError:
    fcntl = None  # Windows uses msvcrt byte-range locking
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Iterator
from .publication import require_positive_publication

LOG=logging.getLogger(__name__)

class Locked(RuntimeError):
    pass
class LostLease(RuntimeError):
    pass

class LocalStorage:
    def __init__(self,root:str):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
    def _path(self,key:str)->Path:
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("unsafe key")
        p=(self.root/key).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("unsafe storage location")
        return p
    def get_json(self,key:str):
        p=self._path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    def get_json_versioned(self,key:str):
        value=self.get_json(key)
        # Local lock provides consistency; no remote ETag needed.
        return value,None
    def publish_pointer(self,key:str,value:dict,version):
        require_positive_publication(value)
        self.put_json(key,value)
    def put_json(self,key:str,value:dict|list):
        self.put_bytes(key,json.dumps(value,ensure_ascii=False,separators=(",",":"),indent=None).encode("utf-8"))
    def put_bytes(self,key:str,value:bytes):
        p=self._path(key);p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_name(p.name+f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with tmp.open("wb") as fp:
                fp.write(value);fp.flush();os.fsync(fp.fileno())
            # Synchronous, caller-owned rename; never delegate positive publish
            # to a worker which could finish after a timeout/cancellation.
            os.replace(tmp,p)
        finally:
            # A pre-rename failure must not leave a staging file that might
            # later be mistaken for a completed publishable artifact.
            tmp.unlink(missing_ok=True)
    @contextlib.contextmanager
    def lease(self,store_id:str)->Iterator[None]:
        """Nonblocking, per-store, OS-native file lock on POSIX and Windows.

        The lock lifetime is the file-handle lifetime and does not modify shared
        Python installations or depend on a third-party library.
        """
        p=self._path(f"locks/{store_id}.lock")
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open("a+b") as fp:
            if os.name == "nt":
                import msvcrt
                # Windows locks the byte at the current seek position.
                fp.seek(0,os.SEEK_END)
                if fp.tell()==0:
                    fp.write(b"\0");fp.flush();os.fsync(fp.fileno())
                fp.seek(0)
                try:msvcrt.locking(fp.fileno(),msvcrt.LK_NBLCK,1)
                except OSError as exc:
                    raise Locked(f"another run holds store lock {store_id}") from exc
                try:yield
                finally:
                    fp.seek(0)
                    msvcrt.locking(fp.fileno(),msvcrt.LK_UNLCK,1)
            else:
                try:fcntl.flock(fp,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise Locked(f"another run holds store lock {store_id}") from exc
                try:yield
                finally:fcntl.flock(fp,fcntl.LOCK_UN)
    def assert_healthy(self):pass

class AzureStorage:
    """Managed identity (preferred) or env-injected connection string; no hardcoded secret."""
    def __init__(self,container_name:str,account_name:str|None=None,connection_string:str|None=None):
        from azure.storage.blob import BlobServiceClient
        from azure.core.exceptions import ResourceExistsError
        if connection_string:
            client=BlobServiceClient.from_connection_string(connection_string)
        elif account_name:
            from azure.identity import DefaultAzureCredential
            client=BlobServiceClient(f"https://{account_name}.blob.core.windows.net",credential=DefaultAzureCredential())
        else:
            raise ValueError("set AZURE_STORAGE_ACCOUNT or AZURE_STORAGE_CONNECTION_STRING")
        self.container=client.get_container_client(container_name)
        try:self.container.create_container()
        except ResourceExistsError:pass
        self._lease_health=True
    def get_json(self,key:str):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            raw=self.container.download_blob(key).readall()
        except ResourceNotFoundError:
            return None
        return json.loads(raw)
    def get_json_versioned(self,key:str):
        from azure.core.exceptions import ResourceNotFoundError
        client=self.container.get_blob_client(key)
        try:
            download=client.download_blob()
            value=json.loads(download.readall())
            version=client.get_blob_properties().etag
            return value,version
        except ResourceNotFoundError:
            return None,None
    def publish_pointer(self,key:str,value:dict,version):
        from azure.core import MatchConditions
        require_positive_publication(value)
        self.assert_healthy()
        blob=self.container.get_blob_client(key)
        payload=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode("utf-8")
        if version:
            blob.upload_blob(payload,overwrite=True,etag=version,match_condition=MatchConditions.IfNotModified,
                             content_settings=self._content_type(key))
        else:
            # First published run may create the pointer; racing creator will fail.
            blob.upload_blob(payload,overwrite=False,content_settings=self._content_type(key))
    def put_json(self,key:str,value:dict|list):
        self.put_bytes(key,json.dumps(value,ensure_ascii=False,separators=(",",":")).encode("utf-8"))
    def put_bytes(self,key:str,value:bytes):
        self.assert_healthy()
        # Each block blob PUT is atomic; pointer is updated only after all units pass.
        self.container.upload_blob(name=key,data=value,overwrite=True,content_settings=self._content_type(key))
    @staticmethod
    def _content_type(key):
        from azure.storage.blob import ContentSettings
        return ContentSettings(content_type="application/json" if key.endswith(".json") else "application/octet-stream")
    @contextlib.contextmanager
    def lease(self,store_id:str)->Iterator[None]:
        """60s lease renewed every 20s; worker aborts on any lost renewal."""
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
        blob=self.container.get_blob_client(f"locks/{store_id}.lock")
        try:blob.upload_blob(b"per-store-job-lock",overwrite=False)
        except ResourceExistsError:pass
        try:
            lease=blob.acquire_lease(lease_duration=60)
        except ResourceModifiedError as exc:
            raise Locked(f"store {store_id} already leased") from exc
        self._lease_health=True
        stop=threading.Event()
        def renew():
            while not stop.wait(20):
                try:lease.renew()
                except Exception as exc:
                    LOG.error("lease_renew_failed",extra={"store":store_id,"error":str(exc)})
                    self._lease_health=False
                    return
        thread=threading.Thread(target=renew,name="azure-lease-renewer",daemon=True)
        thread.start()
        try:
            yield
            self.assert_healthy()
        finally:
            stop.set();thread.join(timeout=5)
            try:lease.release()
            except Exception:LOG.exception("lease_release_failed")
    def assert_healthy(self):
        if not self._lease_health:
            raise LostLease("Azure lease lost; refusing to publish any output")

def make_storage():
    backend=os.getenv("SCRAPER_STORAGE","local").lower()
    if backend=="local":
        return LocalStorage(os.getenv("SCRAPER_DATA_DIR","./local-state"))
    if backend=="azure":
        container=os.environ.get("AZURE_STORAGE_CONTAINER", "marianos-crawls")
        return AzureStorage(container,os.environ.get("AZURE_STORAGE_ACCOUNT"),os.environ.get("AZURE_STORAGE_CONNECTION_STRING"))
    raise ValueError(f"unsupported SCRAPER_STORAGE={backend}")