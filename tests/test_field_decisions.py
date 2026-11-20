import struct,secrets,pytest
from app.protocol import new_plan,load,sign
from app.intelligence import Intelligence
from app.store import Store

def test_exact_signed_local_decision_stays_separate_from_drop_finding(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));store=Store(tmp_path/'db',key);intel=Intelligence(store);plan=new_plan('Return',[{'product':'ghost','callsign':'STONEY','lead':True}]);m=plan['members'][0]
 body=b'WZLD001\0'+bytes.fromhex(plan['id'])+struct.pack('<QII',123,1,15000)+b'\0\1'+bytes.fromhex('020304050607')+struct.pack('<I',3)+b'\2'+bytes(11)
 assert len(body)==64
 report={'schema':1,'actor_id':m['id'],'actor_public_key_hex':m['public'],'record_hex':body.hex(),'signature_hex':sign(load(bytes.fromhex(m['secret'])),b'WZL-LOCAL-DECISION-V1\0'+body).hex()}
 result=intel.ingest_decision(plan,report);assert result['action']=='watch'and result['observation_revision']==3
 assert intel.ingest_decision(plan,report)==result and len(store.all('field_decision'))==1 and not store.all('finding')
 with pytest.raises(ValueError):intel.ingest_decision(plan,dict(report,actor_id='123'))
 with pytest.raises(Exception):intel.ingest_decision(plan,dict(report,record_hex=(body[:-12]+b'\1'+body[-11:]).hex()))
 other=new_plan('Other',[{'product':'ghost','callsign':'STONEY','lead':True}])
 with pytest.raises(ValueError):intel.ingest_decision(other,report)
