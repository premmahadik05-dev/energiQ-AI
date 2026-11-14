"""Where the society-level data comes from, and how it is fetched and recorded.

The only data source used is the Building Data Genome 2 (BDG2) open data set: measured hourly
electricity meters of real buildings (Miller et al., Scientific Data 7, 368, 2020). Nothing in this
project is simulated. A "society" here is a *research-based representative community*: the real
residential-use buildings of one BDG2 site, summed per hour (see docs/17_society_methodology.md).

``download_bdg2`` fetches the files over HTTPS, stores them next to a provenance record (URL, size,
SHA-256, download date) and refuses to continue if a file is not a real data file (the repository
keeps its large files in Git LFS, so a pointer file must never be mistaken for data).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

LFS_MEDIA = "https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/master"
RAW_GITHUB = "https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/master"

# (relative path, uses Git LFS)
BDG2_FILES: tuple[tuple[str, bool], ...] = (
    ("data/metadata/metadata.csv", True),
    ("data/weather/weather.csv", True),
    ("data/meters/raw/electricity.csv", True),
    ("LICENSE", False),
    ("README.md", False),
)

BDG2_CARD = {
    "key": "bdg2",
    "name": "Building Data Genome Project 2 (BDG2)",
    "publisher": "Building and Urban Data Science (BUDS) Lab, National University of Singapore, with the ASHRAE Great Energy Predictor III organisers",
    "official_url": "https://github.com/buds-lab/building-data-genome-project-2",
    "paper": "Miller, C., Kathirgamanathan, A., Picchetti, B. et al. The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition. Sci Data 7, 368 (2020).",
    "paper_doi": "10.1038/s41597-020-00712-x",
    "license": "Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0), as stated in the LICENSE file of the repository",
    "period": "2016-01-01 00:00 to 2017-12-31 23:00 (17,544 hourly values per meter)",
    "frequency": "hourly",
    "energy_unit": "kWh per hour (whole-building electricity meters); the numeric value equals the average demand in kW over that hour",
    "timestamp_convention": "Local clock time of the site as published, no daylight-saving gap or repeat (exactly 17,544 hourly rows); the site time zone is in the metadata",
    "note": "BDG2 is described by its authors as non-residential data in general; this project uses only the buildings whose metadata primary use is 'Lodging/residential' (student residence halls and similar), excluding hotels.",
}


class DownloadError(RuntimeError):
    pass


def sha256_file(path: Path, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(60).startswith(b"version https://git-lfs")


def _fetch(url: str, dest: Path, timeout: int = 300) -> None:
    if not url.startswith("https://"):
        raise DownloadError(f"Refusing to download from a non-https URL: {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "energiq-society-downloader"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:  # nosec B310  # noqa: S310 (https only, checked above)
            shutil.copyfileobj(resp, out, 1 << 20)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"Could not download {url}: {exc}") from exc
    tmp.replace(dest)


def download_bdg2(raw_dir: Path, force: bool = False, log=print) -> dict:
    """Download the BDG2 files needed here into ``raw_dir`` and return the provenance record."""
    raw_dir = Path(raw_dir)
    record_path = raw_dir / "provenance.json"
    files: dict[str, dict] = {}
    for rel, lfs in BDG2_FILES:
        dest = raw_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if force or not dest.is_file() or dest.stat().st_size == 0 or is_lfs_pointer(dest):
            url = f"{LFS_MEDIA if lfs else RAW_GITHUB}/{rel}"
            log(f"downloading {rel}")
            _fetch(url, dest)
        if is_lfs_pointer(dest):
            raise DownloadError(f"{rel} is a Git LFS pointer, not data; the media endpoint did not serve the real file")
        files[rel] = {
            "url": f"{LFS_MEDIA if lfs else RAW_GITHUB}/{rel}",
            "bytes": dest.stat().st_size,
            "sha256": sha256_file(dest),
        }
    previous = json.loads(record_path.read_text()) if record_path.is_file() else None
    record = {
        "source": BDG2_CARD,
        "downloaded_at": previous["downloaded_at"] if previous and not force else datetime.now(UTC).strftime("%Y-%m-%d"),
        "files": files,
    }
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
