"""Real local serial adapter, exact identity checks and bounded operations."""
from pathlib import Path
import fcntl,json,os,secrets,threading,time
from serial.tools import list_ports
from .serial_transport import USB
from .receipts import verify_receipt,verify_owner,verify_binding
from .protocol import digest
from .firmware import running_version
class Native:
 def __init__(self,private,allowlist=None,denylist=()):self.private=Path(private);self.private.mkdir(parents=True,exist_ok=True);self.allowlist=None if allowlist is None else set(allowlist);self.denylist=set(denylist);self.progress={};self.cache={};self.lock=threading.RLock();self.active=set();self.cancels={};self.committed=set();self.labels={};self.identifying=None;self.identify_until=0
 def inventory(self):
  return {p.serial_number.upper():p.device for p in list_ports.comports() if p.serial_number and p.vid in (0x303a,0x2886)}
 def ports(self):
  return {mac:port for mac,port in self.inventory().items() if mac not in self.denylist and (self.allowlist is None or mac in self.allowlist)}
 def unit(self,mac):
  port=self.ports().get(mac)
  if not port:raise ValueError('Device disconnected or access restricted; reconnect it to resume')
  return USB(port,mac)
 def identity(self,u,mac):
  physical=u.exchange('gig identity','GIG IDENTITY ',timeout=3).split()
  if len(physical)!=4 or physical[2].upper()!=mac or physical[3]not in ('esp32s3','esp32c5'):raise ValueError('Physical identity changed')
  return physical[3]
 def phase(self,mac,label,completed=0,total=None):
  with self.lock:self.progress[mac]={'phase':label,'completed':completed,'total':total}
 def discover(self):
  inventory=self.inventory();ports=self.ports();result=[]
  with self.lock:
   # A reconnected device must be identified again, never inherit a stale profile.
   for mac in list(self.cache):
    if mac not in inventory and mac not in self.active:self.cache.pop(mac,None)
   for mac in inventory:
    if mac not in self.labels:self.labels[mac]=len(self.labels)+1
    base={'mac':mac,'chip':None,'profile':'unknown','product':'unknown','compatible':False}
    if mac not in ports:
     result.append(dict(base,connected=True,busy=False,label='Device '+str(self.labels[mac]),discovery='restricted',message='Access restricted by this station. This device has not been opened.'));continue
    cached=self.cache.get(mac)
    retry=cached and (not cached.get('compatible') or not cached.get('firmware_version')) and time.time()-cached['checked_at']>10
    if (not cached or retry) and mac not in self.active:
     try:
      with self.unit(mac)as u:
       chip=self.identity(u,mac);profile='unknown';compatible=False
       try:
        cap=u.exchange('plan capability','PLAN CAPABILITY ',timeout=2).split();profile={1:'original',2:'xl',3:'headless'}[int(cap[4])];compatible=cap[2]=='2'
       except (KeyError,IndexError,ValueError,TimeoutError):pass
       version=None
       if profile!='unknown':
        try:version=running_version(u,profile)
        except (ValueError,TimeoutError,OSError):pass
       self.cache[mac]=dict(base,firmware_version=version,chip=chip,profile=profile,product='drop'if profile=='headless'else'ghost'if profile in ('original','xl')else'unknown',compatible=compatible,checked_at=time.time(),discovery='ready'if compatible else'incompatible',message=''if compatible else'Device setup compatibility could not be verified.')
     except (OSError,ValueError,TimeoutError):
      self.cache[mac]=dict(base,checked_at=time.time(),discovery='unresponsive',message='Waiting for a USB reply. Retrying automatically.')
    result.append(dict(self.cache.get(mac,base),connected=True,busy=mac in self.active,label='Device '+str(self.labels[mac]),progress=self.progress.get(mac)))
  return result
 def identify(self,binding):
  mac=binding['mac']
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   if time.monotonic()<self.identify_until:raise ValueError('Wait for the current identification cue to finish')
   self.active.add(mac)
  try:
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     if self.identity(u,mac)!=binding['chip']:raise ValueError('Physical chip differs')
     number=self.labels.get(mac,1)
     reply=u.exchange('gd identify'if binding['product']=='drop'else'gig identify '+str(number),'IDENTIFY LOCAL ',timeout=3)
     expected='IDENTIFY LOCAL LED 2100'if binding['product']=='drop'else'IDENTIFY LOCAL OLED 3000'
     if reply!=expected:raise ValueError('Device identification cue did not verify')
     with self.lock:self.identifying=mac;self.identify_until=time.monotonic()+3
     return {'label':'Device '+str(number),'cue':'Three slow amber blinks'if binding['product']=='drop'else'Device '+str(number)+' on its screen','duration_ms':2100 if binding['product']=='drop'else 3000,'authentication':False,'radio_actions':0}
  finally:
   with self.lock:self.active.discard(mac)
 def cancel(self,mac):
  with self.lock:
   if mac not in self.active:return {'cancelled':False,'message':'No preparation is active'}
   if mac in self.committed:return {'cancelled':False,'message':'Installation is committed. Verify it, then deliberately clear the device if needed.'}
   event=self.cancels.get(mac)
   if not event:return {'cancelled':False,'message':'This operation does not support cancellation'}
   event.set();return {'cancel_requested':True,'message':'Cancellation requested. The worker will report whether installation was already committed.'}
 def prepare(self,binding,image,plan,member):
  mac=binding['mac'];start=time.monotonic();cancel_event=threading.Event();self.phase(mac,"Checking device")
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac);self.cancels[mac]=cancel_event
  def cancelled():
   if cancel_event.is_set():raise ValueError("Preparation cancelled before commit; device identity was unchanged")
  try:
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     if self.identity(u,mac)!=binding['chip']:raise ValueError('Chip changed')
     cap=u.exchange('plan capability','PLAN CAPABILITY ',timeout=3)
     if cap!='PLAN CAPABILITY 2 PROFILE '+str({'original':1,'xl':2,'headless':3}[binding['profile']]):raise ValueError('Firmware/profile changed')
     handout=plan.get('handout')
     if handout and u.exchange('codebook handout-capability','CODEBOOK HANDOUT ',timeout=3)!='CODEBOOK HANDOUT 2':
      raise ValueError('This Ghost needs dev41 handout support before preparation')
     drop_name=plan.get('drop_name')
     if drop_name and u.exchange('gd handout-capability','GD HANDOUT NAME ',timeout=3)!='GD HANDOUT NAME 1':
      raise ValueError('This Drop needs firmware with persistent handout names')
     if binding['product']=='drop':
      # This exact selected device's old gig cleanup was explicitly reviewed.
      # Quiesce a previously armed/full Drop before staging its new identity.
      self.phase(mac,'Stopping old recording');u.exchange('gd disarm','OK ',timeout=5);quiesce_until=time.monotonic()+12
      while time.monotonic()<quiesce_until:
       old_state=u.exchange('gd status','STATE ',timeout=3)
       if ' ARMED 0 'in old_state and ((' RECORDING 0 'in old_state and old_state.endswith('CONTROL_PENDING 0'))or(' RECORDING 'not in old_state and old_state.startswith('STATE IDLE_UNARMED '))):break
       time.sleep(.1)
      else:raise ValueError('Old Drop recording did not stop; preparation has not committed')
     status=u.exchange('plan status','PLAN ',timeout=3)
     already='phase=2 'in status and('operation='+plan['operation']+' ')in status
     if already:
      with self.lock:self.committed.add(mac)
     journal=self.private/(mac.replace(':','')+'-'+plan['operation']+'.json')
     prior=json.loads(journal.read_text())if journal.exists()else None
     if prior and prior['body_sha256']!=digest(image[:-73]).hex():raise ValueError('Preparation transaction conflicts with previous package')
     if (prior or plan.get('origin')=='offline-lead')and 'phase=0 'in status:raise ValueError('Committed state is missing. Create a fresh team; old keys cannot be reused with reset counters')

     if not already:
      self.phase(mac,'Sending team configuration',0,len(image));cancelled();u.exchange('plan begin '+str(len(image)),'PLAN STAGING',timeout=3)
      for i in range(0,len(image),96):
       cancelled();u.exchange('plan chunk '+str(i)+' '+image[i:i+96].hex(),'PLAN CHUNK ',timeout=3);self.phase(mac,'Sending team configuration',min(i+96,len(image)),len(image))
      with self.lock:
       cancelled();self.committed.add(mac)
      entry={'mac':mac,'operation':plan['operation'],'body_sha256':digest(image[:-73]).hex(),'state':'commit_requested'}
      temporary=journal.with_suffix('.pending')
      with temporary.open('w')as f:json.dump(entry,f);f.flush();os.fsync(f.fileno())
      os.replace(temporary,journal)
      directory=os.open(journal.parent,os.O_RDONLY)
      try:os.fsync(directory)
      finally:os.close(directory)
      self.phase(mac,'Clearing old gig and installing team')
      try:u.exchange('plan commit CONFIRM','PLAN ',timeout=2)
      except (TimeoutError,OSError):pass # reconcile the exact durable transaction; never re-wipe on lost ACK
    last='Waiting for committed configuration'
    while time.monotonic()-start<55:
     try:
      with self.unit(mac)as u:
       self.identity(u,mac)
       status=u.exchange('plan status','PLAN ',timeout=2)
       if 'phase=2 'not in status or('operation='+plan['operation']+' ')not in status:raise ValueError('Preparation still committing')
       self.phase(mac,'Verifying saved team and scanner');nonce=secrets.token_bytes(32)
       parts=u.exchange('setup attest '+nonce.hex(),'SETUP RECEIPT ',timeout=3).split();payload=bytes.fromhex(parts[2]);sig=bytes.fromhex(parts[3]);verify_receipt(plan,member,payload,sig,nonce)
       binding_proof=u.exchange('plan attest '+nonce.hex(),'PLAN PROOF ',timeout=3).split();verify_binding(member,binding,image,bytes.fromhex(binding_proof[2]),bytes.fromhex(binding_proof[3]),nonce)
       owner=u.exchange('recipient attest '+nonce.hex(),'RECIPIENT PROOF ',timeout=3).split();verify_owner(plan,member,bytes.fromhex(owner[2]),bytes.fromhex(owner[3]),nonce)
       health=json.loads(u.exchange('recon status','RECON ',timeout=3)[6:])
       if not health['ready']or health['active']:raise ValueError('Device service not ready/passive')
       if binding['product']=='drop':
        firmware=u.exchange('gd hello','GHOST_DROP ',timeout=3).split()[1]
        state=u.exchange('gd status','STATE ',timeout=3)
        if not state.startswith('STATE IDLE_UNARMED'):raise ValueError('Drop is not disarmed and ready')
        facts=u.exchange('gd health','HEALTH ',timeout=3).split();facts=dict(zip(facts[1::2],facts[2::2]))
        if any(facts.get(k)!='1'for k in ('WIFI_HEALTHY','BLE_HEALTHY'))or facts.get('SCAN_ERROR')!='0':raise ValueError('Drop passive scanner is not healthy')
        service=u.exchange('gd recon','RECON_STORE ',timeout=3).split();service=dict(zip(service[1::2],service[2::2]))
        if service.get('LISTENING')!='1'or int(facts.get('CYCLES',0))<=0:raise ValueError('Drop reader reception is not yet listening')
        storage=u.exchange('gd storage','STORAGE ',timeout=3).split();storage=dict(zip(storage[1::2],storage[2::2]))
        if storage.get('LAYOUT')!='1'or int(storage.get('TOTAL',0))<=0 or int(storage.get('RESERVE',0))<=0:raise ValueError('Drop storage is not ready')
       else:
        scanner=json.loads(u.exchange('status','STATUS ',timeout=3)[7:]);firmware=scanner['firmware']
        if not scanner.get('wifi_healthy')or not scanner.get('ble_healthy')or scanner.get('scan_error')or not scanner.get('radio_progress_ms')or scanner.get('uptime_ms',0)-scanner['radio_progress_ms']>12000:raise ValueError('Ghost passive scanner is not healthy')
       handout_proof={}
       if handout:
        from .handout import apply_handout
        self.phase(mac,'Saving and verifying team handout')
        handout_proof=apply_handout(u,handout,member,plan['certificate'],nonce)
       if drop_name and u.exchange('gd handout-name '+drop_name,'GD HANDOUT NAME ',timeout=3)!='GD HANDOUT NAME '+drop_name:
        raise ValueError('Saved Drop callsign differs')
       self.phase(mac,'Ready',1,1)
       return {**({'drop_name':drop_name} if drop_name else {}),**({'handout':handout_proof} if handout_proof else {}),'nonce':nonce.hex(),'payload':payload.hex(),'signature':sig.hex(),'owner_signature':owner[3],'binding_payload':binding_proof[2],'binding_signature':binding_proof[3],'duration_seconds':round(time.monotonic()-start,3),'firmware_version':firmware,'protocol_version':2,'verified_at':time.time(),'method':'committed-device-signature;creator-escrowed','physical':binding}
     except (OSError,ValueError,TimeoutError)as e:last=str(e);time.sleep(.15)
    raise TimeoutError(last)
  finally:
   with self.lock:self.active.discard(mac);self.cancels.pop(mac,None);self.committed.discard(mac);self.progress.pop(mac,None)

 def unassign(self,binding,operation):
  mac=binding['mac'];start=time.monotonic()
  if len(operation)!=32 or any(c not in '0123456789abcdef'for c in operation):raise ValueError('Invalid operation')
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     if self.identity(u,mac)!=binding['chip']:raise ValueError('Physical chip differs before cleanup')
     if binding['product']=='drop':
      state=u.exchange('gd status','STATE ',timeout=3)
      if state.startswith('STATE RECORDING'):u.exchange('gd disarm','OK',timeout=5)
     current=u.exchange('gig reissue-state '+operation,'GIG REISSUE ',timeout=3)
     if current!='GIG REISSUE COMPLETE':
      try:u.exchange('gig reissue '+operation+' CONFIRM','GIG REISSUE ',timeout=2)
      except (TimeoutError,OSError):pass
    while time.monotonic()-start<40:
     try:
      with self.unit(mac)as u:
       self.identity(u,mac)
       if u.exchange('gig reissue-state '+operation,'GIG REISSUE ',timeout=2)!='GIG REISSUE COMPLETE':raise ValueError('Cleanup pending')
       u.identity_namespace='buddy'if binding['product']=='ghost'else'recon';identity=u.identity()
       if identity.get('certificate'):raise ValueError('Team credentials still installed')
       health=json.loads(u.exchange('recon status','RECON ',timeout=3)[6:])
       if not health['ready']or health['active']or health['peers']:raise ValueError('Service not healthy and unassigned')
       self.cache.pop(mac,None)
       return {'unassigned':True,'mac':mac,'operation':operation,'new_public_fingerprint':digest(identity['public_key']).hex(),'duration_seconds':round(time.monotonic()-start,3)}
     except (ValueError,TimeoutError,OSError):time.sleep(.15)
    raise TimeoutError('Device cleanup did not verify; reconnect to resume')
  finally:
   with self.lock:self.active.discard(mac)
 def briefings(self,binding):
  mac=binding['mac']
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   if binding['product']!='ghost':raise ValueError('Import briefings from a Ghost')
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     if self.identity(u,mac)!=binding['chip']:raise ValueError('Physical chip changed')
     reports=[]
     for page in range(12):
      try:line=u.exchange('recon export '+str(page),'RECON REPORT',timeout=8)
      except ValueError as e:
       if str(e)=='ERR recon export empty':continue
       raise
      if line=='RECON REPORT_END':break
      reports.append(json.loads(line[len('RECON REPORT '):]))
     return reports
  finally:
   with self.lock:self.active.discard(mac)
 def recordings(self,binding):
  import re
  mac=binding['mac']
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   if binding['product']!='drop':raise ValueError('Connect a Drop for supporting recordings')
   with self.unit(mac)as u:
    self.identity(u,mac);state=u.exchange('gd status','STATE ',timeout=3)
    if state.startswith('STATE RECORDING'):raise ValueError('Disarm this Drop before inspecting its closed recordings')
    result=[]
    for i in range(100000):
     line=u.exchange('gd sessions '+str(i),timeout=15)
     if line=='SESSIONS_END':return result
     m=re.fullmatch(r'/?gd-([0-9a-fA-F]{1,16})\.bin BYTES (\d+) VALID (\d+)',line)
     if not m:raise ValueError('Unexpected recording inventory reply')
     result.append({'id':m[1],'bytes':int(m[2]),'valid':int(m[3])})
    raise ValueError('Recording inventory exceeds the firmware cursor range')
  finally:
   with self.lock:self.active.discard(mac)
 def recording(self,binding,segment):
  import re
  if not isinstance(segment,str)or not re.fullmatch('[0-9a-fA-F]{1,16}',segment):raise ValueError('Invalid recording identifier')
  mac=binding['mac']
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   if binding['product']!='drop':raise ValueError('Choose a Drop')
   with self.unit(mac)as u:
    self.identity(u,mac);state=u.exchange('gd status','STATE ',timeout=3)
    if state.startswith('STATE RECORDING'):raise ValueError('Disarm the Drop to read a closed recording')
    content=bytearray();began=time.monotonic()
    while len(content)<=0x660000 and time.monotonic()-began<240:
     parts=u.exchange('gd read '+segment+' '+str(len(content)),'DATA ',timeout=5).split()
     if len(parts)not in (2,3)or parts[1]!=str(len(content)):raise ValueError('Recording read offset changed')
     block=bytes.fromhex(parts[2])if len(parts)==3 else b''
     if len(block)>192:raise ValueError('Recording chunk too large')
     if not block:break
     if not content and block[:4]not in (b'GDS2',b'GDS3'):raise ValueError('Only encrypted recordings are supported')
     content.extend(block)
    else:raise ValueError('Recording exceeds time/size bound')
    fingerprint=digest(content).hex()
    if len(content)<436 or u.exchange('gd digest '+segment,'SHA256 ',timeout=30)!='SHA256 '+str(len(content))+' '+fingerprint:raise ValueError('Recording integrity changed during USB transfer')
    return {'ciphertext':content.hex(),'sha256':fingerprint,'segment':segment,'bytes':len(content)}
  finally:
   with self.lock:self.active.discard(mac)
 def offline(self,binding):
  from .protocol import verify
  import struct
  mac=binding['mac']
  if binding['product']!='ghost':raise ValueError('Connect the Ghost that created the offline team')
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     if self.identity(u,mac)!=binding['chip']:raise ValueError('Physical chip differs')
     u.identity_namespace='buddy';identity=u.identity();nonce=secrets.token_bytes(32);member,sig=u.attest(nonce.hex())
     if member!=identity['member_id']:raise ValueError('Lead identity changed')
     payload=b'WEAZL-USB-ID-V2\0'+nonce+struct.pack('<Q',int(member))+identity['public_key']+bytes(7)
     assert len(payload)==128
     verify(identity['public_key'],bytes.fromhex(sig),payload)
     u.exchange('planned close CONFIRM','PLANNED ENROLLMENT CLOSED ',timeout=5)
     blob=u.exchange('planned export','PLANNED PRIVATE ',timeout=15)[16:]
     assignments=json.loads(u.exchange('planned assignments','PLANNED ASSIGNMENTS ',timeout=10)[20:])
     owner=u.exchange('recipient attest '+nonce.hex(),'RECIPIENT PROOF ').split()
     physical=u.exchange('plan attest '+nonce.hex(),'PLAN PROOF ').split();receipt=u.exchange('setup attest '+nonce.hex(),'SETUP RECEIPT ').split()
     return {'blob':blob,'assignments':assignments,'member':member,'public':identity['public_key'].hex(),'certificate':identity['certificate'].hex()if identity['certificate']else None,'nonce':nonce.hex(),'binding':binding,'physical':physical[2:],'receipt':receipt[2:],'owner':owner[2:]}
  finally:
   with self.lock:self.active.discard(mac)
 def custody(self,binding,digest,nonce,signature):
  mac=binding['mac']
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     self.identity(u,mac)
     return {'acknowledged':u.exchange('planned custody-ack '+digest+' '+nonce+' '+signature,'PLANNED CUSTODY ',timeout=10)=='PLANNED CUSTODY DURABLE APP / PRIVATE ESCROW REMOVED'}
  finally:
   with self.lock:self.active.discard(mac)
 def decisions(self,binding):
  mac=binding['mac']
  if binding['product']!='ghost':raise ValueError('Connect a Ghost for field decisions')
  with self.lock:
   if mac in self.active:raise ValueError('Device is busy')
   self.active.add(mac)
  try:
   with(self.private/(mac.replace(':','')+'.lock')).open('a')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.unit(mac)as u:
     self.identity(u,mac);result=[]
     for index in range(64):
      try:line=u.exchange('gig decision '+str(index),'GIG DECISION ',timeout=5)
      except ValueError as e:
       if str(e)=='ERR decision slot unavailable':break
       raise
      result.append(json.loads(line[len('GIG DECISION '):]))
     return result
  finally:
   with self.lock:self.active.discard(mac)
