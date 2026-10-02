import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage
from storage import write_json


def make_snapshot(root, sid, created):
    folder = root / sid
    (folder / "csv").mkdir(parents=True)
    (folder / "csv" / "players.csv").write_text("player_id\n1\n")
    (folder / "analytics.duckdb").write_bytes(b"db")
    write_json(folder / "manifest.json", {"id": sid, "created_at": created})
    return folder


class Retention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.data, self.snaps = base / "data", base / "snapshots"
        self.data.mkdir()
        self.snaps.mkdir()
        self.patches = [
            patch.object(storage, "DATA", self.data),
            patch.object(storage, "SNAPSHOTS", self.snaps),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def ids(self, n):
        return [f"20261001T0000{i:02d}000000Z" for i in range(n)]

    def test_migration_moves_only_snapshot_folders_and_keeps_state(self):
        sid = self.ids(1)[0]
        make_snapshot(self.data, sid, "2026-10-01T00:00:00")
        write_json(self.data / "journal.json", [])
        (self.data / "failed-imports").mkdir()
        self.assertEqual(storage.migrate_snapshots(), 1)
        self.assertTrue((self.snaps / sid / "manifest.json").exists())
        self.assertFalse((self.data / sid).exists())
        self.assertTrue((self.data / "journal.json").exists())
        self.assertTrue((self.data / "failed-imports").exists())
        self.assertEqual(storage.migrate_snapshots(), 0)  # running again is harmless

    def test_prune_keeps_newest_raw_csv_and_caps_the_count(self):
        sids = self.ids(5)
        for i, sid in enumerate(sids):
            make_snapshot(self.snaps, sid, f"2026-10-01T00:00:0{i}")
        newest = sids[-1]
        write_json(self.data / "current.json", {"id": newest})
        storage.prune(keep=3)
        self.assertTrue((self.snaps / newest / "csv").exists())
        for sid in sids[2:4]:  # kept, but without the raw CSV copy
            self.assertTrue((self.snaps / sid / "analytics.duckdb").exists())
            self.assertFalse((self.snaps / sid / "csv").exists())
        for sid in sids[:2]:  # past the cap
            self.assertFalse((self.snaps / sid).exists())

    def test_prune_never_touches_the_current_snapshot(self):
        sids = self.ids(3)
        for i, sid in enumerate(sids):
            make_snapshot(self.snaps, sid, f"2026-10-01T00:00:0{i}")
        write_json(self.data / "current.json", {"id": sids[0]})  # oldest is current
        storage.prune(keep=1)
        self.assertTrue((self.snaps / sids[0] / "csv").exists())
