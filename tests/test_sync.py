from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync


def manifest(version, available=True):
    return f'''date = "2026-09-26"
[pkg.rust]
version = "{version} (abcdef123 2026-09-25)"
[pkg.rustc]
version = "{version} (abcdef123 2026-09-25)"
[pkg.rust.target.x86_64-unknown-linux-gnu]
available = {str(available).lower()}
xz_url = "https://static.rust-lang.org/dist/2026-09-26/rust-test.tar.xz"
xz_hash = "{'a' * 64}"
'''.encode()


class ChannelTests(unittest.TestCase):
    def test_requested_version_selects_immutable_manifest(self):
        cases = [
            ('stable', '1.98.1', 'channel-rust-1.98.1.toml'),
            ('stable', '2026-09-03', '2026-09-03/channel-rust-stable.toml'),
            ('beta', 'beta-2026-09-20', '2026-09-20/channel-rust-beta.toml'),
            ('nightly', 'nightly-2026-09-26', '2026-09-26/channel-rust-nightly.toml'),
            ('nightly', '2026-09-26', '2026-09-26/channel-rust-nightly.toml'),
        ]
        for channel, version, path in cases:
            with self.subTest(channel=channel, version=version):
                self.assertEqual(sync.manifest_request(channel, version)[0], f'{sync.DIST}/{path}')

    def test_invalid_or_conflicting_version_fails_before_network(self):
        for channel, selector in [('stable', 'nightly-2026-09-26'), ('nightly', '1.98.1'),
                                  ('beta', '../stable'), ('stable', '2026-02-30'),
                                  ('beta', '1.99.0-beta.7'), ('stable', '$(id)')]:
            with self.subTest(channel=channel, selector=selector), self.assertRaises(ValueError):
                sync.manifest_request(channel, selector)

    def test_pinned_artifact_is_isolated_and_version_checked(self):
        raw = manifest('1.98.1')
        checksum = hashlib.sha256(raw).hexdigest().encode()
        with patch.object(sync, 'read_url', side_effect=[raw, checksum]):
            info, _ = sync.resolve('stable', 'x86_64-unknown-linux-gnu', '1.98.1')
        self.assertTrue(info['artifact_name'].startswith('rust-pinned-stable-'))
        self.assertEqual(info['selection'], 'pinned')
        with patch.object(sync, 'read_url', side_effect=[raw, checksum]), self.assertRaises(ValueError):
            sync.resolve('stable', 'x86_64-unknown-linux-gnu', '1.97.0')

    def test_wrong_snapshot_date_is_rejected(self):
        raw = manifest('1.100.0-nightly')
        checksum = hashlib.sha256(raw).hexdigest().encode()
        with patch.object(sync, 'read_url', side_effect=[raw, checksum]), self.assertRaises(ValueError):
            sync.resolve('nightly', 'x86_64-unknown-linux-gnu', 'nightly-2026-09-25')

    def test_channel_identity_is_preserved(self):
        names = set()
        for channel, version in [('stable', '1.98.1'), ('beta', '1.99.0-beta.7'), ('nightly', '1.100.0-nightly')]:
            info = sync.describe(channel, 'x86_64-unknown-linux-gnu', manifest(version))
            self.assertEqual(info['channel'], channel)
            self.assertEqual(info['release'], version)
            self.assertIn(channel, info['artifact_name'])
            names.add(info['artifact_name'])
        self.assertEqual(len(names), 3)

    def test_stable_rejects_prerelease(self):
        for version in ['1.99.0-beta.7', '1.100.0-nightly']:
            with self.assertRaises(ValueError):
                sync.describe('stable', 'x86_64-unknown-linux-gnu', manifest(version))

    def test_beta_and_nightly_cannot_be_swapped(self):
        for channel, version in [('beta', '1.100.0-nightly'), ('nightly', '1.99.0-beta.7')]:
            with self.assertRaises(ValueError):
                sync.describe(channel, 'x86_64-unknown-linux-gnu', manifest(version))

    def test_missing_latest_fails_without_fallback(self):
        with self.assertRaises(ValueError):
            sync.describe('nightly', 'x86_64-unknown-linux-gnu', manifest('1.100.0-nightly', False))

    def test_manifest_checksum_mismatch_retries_pair(self):
        raw = manifest('1.98.1')
        good = hashlib.sha256(raw).hexdigest().encode()
        with patch.object(sync, 'read_url', side_effect=[raw, b'0' * 64, raw, good]) as read, patch.object(sync.time, 'sleep'):
            info, _ = sync.resolve('stable', 'x86_64-unknown-linux-gnu')
        self.assertEqual(read.call_count, 4)
        self.assertEqual(info['release'], '1.98.1')

    def test_corrupt_manifest_is_rejected(self):
        with self.assertRaises(ValueError):
            sync.verify(b'corrupt', '0' * 64)

    def test_artifact_expiry_and_channel_isolation(self):
        now = datetime.now(timezone.utc)
        artifact = {'name': 'stable', 'expired': False, 'expires_at': (now + timedelta(days=30)).isoformat()}
        self.assertTrue(sync.reusable(artifact, 'stable', now))
        self.assertFalse(sync.reusable(artifact, 'nightly', now))
        artifact['expires_at'] = (now + timedelta(days=6)).isoformat()
        self.assertFalse(sync.reusable(artifact, 'stable', now))
        artifact['expired'] = True
        self.assertFalse(sync.reusable(artifact, 'stable', now))


if __name__ == '__main__':
    unittest.main()
