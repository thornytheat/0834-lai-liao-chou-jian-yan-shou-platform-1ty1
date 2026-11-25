from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic

from app.business import DomainIssue
from app.config import RULE_VERSION
from app.modules.pipeline import run


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def execute(store, data):
    start = monotonic()
    fingerprint = sha256(data).hexdigest()
    run_id = sha256(f'{RULE_VERSION}:{fingerprint}'.encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != 'RUN_NOT_FOUND':
            raise
    report = run(data)
    report['manifest'] = dict(sha256=fingerprint, version=RULE_VERSION, created=now(),
                              duration_ms=round((monotonic()-start)*1000,3), bytes=len(data), run_id=run_id)
    return store.register(run_id,report)


def validate(values):
    if not isinstance(values, dict):
        raise DomainIssue('REVIEW_FIELDS')
    revision, status, note = (values.get(key) for key in ('revision','status','note'))
    if type(revision) is not int or revision < 0 or status not in ('APPROVED','HELD') or not isinstance(note,str) or not (3<=len(note.strip())<=200):
        raise DomainIssue('REVIEW_FIELDS')
    return revision, status, note.strip()


def review(store, run_id, values):
    revision, status, note = validate(values)
    current = store.load(run_id)
    if revision != current['revision']:
        raise DomainIssue('STALE_REVIEW')
    if current['status'] == 'APPROVED':
        raise DomainIssue('RUN_FINALIZED')
    if status == 'APPROVED' and not current['report']['balance']['releasable']:
        raise DomainIssue('UNRESOLVED_ISSUES')
    approved = {d['case'] for d in current['decisions'] if d['status'] == 'APPROVED'}
    decisions = [(case['case'], status) for case in current['report']['cases'] if case['case'] not in approved]
    return store.revise(run_id,revision,status,note,now(),decisions)


def review_case(store, run_id, case, values):
    revision, status, note = validate(values)
    current = store.load(run_id)
    if current['status'] == 'APPROVED':
        raise DomainIssue('RUN_FINALIZED')
    cases = {c['case'] for c in current['report']['cases']}
    if case not in cases:
        raise DomainIssue('CASE_UNKNOWN')
    decision = next((d for d in current['decisions'] if d['case'] == case), None)
    if decision and decision['status'] == 'APPROVED':
        raise DomainIssue('CASE_FINALIZED')
    if revision != (decision['revision'] if decision else 0):
        raise DomainIssue('STALE_REVIEW')
    if status == 'APPROVED':
        balance = current['report']['balance']
        if not balance['balanced'] or not balance['release']['cases'][case]['releasable']:
            raise DomainIssue('UNRESOLVED_ISSUES')
    return store.revise_case(run_id,case,revision,status,note,now())
