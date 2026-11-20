import json,secrets
from fastapi.testclient import TestClient
from app.main import create_app
class ReadOnlyAdapter:
 def discover(self):return []
def test_login_scope_csrf_restart_and_plan(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));bootstrap=tmp_path/'bootstrap';bootstrap.write_text(json.dumps({'username':'adminguy','password':'synthetic-owner-password'}))
 app=create_app(tmp_path/'db',key,ReadOnlyAdapter(),bootstrap);client=TestClient(app)
 assert client.get('/api/teams').status_code==401
 assert client.post('/api/login',json={'username':'adminguy','password':'wrong'}).status_code==401
 r=client.post('/api/login',json={'username':'adminguy','password':'synthetic-owner-password'});assert r.status_code==200;csrf=r.json()['csrf'];headers={'X-CSRF-Token':csrf}
 body={'name':'Tonight','request_id':'b'*32,'members':[{'product':'ghost','callsign':'STONEY','lead':True,'profile':'any'}]}
 assert client.post('/api/teams',json=body).status_code==403
 r=client.post('/api/teams',json=body,headers=headers);assert r.status_code==200
 assert 'secret'not in json.dumps(r.json())
 assert client.post('/api/teams',json=body,headers=headers).json()['id']==r.json()['id']
 assert client.post('/api/teams',json=body,headers=headers|{'Origin':'http://attacker.invalid'}).status_code==403
 restarted=TestClient(create_app(tmp_path/'db',key,ReadOnlyAdapter(),bootstrap));restarted.cookies.update(client.cookies)
 assert len(restarted.get('/api/teams').json())==1
 assert restarted.get('/').status_code==200
 assert client.post('/api/logout',json={},headers=headers).status_code==200
 assert restarted.get('/api/teams').status_code==401


def test_removing_team_keeps_custody_and_cannot_revoke_absent_device(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));bootstrap=tmp_path/'bootstrap';bootstrap.write_text(json.dumps({'username':'adminguy','password':'synthetic-owner-password'}))
 app=create_app(tmp_path/'db',key,ReadOnlyAdapter(),bootstrap);client=TestClient(app);csrf=client.post('/api/login',json={'username':'adminguy','password':'synthetic-owner-password'}).json()['csrf'];h={'X-CSRF-Token':csrf}
 plan=client.post('/api/teams',json={'name':'Removable','request_id':'a'*32,'members':[{'product':'ghost','callsign':'STONEY','lead':True}]},headers=h).json();id=plan['id'];secret=app.state.store.get('team',id)['recovery_private']
 assert client.post('/api/teams/'+id+'/delete',json={},headers=h).status_code==400
 assert client.post('/api/teams/'+id+'/delete',json={'confirm':'REMOVE TEAM FROM LIST'},headers=h).status_code==400
 assert client.post('/api/teams/'+id+'/delete',json={'confirm':'REMOVE TEAM FROM LIST','team_name':'Wrong'},headers=h).status_code==400
 app.state.teams.jobs.add((id,plan['members'][0]['id']))
 assert client.post('/api/teams/'+id+'/delete',json={'confirm':'REMOVE TEAM FROM LIST','team_name':'Removable'},headers=h).status_code==400
 app.state.teams.jobs.clear()
 result=client.post('/api/teams/'+id+'/delete',json={'confirm':'REMOVE TEAM FROM LIST','team_name':'Removable'},headers=h).json()
 assert result['devices_cleared']==0 and result['custody_retained']and client.get('/api/teams').json()==[]
 assert client.get('/api/teams/'+id).status_code==404
 assert app.state.store.get('team',id)['recovery_private']==secret
