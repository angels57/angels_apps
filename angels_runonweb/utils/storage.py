"""Model and runtime files kept by the server, under <data_dir>/angels_runonweb.

They are shared by every database of the instance: the files are public open weights,
identified by their pinned revision, so there is nothing per company to separate.
"""

import hashlib
import logging
import os
import tempfile

import requests

from odoo.tools import config

_logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024
TIMEOUT = (10, 60)


class StorageError(Exception):
    """A file of the storage folder could not be written or deleted."""


class DownloadError(StorageError):
    pass


def root():
    return os.path.join(config["data_dir"], "angels_runonweb")


def local_path(entry):
    # Catalog paths are fixed strings, never user input; normpath only tidies separators.
    return os.path.normpath(os.path.join(root(), entry.kind, *entry.path.split("/")))


def is_present(entry):
    """Cheap check used on every request: the file exists with the expected size."""
    try:
        return os.path.getsize(local_path(entry)) == entry.size
    except OSError:
        return False


def download(entry, session=None):
    """Fetch one catalog file into the storage folder, checking size and SHA-256.

    Writes to a temporary file next to the target and renames it at the end, so a
    browser never receives half a file and a failed download leaves nothing behind.
    """
    target = local_path(entry)
    folder = os.path.dirname(target)
    digest = hashlib.sha256()
    received = 0
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".part-")
    except OSError as error:
        raise DownloadError(f"cannot write in {folder}: {error.strerror or error}") from error
    try:
        with os.fdopen(fd, "wb") as out:
            response = (session or requests).get(entry.remote_url, stream=True, timeout=TIMEOUT)
            if response.status_code != 200:
                raise DownloadError(f"{entry.remote_url} answered {response.status_code}")
            for chunk in response.iter_content(CHUNK):
                received += len(chunk)
                if received > entry.size:
                    raise DownloadError(f"{entry.path} is larger than expected")
                digest.update(chunk)
                out.write(chunk)
        if received != entry.size or digest.hexdigest() != entry.sha256:
            raise DownloadError(f"{entry.path} does not match the expected checksum")
        os.replace(tmp, target)
    except requests.RequestException as error:
        raise DownloadError(f"{entry.remote_url}: {error}") from error
    except OSError as error:
        # Disk full, permissions, read-only folder: a clear message, not a server error.
        raise DownloadError(f"cannot write {entry.path}: {error.strerror or error}") from error
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    _logger.info("angels_runonweb: downloaded %s (%s bytes)", entry.path, received)


def remove(entry):
    try:
        os.unlink(local_path(entry))
    except FileNotFoundError:
        pass
    except OSError as error:
        raise StorageError(f"cannot delete {entry.path}: {error.strerror or error}") from error
