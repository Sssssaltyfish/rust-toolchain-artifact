#!/usr/bin/env python3
"""Mirror a verified official Rust distribution; Python 3.11+, no dependencies."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request

CHANNELS = ("stable", "beta", "nightly")
DIST = "https://static.rust-lang.org/dist"


def read_url(url, token=None):
    headers = {"User-Agent": "rust-toolchain-artifacts", "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def verify(data, expected):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: expected {expected}, got {actual}")


def resolve(channel, target):
    url = f"{DIST}/channel-rust-{channel}.toml"
    # The moving manifest and checksum can change between requests. Retry the pair.
    for attempt in range(3):
        raw = read_url(url)
        checksum = read_url(url + ".sha256").decode().split()[0]
        try:
            verify(raw, checksum)
            break
        except ValueError:
            if attempt == 2:
                raise
            time.sleep(2)
    return describe(channel, target, raw), raw


def describe(channel, target, raw):
    manifest = tomllib.loads(raw.decode())
    version = manifest["pkg"]["rust"]["version"]
    release = version.split()[0]
    expected = {"stable": r"\d+\.\d+\.\d+", "beta": r"\d+\.\d+\.\d+-beta(?:\.\d+)?", "nightly": r"\d+\.\d+\.\d+-nightly"}
    if not re.fullmatch(expected[channel], release):
        raise ValueError(f"Wrong release for {channel}: {release}")
    package = manifest["pkg"]["rust"]["target"][target]
    if not package["available"]:
        raise ValueError(f"Latest {channel} has no complete distribution for {target}; refusing to fall back")
    url = package["xz_url"]
    if not url.startswith(f"{DIST}/{manifest['date']}/") or not url.endswith(".tar.xz"):
        raise ValueError(f"Expected a dated official distribution URL, got {url}")
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "channel": channel, "version": version, "release": release,
        "date": manifest["date"], "target": target,
        "rustc_version": manifest["pkg"]["rustc"]["version"],
        "url": url, "sha256": package["xz_hash"], "manifest_sha256": digest,
        "artifact_name": f"rust-{channel}-{release}-{manifest['date']}-{target}-{digest[:12]}",
        "archive": url.rsplit("/", 1)[1],
    }


def reusable(artifact, name, now):
    return (
        artifact["name"] == name
        and not artifact["expired"]
        and datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00")) > now + timedelta(days=7)
    )


def existing_artifact(name):
    repository, token = os.getenv("GITHUB_REPOSITORY"), os.getenv("GH_TOKEN")
    if not repository or not token:
        return None
    query = urllib.parse.urlencode({"name": name, "per_page": 100})
    endpoint = f"https://api.github.com/repos/{repository}/actions/artifacts?{query}"
    now = datetime.now(timezone.utc)
    page = 1
    while True:
        result = json.loads(read_url(f"{endpoint}&page={page}", token))
        for artifact in result["artifacts"]:
            if reusable(artifact, name, now):
                return artifact
        if page * 100 >= result["total_count"]:
            return None
        page += 1


def download(url, path, expected):
    temporary = path.with_suffix(path.suffix + ".part")
    for attempt in range(3):
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected:
                raise ValueError(f"Distribution SHA-256 mismatch for {url}")
            temporary.replace(path)
            return
        except (urllib.error.URLError, TimeoutError, ValueError):
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def output(values):
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


def summary(text):
    print(text, flush=True)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(text + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=CHANNELS, required=True)
    parser.add_argument("--target", default="x86_64-unknown-linux-gnu")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resolve-only", action="store_true")
    args = parser.parse_args()
    info, manifest = resolve(args.channel, args.target)
    print(json.dumps(info, indent=2), flush=True)
    if args.resolve_only:
        return
    existing = None if args.force else existing_artifact(info["artifact_name"])
    if existing:
        output({"publish": "false"})
        run_id = existing["workflow_run"]["id"]
        repository = os.environ["GITHUB_REPOSITORY"]
        summary(f"{args.channel}: {info['version']} ({info['date']}) already available: "
                f"[download artifact](https://github.com/{repository}/actions/runs/{run_id}/artifacts/{existing['id']}).")
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    download(info["url"], args.output_dir / info["archive"], info["sha256"])
    manifest_name = f"channel-rust-{args.channel}.toml"
    (args.output_dir / manifest_name).write_bytes(manifest)
    (args.output_dir / "metadata.json").write_text(json.dumps(info, indent=2) + "\n")
    checksums = []
    for path in sorted(args.output_dir.iterdir()):
        if path.name == "SHA256SUMS":
            continue
        with path.open("rb") as handle:
            checksums.append(f"{hashlib.file_digest(handle, 'sha256').hexdigest()}  {path.name}\n")
    (args.output_dir / "SHA256SUMS").write_text("".join(checksums))
    output({"publish": "true", "artifact_name": info["artifact_name"], "archive": info["archive"]})
    summary(f"Verified official **{args.channel} {info['version']}**, published {info['date']}, target `{args.target}`.\n\n"
            f"Archive SHA-256: `{info['sha256']}`")


if __name__ == "__main__":
    main()
