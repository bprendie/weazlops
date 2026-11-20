import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store


def test_accounts_permissions_persistence_and_duplicate_creation(tmp_path):
    key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32))
    bootstrap=tmp_path/'bootstrap'
    bootstrap.write_text(json.dumps({'username':'OriginalAdmin','password':'synthetic-owner-password'}))
    def server():return create_app(tmp_path/'db',key,None,bootstrap)
    app=server()
    admin=TestClient(app)
    route='/api/settings/users'
    assert admin.get(route).status_code==401
    def login(client,user,password):
        result=client.post('/api/login',json={'username':user,'password':password})
        assert result.status_code==200
        return {'X-CSRF-Token':result.json()['csrf']}
    headers=login(admin,'originaladmin','synthetic-owner-password')
    original={'username':'OriginalAdmin','role':'admin'}
    assert admin.get(route).json()==[original]
    body={'username':'Liz','password':'synthetic-operator-pass'}
    assert admin.post(route,json=body).status_code==403
    assert admin.post(route,json=body,headers=headers|{'Origin':'https://different.invalid'}).status_code==403
    for invalid in [{'username':' '},{'username':'two words'},{'role':'unknown'},{'password':'short'}]:
        assert admin.post(route,json=body|invalid,headers=headers).status_code==400
    result=admin.post(route,json=body,headers=headers)
    assert result.status_code==201 and result.json()=={'username':'Liz','role':'operator'}
    assert admin.post(route,json=body|{'username':'LIZ','role':'admin'},headers=headers).status_code==409
    worker=TestClient(server())
    op_headers=login(worker,'liz',body['password'])
    assert worker.get('/api/session').json()['role']=='operator'
    assert worker.get('/api/teams').status_code==200
    assert worker.get(route).status_code==403
    assert worker.post(route,json=body|{'username':'NewAdmin','role':'admin'},headers=op_headers).status_code==403
    assert admin.post(route,json=body|{'username':'Bob','role':'admin'},headers=headers).status_code==201
    other=TestClient(server());login(other,'Bob',body['password'])
    assert other.get(route).json()==[{'username':'Bob','role':'admin'},result.json(),original]
    # Different processes can race to create the same case-insensitive login.
    def compete(name):
        try:Store(tmp_path/'db',key).create_account(name,'a-synthetic-password');return True
        except FileExistsError:return False
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(compete,['Sam','sam']))==[False,True]
