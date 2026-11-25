import pytest

from app.business import DomainIssue
from app.review.service import execute, review


def test_byte_identical_rerun_keeps_run_and_manifest(store, clean):
    first=execute(store,clean); second=execute(store,clean)
    assert first==second and len(store.list())==1


def test_different_source_starts_new_run(store, clean, dirty):
    assert execute(store,clean)['id']!=execute(store,dirty)['id']
    assert len(store.list())==2


def test_valid_approval_trims_note(store, clean):
    run=execute(store,clean)
    output=review(store,run['id'],dict(revision=0,status='APPROVED',note='  源文件已复核  '))
    assert (output['status'],output['revision'],output['note'])==('APPROVED',1,'源文件已复核')


def test_review_optimistic_lock(store, dirty):  # TRAP-26
    run=execute(store,dirty); update=dict(revision=0,status='HELD',note='请核对样例')
    review(store,run['id'],update)
    with pytest.raises(DomainIssue,match='STALE_REVIEW'): review(store,run['id'],update)


def test_dirty_batch_cannot_be_approved(store, dirty):
    run=execute(store,dirty)
    with pytest.raises(DomainIssue,match='UNRESOLVED_ISSUES'):
        review(store,run['id'],dict(revision=0,status='APPROVED',note='核对已完成'))
    assert store.load(run['id'])['revision']==0


def test_approved_batch_is_final(store, clean):
    run=execute(store,clean)
    review(store,run['id'],dict(revision=0,status='APPROVED',note='完成最终复核'))
    with pytest.raises(DomainIssue,match='RUN_FINALIZED'):
        review(store,run['id'],dict(revision=1,status='HELD',note='试图撤销签发'))


from app.review.service import review_case


def decide(run, case):
    return next((d for d in run['decisions'] if d['case']==case), None)


def test_case_approval_leaves_run_pending(store, partial):
    run=execute(store,partial)
    output=review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='0001 组核清放行'))
    decision=decide(output,'0001')
    assert (decision['status'],decision['revision'],decision['note'])==('APPROVED',1,'0001 组核清放行')
    assert output['status']=='PENDING' and output['revision']==1


def test_case_hold_then_rereview(store, partial):
    run=execute(store,partial)
    held=review_case(store,run['id'],'0002',dict(revision=0,status='HELD',note='0002 组等待补单'))
    assert decide(held,'0002')['status']=='HELD' and held['status']=='HELD'
    output=review_case(store,run['id'],'0002',dict(revision=1,status='APPROVED',note='补单已到，放行'))
    assert decide(output,'0002')['status']=='APPROVED'


def test_case_approval_requires_releasable_group(store, partial):
    run=execute(store,partial)
    with pytest.raises(DomainIssue,match='UNRESOLVED_ISSUES'):
        review_case(store,run['id'],'0004',dict(revision=0,status='APPROVED',note='冲突未核清'))
    with pytest.raises(DomainIssue,match='UNRESOLVED_ISSUES'):
        review_case(store,run['id'],'0003',dict(revision=0,status='APPROVED',note='判定未通过'))
    assert store.load(run['id'])['decisions']==[]


def test_blocked_order_rejects_any_case_approval(store, dirty):
    run=execute(store,dirty)
    with pytest.raises(DomainIssue,match='UNRESOLVED_ISSUES'):
        review_case(store,run['id'],'0002',dict(revision=0,status='APPROVED',note='整单待查中'))
    held=review_case(store,run['id'],'0002',dict(revision=0,status='HELD',note='坏行归属未查清'))
    assert decide(held,'0002')['status']=='HELD'


def test_case_review_optimistic_lock(store, partial):
    run=execute(store,partial)
    review_case(store,run['id'],'0001',dict(revision=0,status='HELD',note='请核对样例'))
    with pytest.raises(DomainIssue,match='STALE_REVIEW'):
        review_case(store,run['id'],'0001',dict(revision=0,status='HELD',note='重复提交'))


def test_approved_case_is_final(store, partial):
    run=execute(store,partial)
    review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='核清放行'))
    with pytest.raises(DomainIssue,match='CASE_FINALIZED'):
        review_case(store,run['id'],'0001',dict(revision=1,status='HELD',note='试图撤销'))


def test_unknown_case_is_rejected(store, partial):
    run=execute(store,partial)
    with pytest.raises(DomainIssue,match='CASE_UNKNOWN'):
        review_case(store,run['id'],'0005',dict(revision=0,status='HELD',note='单外批组'))


def test_approving_every_case_finalizes_run(store, clean):
    run=execute(store,clean)
    review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='放行 0001'))
    output=review_case(store,run['id'],'0002',dict(revision=0,status='APPROVED',note='放行 0002'))
    assert output['status']=='APPROVED'
    with pytest.raises(DomainIssue,match='RUN_FINALIZED'):
        review_case(store,run['id'],'0001',dict(revision=1,status='HELD',note='试图撤销'))
    with pytest.raises(DomainIssue,match='RUN_FINALIZED'):
        review(store,run['id'],dict(revision=2,status='HELD',note='试图整单暂缓'))


def test_run_level_review_fans_out_to_cases(store, dirty):
    run=execute(store,dirty)
    output=review(store,run['id'],dict(revision=0,status='HELD',note='整单暂缓'))
    assert output['status']=='HELD'
    assert {d['case'] for d in output['decisions']}=={'0001','0002','0003','0004'}
    assert all(d['status']=='HELD' and d['note']=='整单暂缓' for d in output['decisions'])


def test_run_level_approval_fills_remaining_cases(store, clean):
    run=execute(store,clean)
    review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='先放行 0001'))
    output=review(store,run['id'],dict(revision=1,status='APPROVED',note='其余组一并签发'))
    assert output['status']=='APPROVED'
    assert decide(output,'0001')['note']=='先放行 0001'
    assert decide(output,'0002')['note']=='其余组一并签发'


def test_case_review_invalidates_stale_run_revision(store, partial):
    run=execute(store,partial)
    review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='放行 0001'))
    with pytest.raises(DomainIssue,match='STALE_REVIEW'):
        review(store,run['id'],dict(revision=0,status='HELD',note='过期整批复核'))
