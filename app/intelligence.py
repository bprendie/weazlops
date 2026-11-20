"""Evidence-based continuity, exact revision review, no raw-record prerequisite."""
import hashlib,json,time
from cryptography.exceptions import InvalidSignature
from .evidence.briefings import verify_report

def team_context(plan):
 cert=bytes.fromhex(plan['certificate']);return {'id':plan['id'],'certificate_hex':plan['certificate'],'root_public_key_hex':plan['root_public'],'roster_epoch':int.from_bytes(cert[24:32],'little'),'group_id':str(int.from_bytes(cert[8:16],'little'))}
class Intelligence:
 def __init__(self,store):self.store=store
 def ingest(self,plan,report):
  with self.store.lock:return self._ingest(plan,report)
 def _ingest(self,plan,report):
  verified=verify_report(report,team_context(plan));receipt=verified['capsule_sha256']
  prior=self.store.get('briefing',receipt)
  if prior:
   if prior['signed_payload_sha256']!=verified['signed_payload_sha256']:raise ValueError('Conflicting signed report')
   return prior
  verified.update(team_id=plan['id'],imported_at=time.time(),authority_origin=plan['origin'],creator_escrowed=True)
  changes=[('briefing',receipt,verified)]
  for card in verified['cards']:
   key=plan['id']+':'+verified['source_id']+':'+card['event_id'];old=self.store.get('finding',key);revision=str(card['revision']);version_key=key+':'+revision
   same=self.store.get('finding_revision',version_key)
   if same and same['card_sha256']!=card['card_sha256']:raise ValueError('Conflicting exact finding revision')
   changes.append(('finding_revision',version_key,card))
   if old and old['revision']>card['revision']:continue
   if old and old['revision']==card['revision']:continue
   value=dict(card,id=key,team_id=plan['id'],team_name=plan['name'],source_id=verified['source_id'],reader_id=verified['reader_id'],source_authentication='VERIFIED_SOURCE_SIGNATURE',creator_escrowed=True,imported_at=time.time(),disposition='unreviewed',operator_note='',version=revision)
   if old:
    value.update(reopened=True,previous_disposition=old['disposition'])
    baseline=old.get('review_baseline')
    if old['disposition'] in ('expected','watch','reviewed'):
     baseline={k:old[k] for k in ('revision','max_rssi','observations','disposition','rule','radio')}
    if baseline:value['review_baseline']=baseline
   changes.append(('finding',key,value))
  self.store.put_many(changes);return verified
 def review(self,id,revision,disposition,note,actor):
  if disposition not in ('reviewed','expected','watch','unreviewed')or not isinstance(note,str)or len(note)>2000:raise ValueError('Invalid review')
  def apply(current):
   if current['revision']!=revision:raise ValueError('Evidence changed; review the current revision')
   current.update(disposition=disposition,operator_note=note,reviewed_by=actor,reviewed_at=time.time(),reopened=False)
  return self.store.modify('finding',id,apply)
 def ingest_decision(self,plan,report):
  from .protocol import verify
  actor=report.get('actor_id');member=next((m for m in plan['members']if m['id']==actor and m['product']=='ghost'),None)
  if not member or report.get('actor_public_key_hex')!=member['public']:raise ValueError('Decision actor is not a Ghost in this team')
  try:
   body=bytes.fromhex(report['record_hex']);sig=bytes.fromhex(report['signature_hex'])
   if len(body)!=64 or body[:8]!=b'WZLD001\0'or body[8:24]!=bytes.fromhex(plan['id'])or body[40]>1 or body[41]>3 or body[52]>3 or any(body[53:])or not int.from_bytes(body[24:32],'little')or not int.from_bytes(body[32:36],'little')or not int.from_bytes(body[48:52],'little'):raise ValueError('Malformed or wrong-team field decision')
   verify(bytes.fromhex(member['public']),sig,b'WZL-LOCAL-DECISION-V1\0'+body)
  except (KeyError,TypeError,ValueError,InvalidSignature):raise ValueError('Invalid exact field decision')from None
  key=hashlib.sha256(bytes.fromhex(plan['id'])+actor.encode()+body).hexdigest();value={'id':key,'team_id':plan['id'],'team_name':plan['name'],'actor_id':actor,'callsign':member['callsign'],'action':('reviewed','expected','watch','reopen')[body[52]],'identifier':str(body[40])+':'+str(body[41])+':'+body[42:48].hex(),'boot_id':body[24:32].hex(),'sequence':int.from_bytes(body[32:36],'little'),'source_offset_ms':int.from_bytes(body[36:40],'little'),'observation_revision':int.from_bytes(body[48:52],'little'),'scope':'EXACT_DEVICE_LOCAL_OBSERVATION_REVISION','authentication':'VERIFIED_CREATOR_ESCROWED_DEVICE_SIGNATURE','imported_at':time.time(),'original':report}
  prior=self.store.get('field_decision',key)
  if prior:return prior
  self.store.put('field_decision',key,value);return value
