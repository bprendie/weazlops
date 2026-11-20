"""Ordinary authorized-login decryption with per-record recipient resolution."""
import hashlib,io,time
from cryptography.hazmat.primitives import serialization
from .evidence.storage_v2 import read_records
class Recordings:
 def __init__(self,store):self.store=store
 def ingest(self,plan,data):
  cipher=bytes.fromhex(data['ciphertext'])
  if len(cipher)<436 or len(cipher)>0x660000 or cipher[:4]not in (b'GDS2',b'GDS3') or hashlib.sha256(cipher).hexdigest()!=data['sha256']:raise ValueError('Encrypted recording integrity mismatch')
  recipient=cipher[20:52].hex();owner=self.store.get('team',plan['id'])
  if not owner or owner['recipient']!=plan['recipient']:raise ValueError('Selected team custody is unavailable')
  if hashlib.sha256(bytes.fromhex(owner['recipient'])).hexdigest()!=recipient:raise ValueError('Recording belongs to a different organizer or team; select its matching team')
  prior=self.store.get('recording',data['sha256'])
  if prior and prior['team_id']!=plan['id']:raise ValueError('This recording is already retained under another team; its original provenance is preserved')
  key=serialization.load_pem_private_key(owner['recovery_private'].encode(),password=None)
  rows=[];closed=False
  for row in read_records(io.BytesIO(cipher),key):
   if closed:raise ValueError('Data follows authenticated recording footer')
   if len(rows)>=200000:raise ValueError('Recording record count exceeds bound')
   rows.append(row);closed=row.get('type')=='end'
  if not rows:raise ValueError('No authenticated recording content')
  result={'id':data['sha256'],'team_id':plan['id'],'segment':data['segment'],'bytes':len(cipher),'recipient':recipient,'imported_at':time.time(),'integrity':'AUTHENTICATED_CONTENT','source_authentication':'NOT_ESTABLISHED_BY_RECORDING_ENCRYPTION','sealed_footer':closed,'records':rows,'ciphertext':data['ciphertext']}
  self.store.put('recording',result['id'],result);return {k:v for k,v in result.items()if k not in ('records','ciphertext')}
 def listing(self):return [{k:v for k,v in r.items()if k not in ('records','ciphertext')}for r in self.store.all('recording')]
 def read(self,id):
  r=self.store.get('recording',id)
  if not r:raise ValueError('Recording unavailable')
  return {k:v for k,v in r.items()if k!='ciphertext'}
