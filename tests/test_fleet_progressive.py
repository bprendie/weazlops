"""Explicit software fixtures. No physical timing, reception or device claims."""
import secrets,time,pytest
from app.store import Store
from app.service import Teams
from app.protocol import CALLSIGNS,package
class FixtureAdapter:
 def __init__(self):self.calls=[]
 def prepare(self,binding,image,plan,member):
  self.calls.append((binding,image,plan['id'],member['id']))
  assert image.startswith(b'WZLPK002')and image[24:30]==bytes.fromhex(binding['mac'].replace(':',''))
  return {'fixture':True,'actual_hardware':False}
def wait(service):
 deadline=time.monotonic()+5
 while service.jobs and time.monotonic()<deadline:time.sleep(.01)
 assert not service.jobs

def test_five_sequential_handouts_survive_absent_first_and_larger_bag(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));store=Store(tmp_path/'db',key);adapter=FixtureAdapter();service=Teams(store,adapter)
 slots=[{'product':'ghost'if i<3 else'drop','profile':'any','callsign':CALLSIGNS[i],'lead':i==0}for i in range(5)]
 public=service.create('Five fixture',slots,'1'*32);plan=store.get('team',public['id']);frozen=[(m['id'],m['public'],m['incarnation'])for m in plan['members']]
 bag=[{'mac':'02:00:00:00:00:'+f'{i+1:02X}','chip':'esp32s3'if i%2==0 else'esp32c5','product':'ghost'if i<3 else'drop','profile':('original'if i%2==0 else'xl')if i<3 else'headless','compatible':True}for i in range(8)]
 for i,member in enumerate(plan['members']):
  service.prepare(plan['id'],member['id'],bag[i]);wait(service)
  current=store.get('team',plan['id']);assert current['members'][i]['status']=='ready'
  assert [(m['id'],m['public'],m['incarnation'])for m in current['members']]==frozen
  assert len(adapter.calls)==i+1 # departed handouts are never accessed again
  for other in current['members']:
   if other['id']!=member['id']:assert bytes.fromhex(other['secret'])not in adapter.calls[-1][1]
 assert store.get('team',plan['id'])['state']=='ready'
 assert len(store.all('device'))==5 and not any(d['mac']in {b['mac']for b in bag[5:]}for d in store.all('device'))
 assert len({c[2]for c in adapter.calls})==1
 with pytest.raises(ValueError,match='1..5'):service.create('Six fixture',slots+[{'product':'ghost','callsign':CALLSIGNS[5]}],'2'*32)

def test_fresh_team_reissue_preserves_old_history_without_duplicate_current_owner(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));store=Store(tmp_path/'db',key);adapter=FixtureAdapter();service=Teams(store,adapter)
 slots=[{'product':'ghost','callsign':CALLSIGNS[0],'lead':True}];device={'mac':'02:00:00:00:00:01','chip':'esp32s3','product':'ghost','profile':'original','compatible':True}
 a=service.create('First',slots,'1'*32);service.prepare(a['id'],a['members'][0]['id'],device);wait(service)
 b=service.create('Second',slots,'2'*32);service.prepare(b['id'],b['members'][0]['id'],device);wait(service)
 assert store.get('team',a['id'])['members'][0]['status']=='reissued'
 assert store.get('device',device['mac'])['team']==b['id']
 assert store.get('team',a['id'])['root_public']!=store.get('team',b['id'])['root_public']
