import io

import pytest


@pytest.mark.parametrize('stage',['intake','prepare','calculate','policy','balance'])
def test_stage_has_http_entry_and_no_database_write(client,stage):
    response=client.post('/api/stages/'+stage,data={'sample':'dirty'})
    assert response.status_code==200 and response.json['intake']['rejected']==5
    assert client.get('/api/runs').json=={'items':[]}


def test_upload_uses_input_content(client,clean):
    a=client.post('/api/runs',data={'file':(io.BytesIO(clean),'input.csv')})
    b=client.post('/api/runs',data={'sample':'clean'})
    assert a.status_code==200 and a.json['id']==b.json['id']


def test_unknown_stage_and_sample(client):
    assert client.post('/api/stages/unknown',data={'sample':'clean'}).status_code==404
    assert client.post('/api/runs',data={'sample':'unknown'}).status_code==404


def test_bad_upload_leaves_history_empty(client):
    result=client.post('/api/runs',data={'file':(io.BytesIO(b'wrong,header\n'),'bad.csv')})
    assert result.status_code==422 and result.json['code']=='HEADER_MISMATCH'
    assert client.get('/api/runs').json['items']==[]


def test_case_review_endpoint(client):
    run=client.post('/api/runs',data={'sample':'partial'}).json
    response=client.patch('/api/runs/'+run['id']+'/cases/0001',json={'revision':0,'status':'APPROVED','note':'0001 组核清放行'})
    assert response.status_code==200
    decision=next(d for d in response.json['decisions'] if d['case']=='0001')
    assert decision['status']=='APPROVED' and response.json['status']=='PENDING'


def test_case_review_rejects_unreleasable_group(client):
    run=client.post('/api/runs',data={'sample':'partial'}).json
    response=client.patch('/api/runs/'+run['id']+'/cases/0004',json={'revision':0,'status':'APPROVED','note':'冲突未核清'})
    assert response.status_code==409 and response.json['code']=='UNRESOLVED_ISSUES'


def test_case_review_unknown_paths(client):
    run=client.post('/api/runs',data={'sample':'partial'}).json
    assert client.patch('/api/runs/'+run['id']+'/cases/9999',json={'revision':0,'status':'HELD','note':'单外批组'}).status_code==404
    assert client.patch('/api/runs/unknown/cases/0001',json={'revision':0,'status':'HELD','note':'无此批次'}).status_code==404


def test_case_review_validates_fields_and_revision(client):
    run=client.post('/api/runs',data={'sample':'partial'}).json
    assert client.patch('/api/runs/'+run['id']+'/cases/0001',json={'revision':0,'status':'HELD','note':'短'}).status_code==422
    assert client.patch('/api/runs/'+run['id']+'/cases/0001',json={'revision':3,'status':'HELD','note':'版本超前'}).status_code==409
