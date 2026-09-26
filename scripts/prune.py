#!/usr/bin/env python3
"""Bound artifact counts without mixing latest and manually pinned distributions."""

import argparse
from datetime import datetime
import json
import os
import re
import urllib.request

from sync import CHANNELS, read_url, summary


def select_deletions(artifacts, channel, target, current_id, keep=2, selection='latest'):
    if keep < 1:
        raise ValueError("Must retain at least one distribution")
    if selection not in ('latest', 'pinned'):
        raise ValueError("Unknown distribution selection")
    prefix = 'rust-pinned' if selection == 'pinned' else 'rust'
    pattern = re.compile(
        rf"{prefix}-{re.escape(channel)}-\d+\.\d+\.\d+(?:-beta(?:\.\d+)?|-nightly)?"
        rf"-\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(target)}-[0-9a-f]{{12}}"
    )
    candidates = [a for a in artifacts if pattern.fullmatch(a['name']) and not a['expired']]
    # Fail closed: never prune without seeing the newly uploaded replacement.
    if not any(a['id'] == current_id for a in candidates):
        raise ValueError("Newly uploaded artifact is not visible; refusing cleanup")
    candidates.sort(key=lambda a: datetime.fromisoformat(a['created_at'].replace('Z', '+00:00')), reverse=True)
    current = next(a for a in candidates if a['id'] == current_id)
    # Keep the current upload first, even if timestamps tie or clocks disagree.
    ordered = [current] + [a for a in candidates if a['id'] != current_id]
    names = set()
    deletions = []
    for artifact in ordered:
        if artifact['name'] in names or len(names) >= keep:
            deletions.append(artifact)
        else:
            names.add(artifact['name'])
    return deletions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', choices=CHANNELS, required=True)
    parser.add_argument('--target', default='x86_64-unknown-linux-gnu')
    parser.add_argument('--current-id', type=int, required=True)
    parser.add_argument('--keep', type=int, default=2)
    parser.add_argument('--selection', choices=('latest', 'pinned'), default='latest')
    args = parser.parse_args()
    repository, token = os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN']
    endpoint = f'https://api.github.com/repos/{repository}/actions/artifacts'
    artifacts = []
    page = 1
    # Gather all pages before deleting so pagination never shifts during cleanup.
    while True:
        result = json.loads(read_url(f'{endpoint}?per_page=100&page={page}', token))
        artifacts.extend(result['artifacts'])
        if page * 100 >= result['total_count']:
            break
        page += 1
    deletions = select_deletions(artifacts, args.channel, args.target, args.current_id, args.keep, args.selection)
    for artifact in deletions:
        request = urllib.request.Request(
            f"{endpoint}/{artifact['id']}", method='DELETE',
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                     'User-Agent': 'rust-toolchain-artifacts'},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 204:
                raise RuntimeError(f'Unexpected delete response: {response.status}')
        print(f"Removed superseded artifact {artifact['id']}: {artifact['name']}", flush=True)
    summary(f'Retention: keep the latest {args.keep} distinct {args.channel} {args.selection} distributions; '
            f'removed {len(deletions)} older/duplicate artifacts after successful publication.')


if __name__ == '__main__':
    main()
