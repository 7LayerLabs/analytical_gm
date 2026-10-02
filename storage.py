import csv, hashlib, json, os, shutil, threading, time
from datetime import datetime, timezone
from pathlib import Path
import duckdb
import re
from analytics import BAT_FIELDS, PIT_FIELDS, combine

ROOT = Path(__file__).resolve().parent
# Small, valuable state (blueprints, journal, saved cases, forecast archive) stays beside the app.
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
# Big, rebuildable export snapshots live on the local disk, outside OneDrive sync.
LOCAL = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OOTP-Analytics"
KEEP_SNAPSHOTS = 20  # newest exports kept; only the newest keeps its raw CSV copy
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
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # OneDrive or antivirus briefly holding the file
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def config():
    return read_json(ROOT / "game-access.json", read_json(ROOT / "game-access.example.json"))


CONFIG_LOCK = threading.Lock()


def save_config(**changes):
    """Update game-access.json in place; every other setting is kept."""
    with CONFIG_LOCK:
        cfg = {**(config() or {}), **changes}
        write_json(ROOT / "game-access.json", cfg)
        return cfg


def follows_ootp(cfg=None):
    # On by default: the app goes wherever OOTP says the GM works.
    return (cfg if cfg is not None else config() or {}).get("follow_ootp", True) is not False


# Settings that belong to one OOTP save. Switching leagues parks them under "saves" and restores
# the other save's set, so each league keeps its own club, league id and follow choice.
SAVE_KEYS = (
    "csv_directory",
    "save_name",
    "league_id",
    "team_id",
    "human_team",
    "follow_ootp",
    "human_manager_id",
)


def source_key(csv_directory):
    """Stable id for one save's export folder; every snapshot records it as `source_id`."""
    return hashlib.sha256(str(Path(csv_directory).resolve()).casefold().encode()).hexdigest()[:12]


def active_source(cfg=None):
    cfg = cfg if cfg is not None else config() or {}
    return source_key(cfg["csv_directory"]) if cfg.get("csv_directory") else None


SNAPSHOTS = Path((config() or {}).get("snapshot_directory") or LOCAL / "snapshots")
SNAPSHOTS.mkdir(parents=True, exist_ok=True)


def migrate_snapshots():
    """One-time move of snapshot folders that used to live in data/ (inside OneDrive)."""
    moved = 0
    for folder in DATA.iterdir():
        if re.fullmatch(r"\d{8}T\d{12}Z", folder.name) and (folder / "manifest.json").exists():
            if not (SNAPSHOTS / folder.name).exists():
                shutil.move(str(folder), str(SNAPSHOTS / folder.name))
                moved += 1
    return moved


def prune(keep=KEEP_SNAPSHOTS):
    """Per save, keep the newest snapshots. Older ones lose their raw CSV copy (the database
    already holds the same rows); anything past `keep` is removed. One league's exports never push
    out another's, and no save's current snapshot is touched."""
    keepers = set(_pointers().values())
    by_save = {}
    for m in snapshots(source=None):
        by_save.setdefault(m.get("source_id"), []).append(m)
    for ms in by_save.values():
        for i, m in enumerate(ms):
            folder = SNAPSHOTS / m["id"]
            if m["id"] in keepers:
                continue
            if i >= keep:
                shutil.rmtree(folder, ignore_errors=True)
            elif i >= 1:
                shutil.rmtree(folder / "csv", ignore_errors=True)


def signature(csv_directory=None):
    p = Path(csv_directory or config()["csv_directory"])
    return [(f.name, f.stat().st_size, f.stat().st_mtime_ns) for f in sorted(p.glob("*.csv"))]


def snapshots(source="active"):
    """Newest first. By default only the active save's exports; `source=None` lists every save's,
    and a source id lists that save's."""
    if source == "active":
        source = active_source()
    found = [read_json(p) for p in SNAPSHOTS.glob("*/manifest.json")]
    return sorted(
        [m for m in found if source is None or m.get("source_id") in (source, None)],
        key=lambda x: x["created_at"],
        reverse=True,
    )


def _pointers():
    """{save source id: its current snapshot id}. A pre-multi-league pointer ({"id": ...}) counts
    for the save that snapshot came from."""
    pointer = read_json(DATA / "current.json") or {}
    by_save = dict(pointer.get("saves") or {})
    if pointer.get("id"):
        m = read_json(SNAPSHOTS / pointer["id"] / "manifest.json")
        if m:
            by_save.setdefault(m.get("source_id"), pointer["id"])
    return by_save


def current():
    by_save = _pointers()
    sid = by_save.get(active_source()) or by_save.get(None)  # None: manifest without a source
    return read_json(SNAPSHOTS / sid / "manifest.json") if sid else None


def connect(sid=None):
    if sid is not None and not re.fullmatch(r"\d{8}T\d{12}Z", sid):
        raise ValueError("Invalid snapshot identifier.")
    m = current() if not sid else read_json(SNAPSHOTS / sid / "manifest.json")
    if not m:
        raise ValueError("Import an OOTP export first.")
    return duckdb.connect(str(SNAPSHOTS / m["id"] / "analytics.duckdb"), read_only=True)


def records(con, sql, params=None):
    cursor = con.execute(sql, params or [])
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


# ---- whose front office this is -----------------------------------------------------------

_CLUBS = {}  # snapshot id -> (clubs, human managers); snapshots never change once imported


def _optional(con, sql, params=None):
    # Older exports may lack a table (human managers, divisions); missing means unknown.
    try:
        return records(con, sql, params)
    except (duckdb.CatalogException, duckdb.BinderException):
        return []


def club_name(name, nickname):
    name, nickname = str(name or ""), str(nickname or "")
    return (name + " " + (nickname if nickname != name else "")).strip()  # "Athletics Athletics"


def _club_context(m):
    if m["id"] not in _CLUBS:
        league = m["league_id"]
        with connect(m["id"]) as con:
            teams = records(
                con,
                "select t.team_id, t.name, t.nickname, t.abbr, t.sub_league_id, t.division_id,"
                " p.name park from teams t left join parks p using(park_id)"
                " where t.league_id=? and t.level=1 and coalesce(t.allstar_team,0)=0",
                [league],
            )
            subs = {
                r["sub_league_id"]: r["abbr"]
                for r in _optional(
                    con, "select sub_league_id, abbr from sub_leagues where league_id=?", [league]
                )
            }
            divisions = {
                (r["sub_league_id"], r["division_id"]): str(r["name"]).replace(" Division", "")
                for r in _optional(
                    con,
                    "select sub_league_id, division_id, name from divisions where league_id=?",
                    [league],
                )
            }
            humans = _optional(
                con,
                "select human_manager_id, team_id, league_id from human_managers"
                " where coalesce(retired,0)=0",
            )
        clubs = sorted(
            (
                {
                    "id": int(t["team_id"]),
                    "name": club_name(t["name"], t["nickname"]),
                    "short": str(t["name"] or ""),
                    "nickname": str(t["nickname"] or t["name"] or ""),
                    "abbr": str(t["abbr"] or ""),
                    "park": t["park"],
                    "division": " ".join(
                        x
                        for x in (
                            subs.get(t["sub_league_id"]),
                            divisions.get((t["sub_league_id"], t["division_id"])),
                        )
                        if x
                    ),
                    "order": (t["sub_league_id"] or 0, t["division_id"] or 0),
                }
                for t in teams
            ),
            key=lambda c: (c["order"], c["name"]),
        )
        _CLUBS[m["id"]] = (clubs, humans)
    return _CLUBS[m["id"]]


def mlb_clubs(m=None):
    m = m or current()
    return _club_context(m)[0] if m else []


def pick_job(humans, clubs, me=None):
    """The MLB club the human GM runs, from OOTP's human_managers rows. None when he's between
    jobs, or when several humans share the save and `human_manager_id` doesn't say which is him."""
    if me is not None:
        humans = [h for h in humans if int(h["human_manager_id"]) == int(me)]
    if len(humans) != 1:
        return None
    team = int(humans[0].get("team_id") or 0)
    return team if team in clubs else None


def ootp_job(m=None, cfg=None):
    m = m or current()
    if not m:
        return None
    clubs, humans = _club_context(m)
    return pick_job(
        humans, {c["id"] for c in clubs}, (cfg or config() or {}).get("human_manager_id")
    )


def active_team(m):
    """The club this front office works for: the GM's choice in game-access.json, as long as it
    is one of this export's MLB clubs; otherwise the club the export was imported for."""
    team = (config() or {}).get("team_id")
    try:
        team = int(team)
    except (TypeError, ValueError):
        return m["team_id"]
    return team if team in {c["id"] for c in mlb_clubs(m)} else m["team_id"]


def sync_team(m=None, announce=True):
    """Follow the GM's OOTP job. When an export shows him running a different MLB club (fired,
    resigned, hired somewhere new), the app switches to that club. Between jobs, the last club
    stays. Returns the change, or None. `announce` leaves a "new job" notice for the dashboard."""
    cfg = config() or {}
    m = m or current()
    if not m or not follows_ootp(cfg):
        return None
    job = ootp_job(m, cfg)
    if job is None or job == cfg.get("team_id"):
        return None
    by_id = {c["id"]: c for c in mlb_clubs(m)}
    old = by_id.get(cfg.get("team_id"), {})
    change = {
        "source": m.get("source_id"),
        "from": cfg.get("team_id"),
        "from_name": old.get("name") or cfg.get("human_team"),
        "to": job,
        "to_name": by_id[job]["name"],
        "game_date": m["game_date"],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    save_config(team_id=job, human_team=by_id[job]["name"])
    if announce:
        write_json(DATA / "team-change.json", change)
    return change


def choose_team(team=None, follow=False):
    """The GM picks the club himself, or goes back to following his OOTP job. Picking the club
    OOTP says he runs keeps following on; picking any other club turns it off, or the next export
    would snap him back."""
    m = current()
    if not m:
        raise ValueError("Import an OOTP export first.")
    by_id = {c["id"]: c for c in mlb_clubs(m)}
    if follow:
        save_config(follow_ootp=True)
        sync_team(m, announce=False)  # going back to his own job is not news
        (DATA / "team-change.json").unlink(missing_ok=True)
        return team_status()
    try:
        team = int(team)
    except (TypeError, ValueError):
        team = None
    if team not in by_id:
        raise ValueError("Choose one of the league's MLB clubs.")
    job = ootp_job(m)
    # Between OOTP jobs there's nothing to snap back to, so following stays as it was: the app
    # still moves when OOTP next gives him a club.
    follow = team == job or (job is None and follows_ootp())
    save_config(team_id=team, human_team=by_id[team]["name"], follow_ootp=follow)
    (DATA / "team-change.json").unlink(missing_ok=True)
    return team_status()


def team_status():
    m = current()
    if not m:
        return None
    cfg = config() or {}
    clubs = mlb_clubs(m)
    by_id = {c["id"]: c for c in clubs}
    team = active_team(m)
    job = ootp_job(m, cfg)
    change = read_json(DATA / "team-change.json")
    if change and (change.get("to") != team or change.get("source") != m.get("source_id")):
        change = None
    chosen = cfg.get("team_id") in by_id
    return {
        **by_id.get(team, {"id": team, "name": cfg.get("human_team") or str(team)}),
        "follow": follows_ootp(cfg),
        "ootp_job": job,
        "ootp_job_name": by_id.get(job, {}).get("name"),
        "clubs": clubs,
        "change": change,
        # A new save where OOTP doesn't say which club is his: the dashboard asks him to pick.
        "needs_pick": not chosen and job is None,
    }


# ---- which OOTP save (league) this front office reads ---------------------------------------


def save_label(csv_directory):
    lg = Path(csv_directory).parent.parent  # <save>.lg/import_export/csv
    return lg.name[:-3] if lg.name.lower().endswith(".lg") else lg.name or "Your league"


def saved_games_folders(cfg=None):
    """OOTP's saved_games folders: the one holding each known save, plus the standard Documents
    locations for any OOTP version, plus an optional `saved_games_directory` setting."""
    cfg = cfg if cfg is not None else config() or {}
    roots = []
    if cfg.get("saved_games_directory"):
        roots.append(Path(cfg["saved_games_directory"]))
    for c in [cfg.get("csv_directory")] + [
        s.get("csv_directory") for s in (cfg.get("saves") or {}).values()
    ]:
        if c:
            roots.append(Path(c).parent.parent.parent)
    for docs in (Path.home() / "Documents", Path.home() / "OneDrive" / "Documents"):
        roots.extend(sorted(docs.glob("Out of the Park Developments/OOTP Baseball */saved_games")))
    seen, unique = set(), []
    for r in roots:
        key = str(r.resolve()).casefold()
        if key not in seen and r.is_dir():
            seen.add(key)
            unique.append(r)
    return unique


def list_saves(cfg=None):
    """Every OOTP save the app can read, newest export first, with what we know about each."""
    cfg = cfg if cfg is not None else config() or {}
    active = active_source(cfg)
    memory = cfg.get("saves") or {}
    pointers = _pointers()
    saves = []
    for root in saved_games_folders(cfg):
        for lg in root.iterdir():
            if not lg.is_dir() or not lg.name.lower().endswith(".lg") or len(lg.name) <= 3:
                continue
            csv_dir = lg / "import_export" / "csv"
            files = list(csv_dir.glob("*.csv")) if csv_dir.is_dir() else []
            key = source_key(csv_dir)
            remembered = cfg if key == active else memory.get(key, {})
            m = read_json(SNAPSHOTS / pointers[key] / "manifest.json") if key in pointers else None
            saves.append(
                {
                    "source": key,
                    "name": lg.name[:-3],
                    "csv_directory": str(csv_dir).replace("\\", "/"),
                    "folder": str(root),
                    "active": key == active,
                    "has_export": bool(files),
                    "exported_at": (
                        datetime.fromtimestamp(max(f.stat().st_mtime for f in files)).isoformat()
                        if files
                        else None
                    ),
                    "game_date": m.get("game_date") if m else None,
                    "team": remembered.get("human_team"),
                }
            )
    saves.sort(key=lambda s: (not s["active"], not s["has_export"], s["name"].casefold()))
    return saves


def league_status(cfg=None):
    cfg = cfg if cfg is not None else config() or {}
    csv_dir = cfg.get("csv_directory")
    has_export = bool(csv_dir) and any(Path(csv_dir).glob("*.csv"))
    return {
        "source": active_source(cfg),
        "name": cfg.get("save_name") or (save_label(csv_dir) if csv_dir else "Your league"),
        "has_export": has_export,
    }


def choose_league(csv_directory):
    """Point the front office at another OOTP save. This save's settings are parked under
    "saves"; the other save's come back (or start fresh: follow OOTP, detect league and club)."""
    target = (
        next((s for s in list_saves() if s["source"] == source_key(csv_directory)), None)
        if csv_directory
        else None
    )
    if not target:
        raise ValueError("Choose one of your OOTP saves.")
    if not LOCK.acquire(blocking=False):
        raise ValueError("An import is running. Switch leagues when it finishes.")
    try:
        with CONFIG_LOCK:
            cfg = config() or {}
            memory = dict(cfg.get("saves") or {})
            here = active_source(cfg)
            if here:
                memory[here] = {k: cfg[k] for k in SAVE_KEYS if k in cfg}
            restored = dict(memory.get(target["source"]) or {})
            restored.setdefault("follow_ootp", True)
            restored.update(csv_directory=target["csv_directory"], save_name=target["name"])
            base = {k: v for k, v in cfg.items() if k not in SAVE_KEYS and k != "saves"}
            write_json(ROOT / "game-access.json", {**base, **restored, "saves": memory})
        STATUS.update(message="Ready", error=None)
    finally:
        LOCK.release()
    if target["has_export"]:
        start_import()  # brings in a newer export; a no-op when the last one is current
    return league_status()


def _first(con, queries, params=None):
    # Exports vary by OOTP version; use the most specific query whose columns exist.
    for sql in queries:
        try:
            return records(con, sql, params)
        except duckdb.BinderException:
            continue
    return []


def _top_leagues(con):
    """Leagues a GM can run a club in (top level, own MLB-level clubs), most clubs first."""
    rows = _first(
        con,
        [
            "select l.league_id, count(t.team_id) clubs from leagues l join teams t"
            " on t.league_id=l.league_id and t.level=1 and coalesce(t.allstar_team,0)=0"
            " where coalesce(l.league_level,1)=1 and coalesce(l.parent_league_id,0)=0"
            " group by l.league_id order by clubs desc, l.league_id",
            "select league_id, count(*) clubs from teams where level=1"
            " and coalesce(allstar_team,0)=0 group by 1 order by clubs desc, 1",
            "select league_id, count(*) clubs from teams group by 1 order by clubs desc, 1",
        ],
    )
    return [int(r["league_id"]) for r in rows]


def detect_league(con, wanted=None):
    """The league this front office works in: the configured one when this export has it, else
    the league the human GM's club plays in, else the biggest top-level league. A brand-new save
    needs no league id typed in."""
    tops = _top_leagues(con)
    if not tops:
        raise ValueError("This export has no top-level league with clubs.")
    try:
        wanted = int(wanted)
    except (TypeError, ValueError):
        wanted = None
    if wanted in tops:
        return wanted
    for h in _optional(
        con,
        "select t.league_id from human_managers h join teams t on t.team_id=h.team_id"
        " where coalesce(h.retired,0)=0 and t.level=1",
    ):
        if int(h["league_id"]) in tops:
            return int(h["league_id"])
    return tops[0]


def detect_team(con, league, cfg):
    """The club recorded on the snapshot: the configured one if it plays in this league, else
    the GM's OOTP job, else the first club (the dashboard then asks him to pick)."""
    clubs = [
        int(r["team_id"])
        for r in _first(
            con,
            [
                "select team_id from teams where league_id=? and level=1"
                " and coalesce(allstar_team,0)=0 order by name, nickname",
                "select team_id from teams where league_id=? order by team_id",
            ],
            [league],
        )
    ]
    try:
        team = int(cfg.get("team_id"))
    except (TypeError, ValueError):
        team = None
    if team in clubs:
        return team
    humans = _optional(
        con,
        "select human_manager_id, team_id, league_id from human_managers"
        " where coalesce(retired,0)=0",
    )
    return pick_job(humans, set(clubs), cfg.get("human_manager_id")) or (
        clubs[0] if clubs else None
    )


def import_snapshot(force=False):
    if not LOCK.acquire(blocking=False):
        return {"message": "An import is already running."}
    sid = None
    try:
        STATUS.update(running=True, message="Checking export files", error=None)
        cfg = config()  # one read: a league switch can't change the target mid-import
        before = signature(cfg["csv_directory"])
        old = current()
        if not before:
            raise ValueError(
                "No export from this save yet. In OOTP: Game Settings, Database, Database Tools,"
                " Export data to CSV files."
            )
        if old and old["signature"] == [list(x) for x in before] and not force:
            STATUS["message"] = "Already current"
            return old
        source = Path(cfg["csv_directory"])
        for table, fields in REQUIRED.items():
            with open(source / (table + ".csv"), encoding="utf-8-sig", newline="") as h:
                actual = next(csv.reader(h))
                missing = set(fields) - set(actual)
                if missing:
                    raise ValueError(f"{table}: missing columns {sorted(missing)}")
        sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder = SNAPSHOTS / sid
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
            if before != signature(source):
                raise ValueError(
                    "The export changed during import. Wait for OOTP to finish exporting, then refresh again."
                )
            lid = detect_league(con, cfg.get("league_id"))
            league = records(con, "select * from leagues where league_id=?", [lid])[0]
            team = detect_team(con, lid, cfg)
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
                "source_id": source_key(source),
                "save_name": cfg.get("save_name") or save_label(source),
                "season": int(league["season_year"]),
                "team_id": team,
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
        pointers = _pointers()
        pointers[manifest["source_id"]] = sid
        write_json(DATA / "current.json", {"id": sid, "saves": pointers})
        STATUS["message"] = "Snapshot ready"
        if manifest["source_id"] == active_source():
            try:
                if (config() or {}).get("league_id") != lid:
                    save_config(league_id=lid)
                sync_team(manifest)
            except Exception as e:  # the import itself succeeded; keep the current club
                STATUS["error"] = f"Imported, but could not check your OOTP job: {e}"
        prune()
        return manifest
    except Exception as e:
        # Only the incomplete directory created by this import can be removed.
        if sid:
            failed = (SNAPSHOTS / sid).resolve()
            if failed.parent == SNAPSHOTS.resolve() and not (failed / "manifest.json").exists():
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
            if not sig:  # this save has no export yet; nothing to import
                last, stable = sig, 0
                continue
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
