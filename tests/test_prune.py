from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prune import select_deletions

TARGET = 'x86_64-unknown-linux-gnu'


def artifact(identifier, date='2026-09-26', channel='stable', target=TARGET, expired=False):
    version = {'stable': '1.98.1', 'beta': '1.99.0-beta.7', 'nightly': '1.100.0-nightly'}[channel]
    return {'id': identifier, 'name': f'rust-{channel}-{version}-{date}-{target}-a7c8774a5fd8',
            'expired': expired, 'created_at': f'{date}T09:00:00Z'}


class PruneTests(unittest.TestCase):
    def test_pinned_cleanup_cannot_evict_latest_channel_artifacts(self):
        automatic = [artifact(1), artifact(2, '2026-09-25')]
        pinned = [artifact(3), artifact(4, '2026-09-25')]
        for a in pinned:
            a['name'] = a['name'].replace('rust-', 'rust-pinned-', 1)
        data = automatic + pinned
        self.assertEqual([a['id'] for a in select_deletions(data, 'stable', TARGET, 3, 1, 'pinned')], [4])
        self.assertEqual(select_deletions(data, 'stable', TARGET, 1, 2, 'latest'), [])

    def test_keep_current_and_previous_distinct_distribution(self):
        data = [artifact(1, '2026-09-24'), artifact(2, '2026-09-25'), artifact(3)]
        self.assertEqual([a['id'] for a in select_deletions(data, 'stable', TARGET, 3)], [1])

    def test_remove_duplicate_but_never_current_upload(self):
        data = [artifact(1), artifact(2), artifact(3, '2026-09-25')]
        self.assertEqual([a['id'] for a in select_deletions(data, 'stable', TARGET, 2)], [1])

    def test_never_delete_other_channels_targets_or_unmanaged_artifacts(self):
        data = [artifact(1), artifact(2, channel='beta'), artifact(3, channel='nightly'),
                artifact(4, target='aarch64-unknown-linux-gnu'), artifact(5, expired=True),
                {'id': 6, 'name': 'unrelated-artifact', 'expired': False}]
        self.assertEqual(select_deletions(data, 'stable', TARGET, 1), [])

    def test_fail_closed_if_replacement_is_missing(self):
        with self.assertRaises(ValueError):
            select_deletions([artifact(1)], 'stable', TARGET, 2)

    def test_zero_retention_is_rejected(self):
        with self.assertRaises(ValueError):
            select_deletions([artifact(1)], 'stable', TARGET, 1, keep=0)


if __name__ == '__main__':
    unittest.main()
