import json,secrets,threading,time
import pytest
from app.store import Store,password_hash
from app.service import Teams
class DeferredAdapter:
 def __init__(self):self.pending=threading.Event();self.calls=0
 def prepare(self,*args):self.calls+=1;self.pending.wait(2);raise TimeoutError('Synthetic lost connection')
@pytest.fixture
def store(tmp_path):
 key=tmp_path/'master';key.write_bytes(secrets.token_bytes(32));return Store(tmp_path/'db',key)
def test_encrypted_access_sessions_and_aad(store):
 store.put('account','a',{'password':password_hash('synthetic-test-password')})
 assert not store.login('a','wrong');token=store.login('a','synthetic-test-password');assert store.session(token)['username']=='a'
 store.put('team','x',{'private':'synthetic-sensitive-material'})
 assert b'synthetic-sensitive-material'not in store.path.read_bytes()
 assert store.get('team','x')['private']=='synthetic-sensitive-material'
 store.put('session',__import__('hashlib').sha256(token.encode()).hexdigest(),{'expires':0});assert not store.session(token)
def test_idempotent_plan_binding_and_concurrent_provision(store):
 adapter=DeferredAdapter();s=Teams(store,adapter);slots=[{'product':'ghost','callsign':'STONEY','lead':True,'profile':'original'}]
 p=s.create('Test',slots,'1'*32);assert s.create('Test',slots,'1'*32)['id']==p['id'];assert len(store.all('team'))==1
 with pytest.raises(ValueError):s.create('Other',slots,'1'*32)
 member=p['members'][0]['id'];device={'mac':'AA:BB:CC:DD:EE:FF','chip':'esp32s3','profile':'original','product':'ghost','compatible':True}
 s.prepare(p['id'],member,device);s.prepare(p['id'],member,device);assert adapter.calls==1
 adapter.pending.set()
 for _ in range(100):
  if not s.jobs:break
  time.sleep(.02)
 assert store.get('team',p['id'])['members'][0]['status']=='error'
 with pytest.raises(ValueError):s.prepare(p['id'],member,device|{'mac':'11:22:33:44:55:66'})
 assert not any('secret'in m for m in p['members'])
