from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.business import DomainIssue
from app.review.service import execute, review


def test_parallel_rerun_commits_single_row(store, clean):
    start=Barrier(4)
    def load():
        start.wait(3)
        return execute(store,clean)
    with ThreadPoolExecutor(max_workers=4) as threads:
        results=list(threads.map(lambda _:load(),range(4)))
    assert all(result==results[0] for result in results)
    assert len(store.list())==1


def test_parallel_review_has_one_winner(store, dirty):
    run=execute(store,dirty); start=Barrier(2)
    def attempt(note):
        start.wait(3)
        try:
            return review(store,run['id'],dict(revision=0,status='HELD',note=note))['status']
        except DomainIssue as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as threads:
        results=list(threads.map(attempt,['来源待检查','分组待处理']))
    assert sorted(results)==['HELD','STALE_REVIEW']
    assert store.load(run['id'])['revision']==1


from app.review.service import review_case


def test_parallel_case_reviews_both_commit(store, partial):
    run=execute(store,partial); start=Barrier(2)
    def attempt(case,status,note):
        start.wait(3)
        try:
            return review_case(store,run['id'],case,dict(revision=0,status=status,note=note))['status']
        except DomainIssue as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as threads:
        results=list(threads.map(lambda args:attempt(*args),[('0001','APPROVED','甲签发 0001'),('0002','HELD','乙暂缓 0002')]))
    assert all(result in ('PENDING','HELD') for result in results)
    final=store.load(run['id'])
    decisions={d['case']:d for d in final['decisions']}
    assert decisions['0001']['status']=='APPROVED' and decisions['0001']['note']=='甲签发 0001'
    assert decisions['0002']['status']=='HELD' and decisions['0002']['note']=='乙暂缓 0002'
    assert final['revision']==2 and final['status']=='HELD'


def test_parallel_same_case_has_one_winner(store, partial):
    run=execute(store,partial); start=Barrier(2)
    def attempt(note):
        start.wait(3)
        try:
            return review_case(store,run['id'],'0001',dict(revision=0,status='HELD',note=note))['status']
        except DomainIssue as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as threads:
        results=list(threads.map(attempt,['来源待检查','分组待处理']))
    assert sorted(results)==['HELD','STALE_REVIEW']
    decision=next(d for d in store.load(run['id'])['decisions'] if d['case']=='0001')
    assert decision['revision']==1


def test_parallel_case_and_run_review_one_winner(store, partial):
    run=execute(store,partial); start=Barrier(2)
    def group():
        start.wait(3)
        try:
            return review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='分组签发'))['status']
        except DomainIssue as error:
            return error.code
    def whole():
        start.wait(3)
        try:
            return review(store,run['id'],dict(revision=0,status='HELD',note='整单暂缓'))['status']
        except DomainIssue as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as threads:
        results=list(threads.map(lambda fn:fn(),[group,whole]))
    assert results.count('STALE_REVIEW')==1
    final=store.load(run['id'])
    assert final['revision']==1
    if results[0]=='STALE_REVIEW':
        assert {d['case'] for d in final['decisions']}=={'0001','0002','0003','0004'}
    else:
        assert [d['case'] for d in final['decisions']]==['0001']
