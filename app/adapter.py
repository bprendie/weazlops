"""Authenticated native-worker boundary. Future browser transport shares this contract."""
import json,urllib.request,urllib.error
from .firmware_upload import ZIP_TYPE
class Adapter:
 def __init__(self,url,token):self.url=url;self.token=token
 def request(self,path,data=None,content_type='application/json'):
  if data is not None and content_type=='application/json':data=json.dumps(data).encode()
  req=urllib.request.Request(self.url+path,data=data,headers={'Authorization':'Bearer '+self.token,'Content-Type':content_type})
  try:
   with urllib.request.urlopen(req,timeout=300 if path in ('/recording','/firmware/import') else 60)as r:return json.load(r)
  except urllib.error.HTTPError as e:
   try:detail=json.load(e).get('detail','USB operation failed')
   except Exception:detail='USB adapter rejected operation'
   raise ValueError(detail)from None
  except urllib.error.URLError:raise ValueError("Device connection temporarily unavailable. Try again.")from None
 def discover(self):return self.request('/devices')
 def prepare(self,binding,image,plan,member):
  fields=('id','operation','roster','recipient','certificate','origin','handout','drop_name')
  return self.request('/prepare',{'binding':binding,'image':image.hex(),'plan':{k:plan[k]for k in fields if k in plan},'member':{k:member[k]for k in ('id','public')}})

 def unassign(self,binding,operation):return self.request('/unassign',{'binding':binding,'operation':operation})
 def briefings(self,binding):return self.request('/briefings',{'binding':binding})
 def recordings(self,binding):return self.request('/recordings',{'binding':binding})
 def recording(self,binding,segment):return self.request('/recording',{'binding':binding,'segment':segment})
 def offline(self,binding):return self.request('/offline',{'binding':binding})
 def custody(self,binding,digest,nonce,signature):return self.request('/custody',{'binding':binding,'digest':digest,'nonce':nonce,'signature':signature})
 def decisions(self,binding):return self.request('/decisions',{'binding':binding})

 def cancel(self,mac):return self.request('/cancel',{'mac':mac})

 def identify(self,binding):return self.request("/identify",{"binding":binding})

 def firmware_catalog(self):return self.request('/firmware')
 def import_firmware(self,bundle):return self.request('/firmware/import',bundle,ZIP_TYPE)
 def flash(self,binding,release):return self.request('/firmware',{'binding':binding,'release':release})
