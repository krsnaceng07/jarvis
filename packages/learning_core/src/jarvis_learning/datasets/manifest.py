"""jarvis_learning.datasets.manifest — dataset versioning and reproducibility.

Every dataset build produces an immutable manifest with content hashes,
split sizes, filter config, and provenance summary.  This enables:

- Exact reproduction of any training run
- Detecting evaluation contamination
- Comparing models trained on different dataset versions

The test split is immutable after creation.  The challenge split is
append-only and never used for training.
"""

from .dataset_manifest import DatasetManifest, compute_file_hash, compute_file_sha256

__all__ = [
    "DatasetManifest",
    "compute_file_hash",
    "compute_file_sha256",
]
