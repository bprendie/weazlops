"""Same-authority custody transfer: encrypted durable commit precedes signed ACK."""
import secrets,time
from .protocol import import_offline,package,public_plan,sign,load
from .receipts import verify_binding,verify_receipt,verify_owner
class Offline:
 def __init__(self,store,worker):self.store=store;self.worker=worker
 def preview(self,binding):
  received=self.worker.offline(binding)
  plan=import_offline(bytes.fromhex(received['blob']),self.store.all('team'))
  lead=next(m for m in plan['members']if m['lead'])
  if received['member']!=lead['id']or received['public']!=lead['public']or received['certificate']!=plan['certificate']:raise ValueError('Connected creator differs from exported authority')
  image=package(plan,lead,binding['mac'],binding['chip'],binding['profile']);nonce=bytes.fromhex(received['nonce'])
  verify_binding(lead,binding,image,*(bytes.fromhex(v)for v in received['physical']),nonce)
  verify_receipt(plan,lead,*(bytes.fromhex(v)for v in received['receipt']),nonce)
  verify_owner(plan,lead,*(bytes.fromhex(v)for v in received['owner']),nonce)
  for row in received['assignments']:
   member=next((m for m in plan['members']if m['id']==row['member']),None)
   if not member:raise ValueError('Assignment is not in signed directory')
   if member['lead']:member.update(binding=binding,status='ready',receipt={'method':'fresh-usb-offline-creator','physical':received['physical'],'configuration':received['receipt']});continue
   if row['phase'] not in (0,1,2):raise ValueError('Invalid historical assignment phase')
   if row['phase']==0:continue
   rawmac=row['mac'].upper();physical={**binding,'mac':':'.join(rawmac[i:i+2]for i in range(0,12,2)),'chip':{1:'esp32s3',2:'esp32c5'}[row['chip']],'profile':{1:'original',2:'xl',3:'headless'}[row['profile']],'product':member['product']}
   if len(rawmac)!=12:raise ValueError('Invalid physical assignment')
   member['binding']=physical
   if row['phase']==1:member['status']='error';member['error']='Offline preparation interrupted; reconnect the same device to verify or resume';continue
   proof=bytes.fromhex(row.get('proof',''))
   if len(proof)!=392:raise ValueError('Offline Ready has no stored installed receipts')
   nonce=proof[40:72];image=package(plan,member,physical['mac'],physical['chip'],physical['profile'])
   verify_binding(member,physical,image,proof[:89],proof[90:90+proof[89]],nonce)
   verify_receipt(plan,member,proof[162:319],proof[320:320+proof[319]],nonce)
   member.update(status='ready',receipt={'method':'historical-offline-signed-installation;not-current-presence','proof':proof.hex()})
  bindings=[m['binding']['mac']for m in plan['members']if m.get('binding')]
  if len(bindings)!=len(set(bindings)):raise ValueError('Device fills multiple offline slots')
  prior=self.store.get('team',plan['id'])
  if prior and(prior['root_public']!=plan['root_public']or prior['roster']!=plan['roster']or prior['recipient']!=plan['recipient']):raise ValueError('Existing team authority conflicts; nothing replaced')
  token=secrets.token_hex(16);self.store.put('offline-preview',token,{'plan':plan,'binding':binding,'captured_at':time.time(),'expires':time.time()+300})
  return {'preview':token,'team':public_plan(plan),'custody':'Offline lead → this application','authority_changed':False,'recording_unlock':'Normal login after import','removes_temporary_lead_keys':True}
 def commit(self,token):
  preview=self.store.get('offline-preview',token)
  if not preview or preview['expires']<time.time():raise ValueError('Preview expired; reconnect the creator')
  plan=preview['plan'];current=self.store.get('device',preview['binding']['mac'])
  if current and current['team']!=plan['id']and current.get('verified_at',0)>preview.get('captured_at',preview['expires']-300):raise ValueError('Creator was reissued after inspection; inspect its current team again')
  prior=self.store.get('team',plan['id'])
  if prior and(prior.get('escrow_digest')!=plan['escrow_digest']):raise ValueError('Team import conflicts; nothing overwritten')
  if prior:plan=prior
  else:
   plan['state']='ready'if all(m['status']=='ready'for m in plan['members'])else'preparing';plan['created']=time.time();plan['imported_at']=time.time();plan['custody']='app-durable;lead-ack-pending'
   # SQLite FULL synchronous commit; key/certificate/roster/recovery persist together.
   self.store.commit_assignments(plan,{preview['binding']['mac']})
  committed=self.store.get('team',plan['id'])
  if committed!=plan:raise ValueError('Durable custody readback differs; lead retains its key')
  nonce=secrets.token_bytes(32);payload=bytes.fromhex(plan['escrow_digest'])+nonce+bytes.fromhex(plan['id']);sig=sign(load(bytes.fromhex(plan['root_secret'])),b'WZL CUSTODY COMMIT V1\0'+payload)
  try:ack=self.worker.custody(preview['binding'],plan['escrow_digest'],nonce.hex(),sig.hex())
  except (ValueError,OSError,TimeoutError):ack={'acknowledged':False}
  if ack['acknowledged']:plan['custody']='app';self.store.put('team',plan['id'],plan)
  return {'team':public_plan(plan),'durable':True,'lead_private_cleanup':bool(ack['acknowledged']),'message':'Imported as the same team. Normal login opens its recordings.'if ack['acknowledged']else'Imported durably. Lead cleanup is pending; retry import confirmation with the same creator.'}
