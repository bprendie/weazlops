"""Software fixtures, NOT physical offline pairing or five-device timing proof."""
import json,secrets,struct,pytest
from app.protocol import *
from app.offline import Offline
from app.store import Store
from test_offline_custody import escrow

def receipt(p,m,nonce):
 return b'WZLTI001'+bytes.fromhex(p['id'])+struct.pack('<II',1,1)+digest(bytes.fromhex(p['roster'])[:638])+struct.pack('<I',1)+CONFIG+bytes.fromhex(p['operation'])+nonce+struct.pack('<Q',int(m['id']))+b'\1'
class Adapter:
 def __init__(self,plan,binding):self.plan=plan;self.binding=binding;self.fail=False;self.calls=0;self.store=None
 def offline(self,binding):
  p=self.plan;m=p['members'][0];nonce=secrets.token_bytes(32);key=load(bytes.fromhex(m['secret']));image=package(p,m,binding['mac'],binding['chip'],binding['profile']);proof=b'WZLPP002'+digest(image[:-73])+nonce+bytes.fromhex(binding['mac'].replace(':',''))+b'\1\1'+struct.pack('<Q',int(m['id']))+b'\2';r=receipt(p,m,nonce)
  return {'blob':escrow(p).hex(),'assignments':[{'member':m['id'],'phase':2}]+[{'member':m['id'],'phase':0}for m in p['members'][1:]],'member':m['id'],'public':m['public'],'certificate':p['certificate'],'nonce':nonce.hex(),'physical':[proof.hex(),sign(key,b'WZL ONE VISIT INSTALLED V2\0'+proof).hex()],'receipt':[r.hex(),sign(key,b'WZL TEAM INSTALLED V1\0'+r).hex()],'owner':[p['recipient'],sign(key,b'WZL-RECIPIENT-V1\0'+bytes.fromhex(p['certificate'])[8:16]+bytes.fromhex(p['recipient'])+nonce).hex()]}
 def custody(self,binding,digest_hex,nonce_hex,signature_hex):
  self.calls+=1;p=self.store.get('team',self.plan['id']);assert p and p['recovery_private']and p['root_secret']
  verify(bytes.fromhex(p['root_public']),bytes.fromhex(signature_hex),b'WZL CUSTODY COMMIT V1\0'+bytes.fromhex(digest_hex+nonce_hex+p['id']))
  if self.fail:raise TimeoutError('Synthetic lost ACK')
  return {'acknowledged':True}

def setup(tmp_path,count=3):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));store=Store(tmp_path/'db',key)
 names=CALLSIGNS[:count];p=new_plan('Offline fixture',[{'product':'ghost'if i!=2 else'drop','callsign':names[i],'lead':i==0}for i in range(count)]);binding={'mac':'02:00:00:00:00:01','chip':'esp32s3','profile':'original','product':'ghost'};adapter=Adapter(p,binding);adapter.store=store;return Offline(store,adapter),store,adapter,p,binding

def test_lost_ack_retains_durable_custody_and_retries_without_rekey(tmp_path):
 flow,store,adapter,p,b=setup(tmp_path,5);preview=flow.preview(b)
 assert not store.all('team')and adapter.calls==0
 assert 'root_secret'not in json.dumps(preview)and 'recovery_private'not in json.dumps(preview)
 adapter.fail=True;result=flow.commit(preview['preview']);assert result['durable']and not result['lead_private_cleanup']
 saved=store.get('team',p['id']);assert saved['root_secret']==p['root_secret']and saved['certificate']==p['certificate']
 adapter.fail=False;result=flow.commit(preview['preview']);assert result['lead_private_cleanup']and len(store.all('team'))==1
 again=flow.commit(preview['preview']);assert again['team']['id']==p['id']and len(store.all('team'))==1
 assert bytes.fromhex(p['root_secret'])not in store.path.read_bytes()

def test_failed_durable_save_never_sends_cleanup(tmp_path,monkeypatch):
 flow,store,adapter,p,b=setup(tmp_path);preview=flow.preview(b);original=store.pack
 def fail(kind,id,obj):
  if kind=='device':raise OSError('Synthetic full disk after team SQL write')
  return original(kind,id,obj)
 monkeypatch.setattr(store,'pack',fail)
 with pytest.raises(OSError):flow.commit(preview['preview'])
 assert adapter.calls==0 and not store.all('team')and not store.all('device')

def test_conflicting_existing_authority_not_overwritten(tmp_path):
 flow,store,adapter,p,b=setup(tmp_path);other={**p,'roster':'00'*711};store.put('team',p['id'],other)
 with pytest.raises(ValueError):flow.preview(b)
 assert store.get('team',p['id'])==other

def test_expired_preview_never_acknowledges(tmp_path):
 flow,store,adapter,p,b=setup(tmp_path);preview=flow.preview(b);store.modify('offline-preview',preview['preview'],lambda row:row.update(expires=0))
 with pytest.raises(ValueError):flow.commit(preview['preview'])
 assert adapter.calls==0


def test_current_creator_assignment_replaces_old_fleet_owner(tmp_path):
 flow,store,adapter,p,b=setup(tmp_path)
 old=new_plan('Previous fixture',[{'product':'ghost','callsign':CALLSIGNS[0],'lead':True}]);old['members'][0].update(binding=b,status='ready');store.put('team',old['id'],old)
 preview=flow.preview(b);result=flow.commit(preview['preview']);assert result['durable']
 assert store.get('device',b['mac'])['team']==p['id']
 assert store.get('team',old['id'])['members'][0]['status']=='reissued'
 assert store.get('team',p['id'])['members'][1]['status']=='waiting'


def test_reissue_after_preview_rejects_stale_current_assignment(tmp_path):
 flow,store,adapter,p,b=setup(tmp_path);preview=flow.preview(b)
 import time
 store.put('device',b['mac'],{'team':'another','verified_at':time.time()+1})
 with pytest.raises(ValueError,match='reissued after inspection'):flow.commit(preview['preview'])
 assert adapter.calls==0 and not store.all('team')
