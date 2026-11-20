from pathlib import Path
import hashlib,json,os,secrets,time,threading
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from .store import Store
from .service import Teams
from .protocol import CALLSIGNS,public_plan
from .adapter import Adapter
from .firmware_upload import FirmwareUpload, MAX_RELEASE_BYTES
from starlette.concurrency import run_in_threadpool
from .intelligence import Intelligence
from .recordings import Recordings
from .offline import Offline
ROOT=Path(__file__).resolve().parents[1]
def create_app(data,key,worker,bootstrap=None):
 store=Store(data,key)
 if bootstrap and not store.accounts():
  obj=json.loads(Path(bootstrap).read_text());store.create_account(obj['username'],obj['password'],'admin',bootstrap=True)
 build_info={'version':os.environ.get('WZL_BUILD','development'),'source_sha256':None}
 if os.environ.get('WZL_ENFORCE_BUILD')=='1':
  build_info=json.loads((ROOT/'app/build_info.json').read_text())
  for path,expected in build_info['files'].items():
   if not (ROOT/path).is_file()or hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise ValueError('Deployed source differs from stamped build')
 service=Teams(store,worker);intel=Intelligence(store);records=Recordings(store);offline=Offline(store,worker);app=FastAPI(docs_url=None,redoc_url=None);app.state.store=store;app.state.teams=service;attempts={};rate_lock=threading.RLock()
 firmware_upload=FirmwareUpload()
 @app.middleware('http')
 async def scope(request,call_next):
  uploading=request.method=='POST' and request.url.path=='/api/firmware/import'
  limit=MAX_RELEASE_BYTES if uploading else 65536
  if int(request.headers.get('content-length','0'))>limit:
   return JSONResponse({'detail':'Choose a release ZIP up to 64 MB.' if uploading else 'Request too large'},413)
  origin=request.headers.get('origin')
  if request.method not in ('GET','HEAD','OPTIONS')and origin and origin!=str(request.base_url).rstrip('/'):return JSONResponse({'detail':'Origin mismatch'},403)
  if request.url.path.startswith('/api/')and request.url.path not in ('/api/login','/api/health'):
   session=store.session(request.cookies.get('wzl_next_session'))
   if not session:return JSONResponse({'detail':'Sign in to continue'},401)
   if request.method not in ('GET','HEAD')and request.headers.get('x-csrf-token')!=session['csrf']:return JSONResponse({'detail':'Session confirmation missing; reload'},403)
   request.state.session=session
  response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'";return response
 @app.exception_handler(ValueError)
 async def invalid(request,exc):return JSONResponse({'detail':str(exc)},400)
 @app.get('/api/health')
 def health():return {'build':build_info['version'],'source_sha256':build_info['source_sha256'],'transport':'native-usb','browser_usb':'deferred'}
 @app.post('/api/login')
 def login(body:dict,request:Request):
  host=request.client.host;now=time.monotonic()
  with rate_lock:
   hits=attempts.setdefault(host,[]);hits[:]=[t for t in hits if now-t<60]
   if len(hits)>=10:raise HTTPException(429,'Wait one minute before trying again')
   hits.append(now)
  token=store.login(body.get('username'),body.get('password'))
  if not token:raise HTTPException(401,'Username or password incorrect')
  res=JSONResponse({'csrf':store.session(token)['csrf']});res.set_cookie('wzl_next_session',token,httponly=True,samesite='strict',max_age=28800);return res
 @app.get('/api/session')
 def session(request:Request):return {'role':account_role(request),'username':request.state.session['username'],'csrf':request.state.session['csrf'],'callsigns':CALLSIGNS,'handout_draft':request.state.session.get('handout_draft')}
 def account_role(request):
  account=store.get('account',request.state.session['username'])
  if not account:raise HTTPException(401,'Sign in to continue')
  return account.get('role','operator')
 def require_admin(request):
  if account_role(request)!='admin':raise HTTPException(403,'An administrator manages user accounts.')
 @app.get('/api/settings/users')
 def users(request:Request):
  require_admin(request)
  return store.accounts()
 @app.post('/api/settings/users',status_code=201)
 def add_user(body:dict,request:Request):
  require_admin(request)
  try:return store.create_account(body.get('username'),body.get('password'),body.get('role','operator'))
  except FileExistsError as exc:raise HTTPException(409,str(exc)) from None
 @app.post('/api/session/handout')
 def save_handout(body:dict,request:Request):
  from .handout import validate_phrases
  phrases=body.get('phrases');validate_phrases(phrases)
  draft={'id':secrets.token_hex(16),'phrases':phrases} if phrases else None
  token=request.cookies['wzl_next_session']
  store.modify('session',hashlib.sha256(token.encode()).hexdigest(),lambda s:s.update(handout_draft=draft))
  return {'id':draft['id'] if draft else None}
 @app.post('/api/logout')
 def logout(request:Request):
  token=request.cookies.get('wzl_next_session');store.put('session',hashlib.sha256(token.encode()).hexdigest(),{'expires':0});r=JSONResponse({'ok':True});r.delete_cookie('wzl_next_session');return r
 @app.get('/api/devices')
 def devices():return worker.discover()
 @app.get('/api/firmware')
 def firmware_catalog():return worker.firmware_catalog()
 @app.post('/api/firmware/import')
 async def import_firmware(request:Request):
  if firmware_upload.lock.locked():raise HTTPException(409,'An import is already in progress.')
  async with firmware_upload.lock:
   bundle=await firmware_upload.read(request)
   return await run_in_threadpool(worker.import_firmware,bundle)
 @app.post('/api/devices/flash')
 def flash_device(body:dict):
  if body.get('confirm') != 'FLASH SELECTED RELEASE':raise ValueError('Review and confirm this firmware update.')
  device=next((d for d in worker.discover() if d['mac']==body.get('device')),None)
  if not device or device.get('busy') or not device.get('compatible'):raise ValueError('Selected device is unavailable.')
  return worker.flash(device,body.get('release'))
 @app.post('/api/devices/identify')
 def identify_device(body:dict):
  found=next((d for d in worker.discover()if d['mac']==body['device']),None)
  if not found:raise ValueError('Device unavailable')
  return worker.identify(found)
 @app.post('/api/devices/unassign')
 def unassign(body:dict):
  if body.get('confirm')!='CLEAR LOCAL TEAM AND RECORDINGS':raise ValueError('Confirm the local cleanup')
  found=next((d for d in worker.discover()if d['mac']==body['device']),None)
  if not found:raise ValueError('Device unavailable')
  result=worker.unassign(found,body['operation'])
  for p in store.all('team'):
   changed=False
   for m in p['members']:
    if m.get('binding')and m['binding']['mac']==found['mac']:m['status']='released';m['released_at']=time.time();changed=True
   if changed:store.put('team',p['id'],p)
  return result
 @app.get('/api/teams')
 def teams():return [public_plan(p)for p in store.all('team')if p['state']!='deleted']
 @app.post('/api/teams')
 def team(body:dict):return service.create(body['name'],body['members'],body['request_id'],body.get('phrases'))
 @app.post('/api/teams/{id}/journey')
 def journey(id,body:dict):
  # Operator observations, never inferred radio or physical acceptance.
  checks=body.get('checks',{})
  if not isinstance(checks,dict)or any(k not in ('names','armed','drop','buddy')or type(v)is not bool for k,v in checks.items()):raise ValueError('Invalid field check')
  def update(p):
   if p['state']!='ready':raise ValueError('Finish preparation before field checks')
   p['journey']={'checks':checks,'source':'operator-reported','updated_at':time.time()}
  return public_plan(store.modify('team',id,update))
 @app.get('/api/teams/{id}')
 def get_team(id):
  obj=store.get('team',id)
  if not obj or obj['state']=='deleted':raise HTTPException(404,'Team not found')
  return public_plan(obj)
 @app.post('/api/teams/{id}/prepare/{member}')
 def prepare(id,member,body:dict):
  found=next((d for d in worker.discover()if d['mac']==body['device']),None)
  if not found:raise ValueError('Device unavailable; reconnect it')
  return service.prepare(id,member,found)
 @app.post('/api/teams/{id}/cancel/{member}')
 def cancel_member(id,member):
  plan=store.get('team',id);item=next((m for m in plan['members']if m['id']==member),None)if plan else None
  if not item or not item.get('binding'):raise ValueError('Preparation unavailable')
  return worker.cancel(item['binding']['mac'])
 @app.post('/api/teams/{id}/archive')
 def archive(id):
  if any(j[0]==id for j in service.jobs):raise ValueError('Wait for preparation to finish')
  obj=store.modify('team',id,lambda p:p.update(state='archived'));return public_plan(obj)
 @app.post('/api/teams/{id}/delete')
 def delete_team(id,body:dict):
  with service.lock:
   plan=store.get('team',id)
   if not plan:raise HTTPException(404,'Team not found')
   if body.get('confirm')!='REMOVE TEAM FROM LIST'or body.get('team_name')!=plan['name']:raise ValueError('Type the exact team name to delete this team')
   if any(j[0]==id for j in service.jobs):raise ValueError('Wait for preparation to finish')
   store.modify('team',id,lambda p:p.update(state='deleted',deleted_at=time.time()))
  return {'removed_from_list':True,'devices_cleared':0,'custody_retained':True,'message':'Team deleted from the app. Devices retain their local team until reissued. Saved evidence and recovery custody are retained.'}
 @app.post('/api/offline/preview')
 def offline_preview(body:dict):
  found=next((d for d in worker.discover()if d['mac']==body['device']),None)
  if not found:raise ValueError('Connect the offline creator Ghost')
  return offline.preview(found)
 @app.post('/api/offline/import')
 def offline_import(body:dict):
  if body.get('confirm')!='IMPORT SAME TEAM AND TRANSFER CUSTODY':raise ValueError('Confirm same-team custody transfer')
  return offline.commit(body['preview'])
 @app.get('/api/intelligence')
 def intelligence():return {'findings':store.all('finding'),'briefings':store.all('briefing'),'decisions':store.all('field_decision')}
 @app.get('/api/intelligence/design-feedback/{snapshot}')
 def design_feedback(snapshot:str,request:Request):
  if len(snapshot)!=64:raise ValueError('Invalid dataset')
  key=request.state.session['username']+'/'+snapshot
  return {view:store.get('design_feedback',key+'/'+view) for view in ('atlas','volume','signal','queue')}
 @app.post('/api/intelligence/design-feedback/{snapshot}')
 def save_design_feedback(snapshot:str,body:dict,request:Request):
  view=body.get('view');note=body.get('note');rating=body.get('rating')
  if len(snapshot)!=64 or any(c not in '0123456789abcdef' for c in snapshot) or view not in ('atlas','volume','signal','queue') or rating not in ('Keep','Change','Skip') or not isinstance(note,str) or len(note)>3000:
   raise ValueError('Choose a verdict and keep feedback under 3,000 characters.')
  key=request.state.session['username']+'/'+snapshot+'/'+view
  store.put('design_feedback',key,{'view':view,'rating':rating,'note':note,'saved_at':time.time()})
  return {'saved':True}
 @app.post('/api/intelligence/import')
 def import_intelligence(body:dict):
  plan=store.get('team',body['team'])
  if not plan:raise ValueError('Team missing')
  member=next((m for m in plan['members']if m['id']==body['member']),None)
  if not member or not member.get('binding')or member['product']!='ghost':raise ValueError('Choose a prepared Ghost')
  reports=worker.briefings(member['binding']);results=[]
  for report in reports:
   if report['reader_id']!=member['id']:raise ValueError('Connected Ghost differs from selected member')
   result=intel.ingest(plan,report);results.append({'source':result['source_id'],'cards':result['card_count'],'authentication':result['source_authentication']})
  decisions=[]
  for report in worker.decisions(member['binding']):
   if report['actor_id']!=member['id']:raise ValueError('Connected Ghost decision actor differs')
   decisions.append(intel.ingest_decision(plan,report)['id'])
  return {'reports':results,'decisions':decisions,'radio_actions':0}
 @app.post('/api/intelligence/review')
 def review_intelligence(body:dict,request:Request):return intel.review(body['id'],body['revision'],body['disposition'],body.get('note',''),request.state.session['username'])
 @app.get('/api/recordings')
 def recording_list():return records.listing()
 @app.get('/api/recordings/{id}')
 def recording_read(id):return records.read(id)
 @app.post('/api/recordings/device')
 def recording_device(body:dict):
  plan=store.get('team',body['team']);member=next((m for m in plan['members']if m['id']==body['member']),None)if plan else None
  if not member or member['product']!='drop'or not member.get('binding'):raise ValueError('Choose a prepared Drop')
  return worker.recordings(member['binding'])
 @app.post('/api/recordings/import')
 def recording_import(body:dict):
  plan=store.get('team',body['team']);member=next((m for m in plan['members']if m['id']==body['member']),None)if plan else None
  if not member or member['product']!='drop'or not member.get('binding'):raise ValueError('Choose a prepared Drop')
  return records.ingest(plan,worker.recording(member['binding'],body['segment']))
 @app.get('/')
 def index():return FileResponse(ROOT/'web/index.html')
 app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
 return app

def configured():
 data=Path(os.environ.get('WZL_DATA','.runtime/data'))
 return create_app(data/'app.sqlite',os.environ['WZL_MASTER_KEY'],Adapter(os.environ.get('WZL_ADAPTER','http://127.0.0.1:5015'),Path(os.environ['WZL_WORKER_TOKEN']).read_text().strip()),os.environ.get('WZL_BOOTSTRAP'))
