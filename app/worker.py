from pathlib import Path
import hmac,json,os
from fastapi import FastAPI,Request,HTTPException
from .native import Native
from .firmware_upload import FirmwareUpload, MAX_RELEASE_BYTES
from .firmware_catalog import import_bundle
from io import BytesIO
from starlette.concurrency import run_in_threadpool
private=Path(os.environ.get('WZL_PRIVATE','.runtime'))
token=Path(os.environ['WZL_WORKER_TOKEN']).read_text().strip()
allowpath=os.environ.get('WZL_BENCH_ALLOWLIST')
denypath=os.environ.get('WZL_DEVICE_DENYLIST')
native=Native(private,json.loads(Path(allowpath).read_text())if allowpath else None,json.loads(Path(denypath).read_text())if denypath else ())
from .firmware import Firmware
firmware=Firmware(native,Path(__file__).resolve().parents[1]/'.runtime/firmware')
app=FastAPI(docs_url=None,redoc_url=None)
firmware_upload=FirmwareUpload()
@app.middleware('http')
async def auth(request,call_next):
 from fastapi.responses import JSONResponse
 if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):return JSONResponse({'detail':'Unauthorized adapter request'},401)
 limit=MAX_RELEASE_BYTES if request.method=='POST' and request.url.path=='/firmware/import' else 16384
 if int(request.headers.get('content-length','0'))>limit:return JSONResponse({'detail':'Request too large'},413)
 return await call_next(request)
@app.get('/devices')
def devices():return native.discover()
@app.get('/health')
def health():return {'ready':True,'active':len(native.active),'transport':'native-usb'}
@app.post('/prepare')
def prepare(body:dict):
 try:return native.prepare(body['binding'],bytes.fromhex(body['image']),body['plan'],body['member'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))

@app.post('/unassign')
def unassign(body:dict):
 try:return native.unassign(body['binding'],body['operation'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))
@app.post('/briefings')
def briefings(body:dict):
 try:return native.briefings(body['binding'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))
@app.post('/recordings')
def recordings(body:dict):
 try:return native.recordings(body['binding'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))
@app.post('/recording')
def recording(body:dict):
 try:return native.recording(body['binding'],body['segment'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))
@app.post('/offline')
def offline(body:dict):
 try:return native.offline(body['binding'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))
@app.post('/custody')
def custody(body:dict):
 try:return native.custody(body['binding'],body['digest'],body['nonce'],body['signature'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))
@app.post('/decisions')
def decisions(body:dict):
 try:return native.decisions(body['binding'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))

@app.post('/cancel')
def cancel(body:dict):return native.cancel(body['mac'])

@app.post('/identify')
def identify(body:dict):
 try:return native.identify(body['binding'])
 except (OSError,ValueError,TimeoutError)as e:raise HTTPException(409,str(e))

@app.get('/firmware')
def firmware_catalog():
 return firmware.listing()

@app.post('/firmware')
def flash_selected(body:dict):
 try:return firmware.start(body['binding'],body['release'])
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/firmware/import')
async def import_firmware(request:Request):
 if firmware_upload.lock.locked():raise HTTPException(409,'An import is already in progress.')
 async with firmware_upload.lock:
  bundle=await firmware_upload.read(request)
  try:return await run_in_threadpool(import_bundle,BytesIO(bundle),firmware.root)
  except ValueError as exc:raise HTTPException(400,str(exc)) from exc
  except OSError as exc:raise HTTPException(503,'Could not save the release. Check station storage and retry.') from exc
