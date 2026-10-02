"""Changing clubs: the app follows the GM's OOTP job (fired, resigned, hired) and lets him pick a
club himself. Portable: builds a tiny export database, no private save needed."""

import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage
from storage import read_json, write_json

SID = "20261002T000000000000Z"
CLUBS = [
    # team_id, city, nickname, abbr, park_id, sub_league, division
    (4, "Boston", "Red Sox", "BOS", 9, 0, 0),
    (18, "New York", "Yankees", "NYY", 21, 0, 0),
    (6, "Chicago", "Cubs", "CHC", 10, 1, 1),
    (20, "Athletics", "Athletics", "ATH", 72, 0, 2),
]


def build(root, humans, sid=SID):
    folder = root / sid
    folder.mkdir(parents=True)
    con = duckdb.connect(str(folder / "analytics.duckdb"))
    con.execute(
        "create table teams(team_id int, name text, nickname text, abbr text, park_id int,"
        " sub_league_id int, division_id int, league_id int, level int, allstar_team int)"
    )
    for c in CLUBS:
        con.execute("insert into teams values (?,?,?,?,?,?,?,203,1,0)", list(c))
    # A minor-league affiliate and an all-star team are never choices.
    con.execute("insert into teams values (35,'Worcester','Red Sox','WOR',90,0,0,204,2,0)")
    con.execute("insert into teams values (99,'American','All-Stars','AL',9,0,0,203,1,1)")
    con.execute("create table parks(park_id int, name text)")
    for pid, name in [(9, "Fenway Park"), (21, "Yankee Stadium"), (10, "Wrigley Field")]:
        con.execute("insert into parks values (?,?)", [pid, name])
    con.execute("create table sub_leagues(league_id int, sub_league_id int, abbr text)")
    con.execute("insert into sub_leagues values (203,0,'AL'),(203,1,'NL')")
    con.execute(
        "create table divisions(league_id int, sub_league_id int, division_id int, name text)"
    )
    con.execute(
        "insert into divisions values (203,0,0,'East Division'),(203,1,1,'Central Division'),"
        "(203,0,2,'West Division')"
    )
    con.execute(
        "create table human_managers(human_manager_id int, team_id int, league_id int, retired int)"
    )
    for h in humans:
        con.execute("insert into human_managers values (?,?,203,0)", list(h))
    con.close()
    write_json(
        folder / "manifest.json",
        {
            "id": sid,
            "created_at": "2026-10-02T00:00:00",
            "game_date": "2026-07-10",
            "season": 2026,
            "team_id": 4,
            "league_id": 203,
        },
    )


class TeamSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, self.data, self.snaps = base, base / "data", base / "snapshots"
        self.data.mkdir()
        self.snaps.mkdir()
        self.patches = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "DATA", self.data),
            patch.object(storage, "SNAPSHOTS", self.snaps),
            patch.object(storage, "_CLUBS", {}),
        ]
        for p in self.patches:
            p.start()
        write_json(self.data / "current.json", {"id": SID})
        write_json(
            self.root / "game-access.json",
            {
                "csv_directory": "C:/save/csv",
                "team_id": 4,
                "league_id": 203,
                "human_team": "Boston Red Sox",
            },
        )

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def cfg(self):
        return read_json(self.root / "game-access.json")

    def test_pick_job_reads_one_human(self):
        clubs = {4, 6, 18}
        self.assertEqual(storage.pick_job([{"human_manager_id": 1, "team_id": 6}], clubs), 6)
        # Between jobs, or running a club outside the MLB list: no job to follow.
        self.assertIsNone(storage.pick_job([{"human_manager_id": 1, "team_id": 0}], clubs))
        self.assertIsNone(storage.pick_job([{"human_manager_id": 1, "team_id": 35}], clubs))
        # Several humans (online league): only follow the one we were told is him.
        two = [{"human_manager_id": 1, "team_id": 4}, {"human_manager_id": 2, "team_id": 18}]
        self.assertIsNone(storage.pick_job(two, clubs))
        self.assertEqual(storage.pick_job(two, clubs, me=2), 18)

    def test_clubs_are_mlb_only_with_divisions_and_parks(self):
        build(self.snaps, [(1, 4)])
        clubs = storage.mlb_clubs()
        self.assertEqual({c["id"] for c in clubs}, {4, 6, 18, 20})
        bos = next(c for c in clubs if c["id"] == 4)
        self.assertEqual(
            (bos["name"], bos["short"], bos["abbr"], bos["park"], bos["division"]),
            ("Boston Red Sox", "Boston", "BOS", "Fenway Park", "AL East"),
        )
        self.assertEqual(next(c for c in clubs if c["id"] == 20)["name"], "Athletics")

    def test_fired_and_hired_elsewhere_moves_the_front_office(self):
        build(self.snaps, [(1, 6)])
        change = storage.sync_team()
        self.assertEqual((change["from"], change["to"], change["to_name"]), (4, 6, "Chicago Cubs"))
        self.assertEqual(change["from_name"], "Boston Red Sox")
        self.assertEqual((self.cfg()["team_id"], self.cfg()["human_team"]), (6, "Chicago Cubs"))
        self.assertEqual(self.cfg()["csv_directory"], "C:/save/csv")  # other settings kept
        status = storage.team_status()
        self.assertEqual((status["id"], status["follow"], status["ootp_job"]), (6, True, 6))
        self.assertEqual(status["change"]["to"], 6)
        self.assertIsNone(storage.sync_team())  # already there

    def test_between_jobs_keeps_the_last_club(self):
        build(self.snaps, [(1, 0)])
        self.assertIsNone(storage.sync_team())
        self.assertEqual(self.cfg()["team_id"], 4)
        self.assertIsNone(storage.team_status()["ootp_job"])

    def test_picking_another_club_stops_following_until_asked(self):
        build(self.snaps, [(1, 4)])
        status = storage.choose_team(18)
        self.assertEqual((status["id"], status["follow"]), (18, False))
        self.assertIsNone(storage.sync_team())  # a manual pick is not undone by the next export
        self.assertEqual(self.cfg()["team_id"], 18)
        status = storage.choose_team(follow=True)
        self.assertEqual((status["id"], status["follow"]), (4, True))
        self.assertIsNone(status["change"])  # back to his own job: no "new job" notice

    def test_picking_your_own_ootp_club_keeps_following(self):
        build(self.snaps, [(1, 4)])
        storage.choose_team(18)
        self.assertTrue(storage.choose_team(4)["follow"])

    def test_new_league_without_an_ootp_job_asks_and_keeps_following(self):
        build(self.snaps, [(1, 0)])
        storage.save_config(team_id=None)
        status = storage.team_status()
        self.assertTrue(status["needs_pick"])
        status = storage.choose_team(6)
        self.assertEqual((status["id"], status["follow"], status["needs_pick"]), (6, True, False))

    def test_bad_choices_are_refused(self):
        build(self.snaps, [(1, 4)])
        for bad in (35, 99, 12345, None, "abc"):
            with self.assertRaises(ValueError):
                storage.choose_team(bad)
        self.assertEqual(self.cfg()["team_id"], 4)

    def test_active_team_falls_back_when_config_is_not_a_club(self):
        build(self.snaps, [(1, 4)])
        m = storage.current()
        storage.save_config(team_id=35)
        self.assertEqual(storage.active_team(m), 4)
        storage.save_config(team_id=6)
        self.assertEqual(storage.active_team(m), 6)

    def test_missing_human_table_means_no_job(self):
        build(self.snaps, [])
        with duckdb.connect(str(self.snaps / SID / "analytics.duckdb")) as con:
            con.execute("drop table human_managers")
        self.assertIsNone(storage.ootp_job())
        self.assertIsNone(storage.sync_team())


if __name__ == "__main__":
    unittest.main()
