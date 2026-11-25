import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue
from app.modules.reconcile import release

SCHEMA = '''CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);
CREATE TABLE IF NOT EXISTS case_reviews (
    run_id TEXT NOT NULL, "case" TEXT NOT NULL,
    status TEXT NOT NULL, note TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0, reviewed TEXT NOT NULL,
    PRIMARY KEY (run_id, "case")
);'''

DECISION_KEYS = '"case",status,note,revision,reviewed'


def derive(cases, decisions):
    decided = {d['case']: d['status'] for d in decisions}
    if cases and all(decided.get(case) == 'APPROVED' for case in cases):
        return 'APPROVED'
    if any(status == 'HELD' for status in decided.values()):
        return 'HELD'
    return 'PENDING'


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.executescript(SCHEMA)
            yield db

    def register(self, run_id, report):
        with self.connect() as db:
            db.execute('INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',
                       (run_id,json.dumps(report,ensure_ascii=False),report['manifest']['created']))
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise DomainIssue('RUN_NOT_FOUND')
            decisions = [dict(r) for r in db.execute(f'SELECT {DECISION_KEYS} FROM case_reviews WHERE run_id=? ORDER BY "case"',(run_id,))]
        result = dict(row)
        result['report'] = json.loads(result['report'])
        balance = result['report'].get('balance')
        if balance is not None and 'release' not in balance:
            balance['release'] = release(result['report']['intake'], result['report']['cases'])
        result['decisions'] = decisions
        return result

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50')]

    def revise(self, run_id, revision, status, note, now, decisions):
        with self.connect() as db:
            cursor = db.execute('UPDATE runs SET note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=?',
                                (note,now,run_id,revision))
            if cursor.rowcount != 1:
                raise DomainIssue('STALE_REVIEW')
            for case, decision in decisions:
                db.execute('''INSERT INTO case_reviews(run_id,"case",status,note,revision,reviewed) VALUES (?,?,?,?,1,?)
                              ON CONFLICT(run_id,"case") DO UPDATE SET status=excluded.status,note=excluded.note,
                              reviewed=excluded.reviewed,revision=case_reviews.revision+1
                              WHERE case_reviews.status<>'APPROVED' ''',
                           (run_id,case,decision,note,now))
            cases = [c['case'] for c in json.loads(db.execute('SELECT report FROM runs WHERE id=?',(run_id,)).fetchone()['report'])['cases']]
            decided = [dict(r) for r in db.execute(f'SELECT {DECISION_KEYS} FROM case_reviews WHERE run_id=?',(run_id,))]
            db.execute('UPDATE runs SET status=? WHERE id=?',(derive(cases,decided) if decided else status,run_id))
        return self.load(run_id)

    def revise_case(self, run_id, case, revision, status, note, now):
        with self.connect() as db:
            row = db.execute('SELECT status,report FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise DomainIssue('RUN_NOT_FOUND')
            if row['status'] == 'APPROVED':
                raise DomainIssue('RUN_FINALIZED')
            cases = [c['case'] for c in json.loads(row['report'])['cases']]
            if case not in cases:
                raise DomainIssue('CASE_UNKNOWN')
            existing = db.execute('SELECT revision,status FROM case_reviews WHERE run_id=? AND "case"=?',(run_id,case)).fetchone()
            if existing is None:
                if revision != 0:
                    raise DomainIssue('STALE_REVIEW')
                cursor = db.execute('INSERT INTO case_reviews(run_id,"case",status,note,revision,reviewed) VALUES (?,?,?,?,1,?) ON CONFLICT(run_id,"case") DO NOTHING',
                                    (run_id,case,status,note,now))
                if cursor.rowcount != 1:
                    raise DomainIssue('STALE_REVIEW')
            else:
                if existing['status'] == 'APPROVED':
                    raise DomainIssue('CASE_FINALIZED')
                cursor = db.execute('UPDATE case_reviews SET status=?,note=?,reviewed=?,revision=revision+1 WHERE run_id=? AND "case"=? AND revision=?',
                                    (status,note,now,run_id,case,revision))
                if cursor.rowcount != 1:
                    raise DomainIssue('STALE_REVIEW')
            decided = [dict(r) for r in db.execute(f'SELECT {DECISION_KEYS} FROM case_reviews WHERE run_id=?',(run_id,))]
            cursor = db.execute("UPDATE runs SET status=?,reviewed=?,revision=revision+1 WHERE id=? AND status<>'APPROVED'",
                                (derive(cases,decided),now,run_id))
            if cursor.rowcount != 1:
                raise DomainIssue('RUN_FINALIZED')
        return self.load(run_id)
