from app.modules.pipeline import run
from app.modules.reconcile import balance
from conftest import csv_data


def test_input_row_conservation(dirty):
    checks=run(dirty)['balance']
    assert checks['input']==checks['accepted']+checks['isolated']+checks['ignored']


def test_business_cases_conserve_input(dirty):
    report=run(dirty)
    assert len(report['cases'])==4
    assert sum(len(c['records']) for c in report['cases'])==report['balance']['accepted']


def test_clean_case_set_is_releasable(clean):
    assert run(clean)['balance']['releasable'] is True


def test_dirty_case_set_is_blocked(dirty):
    checks=run(dirty)['balance']
    assert checks['isolated']==5 and checks['pending']==2 and not checks['releasable']


def test_empty_case_set_cannot_release():
    checks=balance(dict(input=1,accepted=0,rejected=0,blank=1,repeated=0),[])
    assert checks['balanced'] and not checks['releasable']


def test_miscounted_lines_cannot_release():
    checks=balance(dict(input=9,accepted=1,rejected=0,blank=0,repeated=0),[dict(records=['a'],status='READY')])
    assert not checks['balanced'] and not checks['releasable']


def release_of(data):
    return run(data)['balance']['release']


def test_dirty_order_is_blocked_by_unattributable_row(dirty):
    release = release_of(dirty)
    assert release['blocked'] is True
    assert [row['reason'] for row in release['unattributed']] == ['COLUMN_COUNT']
    assert all(not group['releasable'] for group in release['cases'].values())


def test_isolation_rows_attribute_to_named_case(dirty):
    holds = release_of(dirty)['holds']
    assert [row['reason'] for row in holds['0001']] == ['DUPLICATE_REPLAY']
    assert sorted(row['reason'] for row in holds['9999']) == ['DUPLICATE_CONFLICT']*2 + ['MISSING_NUMBER']


def test_partial_order_releases_checked_groups(partial):
    release = release_of(partial)
    assert release['blocked'] is False
    assert release['cases']['0001']['releasable'] is True
    assert release['cases']['0002']['releasable'] is True
    assert release['cases']['0003']['releasable'] is False
    assert not release['cases']['0003']['holds']


def test_cross_case_conflict_holds_involved_groups(partial):
    release = release_of(partial)
    assert release['cases']['0004']['releasable'] is False
    assert [row['line'] for row in release['cases']['0004']['holds']] == [18]
    assert [row['case'] for row in release['holds']['0005']] == ['0005']


def test_unreadable_case_blocks_whole_order(clean):
    rows = clean.decode().splitlines()
    rows.append('BAD9,@批次,plan,1,0,0,0,0,批组无法辨认')
    release = release_of('\n'.join(rows).encode() + b'\n')
    assert release['blocked'] is True and release['unattributed'][0]['reason'] == 'BAD_IDENTIFIER'
    assert all(not group['releasable'] for group in release['cases'].values())


def test_column_count_row_cannot_be_attributed(clean):
    rows = clean.decode().splitlines()
    rows.append('000901,0001,plan,1,0,0,0,0,多出一列,串列')
    release = release_of('\n'.join(rows).encode() + b'\n')
    assert release['blocked'] is True and release['unattributed'][0]['reason'] == 'COLUMN_COUNT'


def test_same_case_conflict_only_holds_that_case(clean):
    rows = clean.decode().splitlines()
    rows += ['000901,0001,observed,0,3,0,0,0,重发前数据', '000901,0001,observed,0,3,0,1,0,重发前数据']
    release = release_of('\n'.join(rows).encode() + b'\n')
    assert release['blocked'] is False
    assert release['cases']['0001']['releasable'] is False
    assert release['cases']['0002']['releasable'] is True
