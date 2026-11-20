import hashlib,io,json,secrets,struct
import pytest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.store import Store
from app.protocol import new_plan
from app.recordings import Recordings

def archive(plan,rows):
 owner=serialization.load_pem_private_key(plan['recovery_private'].encode(),None);key=secrets.token_bytes(32);prefix=b'GDS2'+secrets.token_bytes(16)+hashlib.sha256(bytes.fromhex(plan['recipient'])).digest();header=prefix+owner.public_key().encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=prefix));result=bytearray(header);prev=bytes(16)
 for n,row in enumerate(rows):
  data=b'\0'+json.dumps(row).encode();plain=struct.pack('<H',len(data))+data;p=struct.pack('<II',len(plain),n)+prev;body=AESGCM(key).encrypt(header[4:8]+struct.pack('<Q',n),plain,hashlib.sha256(header).digest()+p);result.extend(p+body);prev=body[-16:]
 return bytes(result)
def test_multiple_recipient_keys_no_unlock_and_tamper(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));s=Store(tmp_path/'db',key);r=Recordings(s)
 for label in ('One','Two'):
  p=new_plan(label,[{'product':'ghost','callsign':'STONEY','lead':True},{'product':'drop','callsign':'gh05t-we4zR'}]);s.put('team',p['id'],p);b=archive(p,[{'type':'config','firmware':'synthetic'},{'type':'end'}]);data={'ciphertext':b.hex(),'sha256':hashlib.sha256(b).hexdigest(),'segment':'a'};result=r.ingest(p,data);assert result['sealed_footer'];assert len(r.read(result['id'])['records'])==2
  corrupt=bytearray(b);corrupt[-1]^=1
  with pytest.raises(Exception):r.ingest(p,data|{'ciphertext':corrupt.hex(),'sha256':hashlib.sha256(corrupt).hexdigest()})
 assert len(r.listing())==2
 p['id']='foreign'
 with pytest.raises(ValueError):r.ingest(p,data)


def test_reused_organizer_recipient_does_not_choose_first_team(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));store=Store(tmp_path/'db',key);records=Recordings(store)
 first=new_plan('Earlier',[{'product':'ghost','callsign':'STONEY','lead':True}]);second=new_plan('Imported later',[{'product':'ghost','callsign':'STONEY','lead':True}])
 second.update(recipient=first['recipient'],recovery_private=first['recovery_private'])
 store.put('team',first['id'],first);store.put('team',second['id'],second)
 blob=archive(second,[{'type':'config','scope':'synthetic-shared-organizer'},{'type':'end'}]);data={'ciphertext':blob.hex(),'sha256':hashlib.sha256(blob).hexdigest(),'segment':'b'}
 result=records.ingest(second,data);assert result['team_id']==second['id']and result['sealed_footer']
 with pytest.raises(ValueError,match='original provenance'):records.ingest(first,data)
 assert records.read(result['id'])['team_id']==second['id']
