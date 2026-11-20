"""Wizard/discovery regressions; synthetic USB fixtures, not physical acceptance."""
import json,secrets,time
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import create_app
from app.native import Native
import app.native as module

def port(mac):return SimpleNamespace(serial_number=mac,device='/dev/fixture-'+mac,vid=0x303a)
def test_arrival_outside_inventory_and_explicit_restriction(tmp_path,monkeypatch):
 fresh='02:00:00:00:00:01';excluded='02:00:00:00:00:02';rows=[port(fresh),port(excluded)]
 monkeypatch.setattr(module.list_ports,'comports',lambda:rows);native=Native(tmp_path,None,[excluded]);opened=[]
 class Unit:
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def exchange(self,line,*a,**kw):
   if line=='gig identity':return 'GIG IDENTITY '+fresh+' esp32c5'
   return 'PLAN CAPABILITY 2 PROFILE 2'
 def unit(mac):opened.append(mac);assert mac!=excluded;return Unit()
 monkeypatch.setattr(native,'unit',unit)
 found=native.discover();assert len(found)==2 and found[0]['profile']=='xl' and found[0]['compatible']
 assert found[1]['discovery']=='restricted' and not found[1]['compatible'] and opened==[fresh]
 # Disconnection drops cached identity. Rearrival must probe again.
 rows.clear();assert native.discover()==[];rows.append(port(fresh));native.discover();assert opened==[fresh,fresh]

def test_unresponsive_arrival_visible_and_bounded_retry(tmp_path,monkeypatch):
 mac='02:00:00:00:00:03';monkeypatch.setattr(module.list_ports,'comports',lambda:[port(mac)]);native=Native(tmp_path);calls=[]
 def unit(mac):calls.append(mac);raise TimeoutError('fixture: no application')
 monkeypatch.setattr(native,'unit',unit)
 d=native.discover()[0];assert d['discovery']=='unresponsive' and not d['compatible']
 native.discover();assert len(calls)==1 # no repeated 3s probe every poll
 native.cache[mac]['checked_at']-=11;native.discover();assert len(calls)==2

class Adapter:
 def discover(self):return []
def test_field_checks_explicit_persisted_and_do_not_change_security(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));boot=tmp_path/'boot';boot.write_text(json.dumps({'username':'adminguy','password':'synthetic-wizard-password'}))
 app=create_app(tmp_path/'db',key,Adapter(),boot);client=TestClient(app);csrf=client.post('/api/login',json={'username':'adminguy','password':'synthetic-wizard-password'}).json()['csrf'];h={'X-CSRF-Token':csrf}
 plan=client.post('/api/teams',headers=h,json={'name':'Wizard','request_id':'f'*32,'members':[{'product':'ghost','callsign':'STONEY','lead':True,'profile':'any'}]}).json();url='/api/teams/'+plan['id']+'/journey'
 assert client.post(url,headers=h,json={'checks':{'drop':True}}).status_code==400
 store=app.state.store;store.modify('team',plan['id'],lambda p:p.update(state='ready'));old=store.get('team',plan['id'])
 assert client.post(url,json={'checks':{'drop':True}}).status_code==403
 assert client.post(url,headers=h,json={'checks':{'drop':'passed'}}).status_code==400
 result=client.post(url,headers=h,json={'checks':{'names':True,'drop':False}});assert result.status_code==200 and result.json()['journey']['source']=='operator-reported'
 updated=store.get('team',plan['id']);assert all(updated[k]==old[k]for k in ('root_secret','roster','members','recovery_private'))
 restarted=TestClient(create_app(tmp_path/'db',key,Adapter(),boot));restarted.cookies.update(client.cookies);assert restarted.get('/api/teams/'+plan['id']).json()['journey']['checks']=={'names':True,'drop':False}
