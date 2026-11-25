import json
from hashlib import sha256

from app.evidence.render import artifact
from app.review.service import execute, review


def test_origin_checksum_matches_input(store, clean):
    output=json.loads(artifact(execute(store,clean)))
    assert output['manifest']['sha256']==sha256(clean).hexdigest()


def test_same_revision_bytes_are_deterministic(store, clean):
    run=execute(store,clean)
    assert artifact(run)==artifact(store.load(run['id']))


def test_export_preserves_isolated_row_numbers(store, dirty):
    output=json.loads(artifact(execute(store,dirty)))
    isolated=output['intake']['isolation']
    assert len(isolated)==5 and all(row['line']>1 for row in isolated)


def test_export_preserves_approved_note(store, clean):
    run=execute(store,clean)
    revised=review(store,run['id'],dict(revision=0,status='APPROVED',note='复核结果通过'))
    assert json.loads(artifact(revised))['review']['note']=='复核结果通过'


def test_evidence_404(client):
    assert client.get('/api/runs/unknown/evidence').status_code==404


def test_download_attachment(client):
    run=client.post('/api/runs',data={'sample':'clean'}).json
    response=client.get('/api/runs/'+run['id']+'/evidence')
    assert response.status_code==200 and 'attachment' in response.headers['Content-Disposition']
    assert response.json['schema']=='review-evidence/2'


from app.review.service import review_case


def test_export_lists_case_decisions(store, partial):
    run=execute(store,partial)
    review_case(store,run['id'],'0001',dict(revision=0,status='APPROVED',note='0001 组核清放行'))
    revised=review_case(store,run['id'],'0003',dict(revision=0,status='HELD',note='0003 组计划待整改'))
    output=json.loads(artifact(revised))
    decisions={d['case']:d for d in output['decisions']}
    assert decisions['0001']['status']=='APPROVED' and decisions['0001']['note']=='0001 组核清放行'
    assert decisions['0003']['status']=='HELD' and decisions['0003']['note']=='0003 组计划待整改'


def test_held_case_traces_back_to_source_lines(store, partial):
    run=execute(store,partial)
    review_case(store,run['id'],'0004',dict(revision=0,status='HELD',note='串组冲突待查'))
    output=json.loads(artifact(store.load(run['id'])))
    case=next(c for c in output['cases'] if c['case']=='0004')
    assert case['lines']['000401']==14
    holds=output['balance']['release']['cases']['0004']['holds']
    assert [row['line'] for row in holds]==[18] and holds[0]['record']=='000901'
