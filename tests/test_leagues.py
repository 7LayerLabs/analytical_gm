"""Several OOTP saves: find them, switch between them, keep each league's exports, settings and
plans apart, and work out a brand-new league without typing ids. Portable: temp folders only."""

import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage
from storage import read_json, write_json


def make_snapshot(root, sid, created, source):
    folder = root / sid
    (folder / "csv").mkdir(parents=True)
    (folder / "analytics.duckdb").write_bytes(b"db")
    write_json(
        folder / "manifest.json",
        {"id": sid, "created_at": created, "source_id": source, "game_date": "2026-07-10"},
    )


class Leagues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, self.data, self.snaps = base / "app", base / "data", base / "snapshots"
        for p in (self.root, self.data, self.snaps):
            p.mkdir()
        # A home folder with OOTP's usual layout: one exported save, one brand-new league.
        self.home = base / "home"
        games = self.home / "Documents/Out of the Park Developments/OOTP Baseball 27/saved_games"
        self.abl = games / "abl.lg/import_export/csv"
        self.abl.mkdir(parents=True)
        (self.abl / "players.csv").write_text("player_id\n1\n")
        self.new = games / "Paramount Baseball League.lg/import_export/csv"
        (games / "Paramount Baseball League.lg").mkdir()
        (games / ".lg").mkdir()  # OOTP leaves an unnamed folder; not a league
        self.patches = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "DATA", self.data),
            patch.object(storage, "SNAPSHOTS", self.snaps),
            patch.object(storage, "_CLUBS", {}),
            patch.object(storage.Path, "home", return_value=self.home),
            patch.object(storage, "start_import"),
        ]
        for p in self.patches:
            p.start()
        write_json(
            self.root / "game-access.json",
            {
                "csv_directory": str(self.abl),
                "team_id": 18,
                "league_id": 203,
                "save_name": "abl",
                "human_team": "New York Yankees",
                "follow_ootp": False,
                "snapshot_directory": "D:/snaps",
            },
        )
        self.abl_key = storage.source_key(self.abl)
        self.new_key = storage.source_key(self.new)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def cfg(self):
        return read_json(self.root / "game-access.json")

    def test_finds_every_save_and_which_have_exports(self):
        saves = storage.list_saves()
        self.assertEqual([s["name"] for s in saves], ["abl", "Paramount Baseball League"])
        abl, new = saves
        self.assertTrue(abl["active"] and abl["has_export"])
        self.assertEqual(abl["team"], "New York Yankees")
        self.assertFalse(new["active"] or new["has_export"])
        self.assertEqual(storage.source_key(new["csv_directory"]), self.new_key)

    def test_switching_parks_this_league_and_starts_the_new_one_fresh(self):
        make_snapshot(self.snaps, "20261002T000000000000Z", "2026-10-02T00:00:00", self.abl_key)
        write_json(self.data / "current.json", {"saves": {self.abl_key: "20261002T000000000000Z"}})
        status = storage.choose_league(str(self.new))
        self.assertEqual(
            (status["name"], status["has_export"]), ("Paramount Baseball League", False)
        )
        cfg = self.cfg()
        self.assertEqual(storage.source_key(cfg["csv_directory"]), self.new_key)
        self.assertTrue(cfg["follow_ootp"])
        for key in ("team_id", "league_id", "human_team"):  # the new league works these out
            self.assertNotIn(key, cfg)
        self.assertEqual(cfg["snapshot_directory"], "D:/snaps")  # app-wide settings stay
        self.assertEqual(cfg["saves"][self.abl_key]["team_id"], 18)
        self.assertIsNone(storage.current())
        self.assertEqual(storage.snapshots(), [])
        storage.start_import.assert_not_called()  # nothing to import until OOTP exports

        storage.choose_league(str(self.abl))
        cfg = self.cfg()
        self.assertEqual((cfg["team_id"], cfg["follow_ootp"], cfg["save_name"]), (18, False, "abl"))
        self.assertEqual(storage.current()["id"], "20261002T000000000000Z")
        storage.start_import.assert_called_once()  # picks up a newer abl export if there is one

    def test_only_known_saves_can_be_chosen(self):
        for bad in ("", str(self.root), "C:/Windows"):
            with self.assertRaises(ValueError):
                storage.choose_league(bad)

    def test_each_league_keeps_its_own_history(self):
        make_snapshot(self.snaps, "20261001T000000000000Z", "2026-10-01T00:00:00", self.abl_key)
        make_snapshot(self.snaps, "20261002T000000000000Z", "2026-10-02T00:00:00", self.new_key)
        write_json(
            self.data / "current.json",
            {
                "saves": {
                    self.abl_key: "20261001T000000000000Z",
                    self.new_key: "20261002T000000000000Z",
                }
            },
        )
        self.assertEqual([m["id"] for m in storage.snapshots()], ["20261001T000000000000Z"])
        self.assertEqual(storage.current()["id"], "20261001T000000000000Z")
        self.assertEqual(len(storage.snapshots(source=None)), 2)

    def test_old_single_pointer_still_finds_its_save(self):
        make_snapshot(self.snaps, "20261001T000000000000Z", "2026-10-01T00:00:00", self.abl_key)
        write_json(self.data / "current.json", {"id": "20261001T000000000000Z"})
        self.assertEqual(storage.current()["id"], "20261001T000000000000Z")
        storage.save_config(csv_directory=str(self.new))
        self.assertIsNone(storage.current())  # that pointer was abl's, not the new league's

    def test_pruning_is_per_league(self):
        ids = {}
        for key in (self.abl_key, self.new_key):
            ids[key] = [
                f"2026100{i}T00000000000{'0' if key == self.abl_key else '1'}Z" for i in range(1, 5)
            ]
            for i, sid in enumerate(ids[key]):
                make_snapshot(
                    self.snaps, sid, f"2026-10-0{i + 1}T00:00:0{int(key == self.new_key)}", key
                )
        write_json(
            self.data / "current.json",
            {"saves": {k: v[-1] for k, v in ids.items()}},
        )
        storage.prune(keep=2)
        for key, sids in ids.items():
            self.assertTrue((self.snaps / sids[-1] / "csv").exists())
            self.assertTrue((self.snaps / sids[-2]).exists())
            self.assertFalse((self.snaps / sids[0]).exists())


class BrandNewLeague(unittest.TestCase):
    """A fictional league: different league and club ids, minor leagues under it."""

    def setUp(self):
        self.con = duckdb.connect()
        self.con.execute(
            "create table leagues(league_id int, league_level int, parent_league_id int)"
        )
        self.con.execute("insert into leagues values (100,1,0),(101,2,100),(203,2,100)")
        self.con.execute(
            "create table teams(team_id int, name text, nickname text, league_id int, level int,"
            " allstar_team int)"
        )
        for tid, name in [(1, "Portland"), (2, "Austin"), (3, "Omaha"), (4, "Boise")]:
            self.con.execute("insert into teams values (?,?,'Pioneers',100,1,0)", [tid, name])
        self.con.execute("insert into teams values (20,'Salem','Kids',101,2,0)")
        self.con.execute(
            "create table human_managers(human_manager_id int, team_id int, league_id int,"
            " retired int)"
        )

    def tearDown(self):
        self.con.close()

    def test_league_is_detected_without_typing_an_id(self):
        # The old save's 203 exists here only as a minor league: not ours.
        self.assertEqual(storage.detect_league(self.con, 203), 100)
        self.assertEqual(storage.detect_league(self.con, None), 100)

    def test_club_comes_from_the_ootp_job_else_ask(self):
        self.assertEqual(storage.detect_team(self.con, 100, {}), 2)  # first by name; dashboard asks
        self.con.execute("insert into human_managers values (1,3,100,0)")
        self.assertEqual(storage.detect_team(self.con, 100, {"team_id": 18}), 3)
        self.assertEqual(storage.detect_team(self.con, 100, {"team_id": 4}), 4)

    def test_missing_level_columns_still_work(self):
        con = duckdb.connect()
        con.execute("create table leagues(league_id int)")
        con.execute("insert into leagues values (203)")
        con.execute("create table teams(team_id int, league_id int)")
        con.execute("insert into teams values (4,203),(5,203)")
        self.assertEqual(storage.detect_league(con, None), 203)
        self.assertEqual(storage.detect_team(con, 203, {"team_id": 4}), 4)
        con.close()


class OneDriveLocks(unittest.TestCase):
    def test_a_briefly_locked_file_is_retried_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            real = storage.os.replace
            calls = []

            def flaky(src, dst):
                calls.append(1)
                if len(calls) < 3:
                    raise PermissionError("[WinError 5] Access is denied")
                real(src, dst)

            with patch.object(storage.os, "replace", side_effect=flaky):
                write_json(target, {"ok": True})
            self.assertEqual(read_json(target), {"ok": True})
            self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
