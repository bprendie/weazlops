"""Transport-neutral team lifecycle. USB is one adapter, never a trust authority."""
import threading,time
from .protocol import new_plan,package,public_plan,CALLSIGNS
class Teams:
 def __init__(self,store,adapter):
  self.store=store;self.adapter=adapter;self.lock=threading.RLock();self.jobs=set()
  # Persisted pending work is reconciled only after a fresh authenticated Resume.
  # Restart cannot execute a stale destructive approval on its own.
  for plan in store.all('team'):
   dirty=False
   for m in plan['members']:
    if m['status']in ('preparing','verifying'):m['status']='error';m['error']='Preparation interrupted. Reconnect the same device and resume.';dirty=True
   if dirty:store.put('team',plan['id'],plan)
 def create(self,name,slots,request_id,phrases=None):
  if len(request_id)!=32 or any(c not in '0123456789abcdef'for c in request_id):raise ValueError('Invalid request ID')
  with self.lock:
   prior=self.store.get('request',request_id)
   if prior:
    plan=self.store.get('team',prior['team'])
    if plan.get('phrases')!=phrases or plan['name']!=name or [{k:m.get(k)for k in ('product','callsign','lead','profile')}for m in plan['members']]!=[{k:m.get(k)for k in ('product','callsign','lead','profile')}for m in slots]:raise ValueError('Request ID reused for different plan')
    return public_plan(plan)
   plan=new_plan(name,slots,phrases);plan['created']=time.time();self.store.put_many([('team',plan['id'],plan),('request',request_id,{'team':plan['id']})]);return public_plan(plan)
 def prepare(self,team_id,member_id,device):
  with self.lock:
   plan=self.store.get('team',team_id)
   if not plan or plan['state']in ('archived','deleted'):raise ValueError('Team unavailable')
   member=next((m for m in plan['members']if m['id']==member_id),None)
   if not member:raise ValueError('Member missing')
   if member['status']=='ready':return public_plan(plan)
   if member['status']=='lost_state':raise ValueError('Previous assignment was erased. Create a new team with fresh credentials; do not reinstall old keys.')
   if member['product']!=device['product']or(member.get('profile','any')!='any'and member.get('profile')!=device['profile']):raise ValueError('Choose matching device type and display')
   if not device.get('compatible'):raise ValueError('Device needs compatible firmware')
   binding={k:device[k]for k in ('mac','chip','profile','product')}
   if member['binding']and member['binding']!=binding:raise ValueError('This member is already bound; resume with that device')
   for p in self.store.all('team'):
    for m in p['members']:
     if p['id']==team_id and m['id']!=member_id and m.get('binding',{} )and m['binding']['mac']==binding['mac']:raise ValueError('Device already fills another slot')
     if m.get('binding')and m['binding']['mac']==binding['mac']and m['status']in ('preparing','verifying')and(p['id'],m['id'])!=(team_id,member_id):raise ValueError('Device has another pending preparation')
   key=(team_id,member_id)
   if key in self.jobs:return public_plan(plan)
   def mark(p):
    m=next(m for m in p['members']if m['id']==member_id);m['binding']=binding;m['status']='preparing';m.pop('error',None)
   self.store.modify('team',team_id,mark);self.jobs.add(key)
   threading.Thread(target=self._run,args=(team_id,member_id,binding),daemon=True).start()
   return public_plan(self.store.get('team',team_id))
 def _run(self,team_id,member_id,binding):
  try:
   plan=self.store.get('team',team_id);member=next(m for m in plan['members']if m['id']==member_id)
   image=package(plan,member,binding['mac'],binding['chip'],binding['profile'])
   prepared_plan=dict(plan)
   if plan.get('origin')=='offline-lead'and not member.get('receipt')and member.get('status')!='error':prepared_plan['origin']='offline-waiting'
   from .handout import uses_handout,publication
   if binding['product']=='ghost' and uses_handout(plan):
    prepared_plan['handout']=publication(plan,member)
   if binding['product']=='drop' and member['callsign'] not in CALLSIGNS:
    prepared_plan['drop_name']=member['callsign']
   proof=self.adapter.prepare(binding,image,prepared_plan,member)
   if 'handout' in prepared_plan:
    from .handout import verify_handout
    verify_handout(member,plan['certificate'],prepared_plan['handout']['manifest'],bytes.fromhex(proof['nonce']),proof.get('handout',{}))
   if 'drop_name' in prepared_plan and proof.get('drop_name')!=prepared_plan['drop_name']:
    raise ValueError('Drop did not confirm its saved callsign')
   def ready(p):
    m=next(m for m in p['members']if m['id']==member_id);m['status']='ready';m['verified_at']=time.time();m['receipt']=proof
    if all(m['status']=='ready'for m in p['members']):p['state']='ready'
   with self.store.lock:
    current=self.store.get('team',team_id);ready(current)
    self.store.commit_assignments(current,{binding['mac']})

  except Exception as e:
   def fail(p):
    m=next(m for m in p['members']if m['id']==member_id);m['status']='error';m['error']=str(e)[:240]
   self.store.modify('team',team_id,fail)
  finally:
   with self.lock:self.jobs.discard((team_id,member_id))
