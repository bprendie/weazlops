import struct,pytest,secrets
from app.protocol import *
from app.receipts import verify_receipt,verify_binding

def test_fresh_receipt_rejects_replay_and_wrong_physical_binding():
 p=new_plan('Test',[{'product':'ghost','callsign':'STONEY','lead':True}]);m=p['members'][0];nonce=secrets.token_bytes(32);key=load(bytes.fromhex(m['secret']))
 data=b'WZLTI001'+bytes.fromhex(p['id'])+struct.pack('<II',1,1)+digest(bytes.fromhex(p['roster'])[:638])+struct.pack('<I',1)+CONFIG+bytes.fromhex(p['operation'])+nonce+struct.pack('<Q',int(m['id']))+b'\1'
 sig=sign(key,b'WZL TEAM INSTALLED V1\0'+data);verify_receipt(p,m,data,sig,nonce)
 with pytest.raises(ValueError):verify_receipt(p,m,data,sig,secrets.token_bytes(32))
 physical={'mac':'02:00:00:00:00:01','chip':'esp32s3','profile':'original'};image=package(p,m,**physical)
 proof=b'WZLPP002'+digest(image[:-73])+nonce+bytes.fromhex(physical['mac'].replace(':',''))+b'\1\1'+struct.pack('<Q',int(m['id']))+b'\2';sig=sign(key,b'WZL ONE VISIT INSTALLED V2\0'+proof)
 verify_binding(m,physical,image,proof,sig,nonce)
 with pytest.raises(ValueError):verify_binding(m,physical|{'chip':'esp32c5'},image,proof,sig,nonce)
