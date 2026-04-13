from __future__ import annotations

from pathlib import Path

import kagglehub


def main() -> None:
    path = Path(
        kagglehub.dataset_download("kaggleprollc/phishing-url-websites-dataset-phiusiil")
    )
    print(f"Path to dataset files: {path}")

    csv_files = sorted(path.glob("*.csv"))
    if csv_files:
        print(f"CSV to train on: {csv_files[0]}")
        print(f"Train command: python train.py --data {csv_files[0]} --phishing-label 0")


if __name__ == "__main__":
    main()
