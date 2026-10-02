import csv, hashlib, json, os, shutil, threading, time
from datetime import datetime, timezone
from pathlib import Path
import duckdb
import re
from analytics import BAT_FIELDS, PIT_FIELDS, combine

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
LOCK = threading.Lock()
STATUS = {"running": False, "message": "Ready", "error": None}
REQUIRED = {
    "players": ["player_id", "team_id", "organization_id", "retired", "first_name", "last_name"],
    "teams": ["team_id", "league_id"],
    "leagues": ["league_id", "current_date", "season_year"],
    "players_career_batting_stats": ["player_id", "year", "split_id", "league_id", "pa", "ab", "h"],
    "players_career_pitching_stats": [
        "player_id",
        "year",
        "split_id",
        "league_id",
        "outs",
        "bf",
        "er",
    ],
    "players_batting": ["player_id"],
    "players_pitching": ["player_id"],
    "players_fielding": ["player_id"],
    "players_roster_status": ["player_id"],
    "players_contract": ["player_id", "salary0", "season_year"],
    "team_financials": ["team_id", "budget", "player_payroll"],
}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default


def write_json(path, value):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def config():
    return read_json(ROOT / "game-access.json", read_json(ROOT / "game-access.example.json"))


def signature():
    p = Path(config()["csv_directory"])
    return [(f.name, f.stat().st_size, f.stat().st_mtime_ns) for f in sorted(p.glob("*.csv"))]


def snapshots():
    return sorted(
        [read_json(p) for p in DATA.glob("*/manifest.json")],
        key=lambda x: x["created_at"],
        reverse=True,
    )


def current():
    pointer = read_json(DATA / "current.json")
    return read_json(DATA / pointer["id"] / "manifest.json") if pointer else None


def connect(sid=None):
    if sid is not None and not re.fullmatch(r"\d{8}T\d{12}Z", sid):
        raise ValueError("Invalid snapshot identifier.")
    m = current() if not sid else read_json(DATA / sid / "manifest.json")
    if not m:
        raise ValueError("Import an OOTP export first.")
    return duckdb.connect(str(DATA / m["id"] / "analytics.duckdb"), read_only=True)


def records(con, sql, params=None):
    cursor = con.execute(sql, params or [])
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def import_snapshot(force=False):
    if not LOCK.acquire(blocking=False):
        return {"message": "An import is already running."}
    sid = None
    try:
        STATUS.update(running=True, message="Checking export files", error=None)
        before = signature()
        old = current()
        if not before:
            raise ValueError("No CSV files were found at the configured export folder.")
        if old and old["signature"] == [list(x) for x in before] and not force:
            STATUS["message"] = "Already current"
            return old
        source = Path(config()["csv_directory"])
        for table, fields in REQUIRED.items():
            with open(source / (table + ".csv"), encoding="utf-8-sig", newline="") as h:
                actual = next(csv.reader(h))
                missing = set(fields) - set(actual)
                if missing:
                    raise ValueError(f"{table}: missing columns {sorted(missing)}")
        sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder = DATA / sid
        folder.mkdir()
        raw = folder / "csv"
        raw.mkdir()
        hashes = {}
        counts = {}
        STATUS["message"] = "Preserving and importing the export"
        con = duckdb.connect(str(folder / "analytics.duckdb"))
        try:
            for name, _, _ in before:
                f = raw / name
                shutil.copy2(source / name, f)
                hashes[name] = hashlib.sha256(f.read_bytes()).hexdigest()
                table = f.stem
                if not table.replace("_", "").isalnum():
                    continue
                con.execute(
                    f"CREATE TABLE \"{table}\" AS SELECT * FROM read_csv(?, header=true, auto_detect=true, sample_size=-1, nullstr=['NULL',''], strict_mode=true)",
                    [str(f)],
                )
                counts[table] = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            if before != signature():
                raise ValueError(
                    "The export changed during import. Wait for OOTP to finish exporting, then refresh again."
                )
            lid = config()["league_id"]
            league = records(con, "select * from leagues where league_id=?", [lid])[0]
            issues = []
            for table in [
                "players",
                "players_batting",
                "players_pitching",
                "players_fielding",
                "players_contract",
                "players_roster_status",
                "teams",
            ]:
                key = "team_id" if table == "teams" else "player_id"
                dup = con.execute(f"SELECT count(*)-count(distinct {key}) FROM {table}").fetchone()[
                    0
                ]
                if dup:
                    raise ValueError(f"{table}: {dup} duplicate identifiers; import rejected.")
            for table in [
                "players_batting",
                "players_pitching",
                "players_fielding",
                "players_contract",
                "players_roster_status",
            ]:
                missing = con.execute(
                    f"SELECT count(*) FROM {table} t LEFT JOIN players p USING(player_id) WHERE p.player_id IS NULL"
                ).fetchone()[0]
                if missing:
                    issues.append(f"{table}: {missing} unmatched player IDs")
            ratings = []
            for table, prefix in [
                ("players_batting", "batting_ratings_overall_"),
                ("players_pitching", "pitching_ratings_overall_"),
                ("players_fielding", "fielding_rating_pos"),
            ]:
                columns = [
                    r[0]
                    for r in con.execute(f"DESCRIBE {table}").fetchall()
                    if r[0].startswith(prefix)
                ]
                for column in columns:
                    lo, hi = con.execute(
                        f'SELECT min("{column}"),max("{column}") FROM {table}'
                    ).fetchone()
                    ratings.append(
                        {
                            "table": table,
                            "column": column,
                            "min": lo,
                            "max": hi,
                            "within_1_10": lo is not None and lo >= 0 and hi <= 10,
                        }
                    )
            batting_splits = records(
                con,
                "select split_id,count(*) row_count from players_career_batting_stats group by split_id order by split_id",
            )
            pitching_splits = records(
                con,
                "select split_id,count(*) row_count from players_career_pitching_stats group by split_id order by split_id",
            )
            # split 1 is season total; split 2/3 are separate handedness rows, never add to totals.
            for table, fields in [("bat_seasons", BAT_FIELDS), ("pit_seasons", PIT_FIELDS)]:
                src = (
                    "players_career_batting_stats"
                    if table == "bat_seasons"
                    else "players_career_pitching_stats"
                )
                sums = ",".join(f'sum(coalesce("{k}",0)) "{k}"' for k in fields)
                con.execute(
                    f"CREATE TABLE {table} AS SELECT player_id,year,league_id,{sums} FROM {src} WHERE split_id=1 AND game_id=0 GROUP BY player_id,year,league_id"
                )
            manifest = {
                "id": sid,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "game_date": str(league["current_date"]),
                "source_id": hashlib.sha256(str(source.resolve()).casefold().encode()).hexdigest()[
                    :12
                ],
                "season": int(league["season_year"]),
                "team_id": config()["team_id"],
                "league_id": lid,
                "signature": before,
                "hashes": hashes,
                "tables": counts,
                "issues": issues,
                "rating_checks": ratings,
                "batting_splits": batting_splits,
                "pitching_splits": pitching_splits,
                "validation": "Export schema, IDs and source stability checked. UI reconciliation is still a manual check.",
                "total_rows": sum(counts.values()),
            }
            write_json(folder / "manifest.json", manifest)
        finally:
            con.close()
        write_json(DATA / "current.json", {"id": sid})
        STATUS["message"] = "Snapshot ready"
        return manifest
    except Exception as e:
        # Only the incomplete directory created by this import can be removed.
        if sid:
            failed = (DATA / sid).resolve()
            if failed.parent == DATA.resolve() and not (failed / "manifest.json").exists():
                shutil.rmtree(failed)
        STATUS.update(message="Import failed; previous snapshot retained", error=str(e))
        raise
    finally:
        STATUS["running"] = False
        LOCK.release()


def start_import(force=False):
    def run():
        try:
            import_snapshot(force)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def watcher():
    last = None
    stable = 0
    attempted = None
    while True:
        time.sleep(10)
        try:
            sig = signature()
            stable = stable + 1 if sig == last else 0
            last = sig
            m = current()
            if (
                stable >= 2
                and not STATUS["running"]
                and sig != attempted
                and (not m or m["signature"] != [list(x) for x in sig])
            ):
                attempted = sig
                start_import()
        except Exception as e:
            STATUS["error"] = str(e)
