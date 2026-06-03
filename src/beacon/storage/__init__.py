"""beacon.storage — artifact I/O abstraction layer.

Public API:
    StorageBackend   Abstract base class (backend.py)
    LocalStorage     Filesystem implementation (local.py)
    GCSStorage       Google Cloud Storage implementation (gcs.py)
    create_storage_backend   Factory function — picks impl from Config

Usage::

    from beacon.storage import create_storage_backend
    from beacon.config import load_config

    storage = create_storage_backend(load_config())
    storage.save("pir", "pir_output_202605251700.json", json_str)
    content = storage.load("pir", "pir_output_202605251700.json")
    files = storage.list_files("pir")
    found = storage.exists("pir", "pir_output_202605251700.json")
"""

from __future__ import annotations

from .backend import StorageBackend
from .local import LocalStorage

__all__ = [
    "StorageBackend",
    "LocalStorage",
    "GCSStorage",
    "create_storage_backend",
]


def create_storage_backend(config: object) -> StorageBackend:
    """Instantiate and return a StorageBackend based on *config*.

    Args:
        config: A ``beacon.config.Config`` instance (typed as object to
                avoid circular imports; duck-typed access only).

    Returns:
        LocalStorage  when ``config.storage_backend == "local"`` (default).
        GCSStorage    when ``config.storage_backend == "gcs"``.

    Raises:
        ValueError:   If ``storage_backend`` is set to an unknown value.
        ImportError:  If ``storage_backend == "gcs"`` and
                      ``google-cloud-storage`` is not installed.
    """
    backend_name: str = getattr(config, "storage_backend", "local")

    if backend_name == "local":
        base_dir: str = getattr(config, "storage_base_dir", "output")
        return LocalStorage(base_dir=base_dir)

    if backend_name == "gcs":
        from .gcs import GCSStorage  # deferred — optional dependency

        bucket: str = getattr(config, "storage_bucket", "")
        if not bucket:
            raise ValueError("BEACON_STORAGE_BUCKET must be set when BEACON_STORAGE=gcs")
        prefix: str = getattr(config, "storage_prefix", "")
        return GCSStorage(bucket=bucket, prefix=prefix)

    raise ValueError(f"Unknown storage backend '{backend_name}'. Valid values: 'local', 'gcs'.")


# Re-export GCSStorage lazily so `from beacon.storage import GCSStorage`
# still works without importing google-cloud-storage at module load time.
def __getattr__(name: str) -> object:
    if name == "GCSStorage":
        from .gcs import GCSStorage  # noqa: PLC0415

        return GCSStorage
    raise AttributeError(f"module 'beacon.storage' has no attribute {name!r}")
