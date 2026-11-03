"""
FormAI Dataset Collector & Ingestion Pipeline.

Automates the collection, trimming, validation, and feature extraction of diverse
multi-lifter exercise videos for ML training and validation.
"""
import os
import sys

# Ensure backend directory is in sys.path
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.ml.dataset_collector.manifest import ClipEntry, DatasetManifest
from backend.ml.dataset_collector.downloader import VideoDownloader
from backend.ml.dataset_collector.validator import VideoValidator

__all__ = ["ClipEntry", "DatasetManifest", "VideoDownloader", "VideoValidator"]
