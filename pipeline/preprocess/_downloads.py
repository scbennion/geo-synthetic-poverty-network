"""Shared streaming downloader for roads, LODES, and County Business Patterns."""
import os

import requests
from loguru import logger


def download_file(url, output_path, verify_ssl=True):
    """Download ``url`` to ``output_path``; returns True on success, False on error.

    TLS certificates are verified unless ``verify_ssl=False`` is passed. The file is
    written to ``<output_path>.part`` and renamed only when complete, so a failed
    download never leaves a truncated file that later looks cached.
    """
    part_path = f"{output_path}.part"
    try:
        response = requests.get(url, stream=True, verify=verify_ssl, timeout=60)
        response.raise_for_status()

        with open(part_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        os.replace(part_path, output_path)
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading {url}: {e}")
        if os.path.exists(part_path):
            os.remove(part_path)
        return False
