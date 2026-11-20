"""Discovery authorization and actual local Identify transport fixture."""
from types import SimpleNamespace
import pytest
from app.native import Native
import app.native as module

def test_explicit_empty_allowlist_opens_nothing(tmp_path,monkeypatch):
 rows=[SimpleNamespace(serial_number='02:00:00:00:00:01',device='/dev/example',vid=0x303a)]
 monkeypatch.setattr(module.list_ports,'comports',lambda:rows)
 assert Native(tmp_path,[]).ports()=={}
 assert Native(tmp_path,None).ports()=={'02:00:00:00:00:01':'/dev/example'}
 rows.append(SimpleNamespace(serial_number='printer',device='/dev/printer',vid=0x1234))
 assert '/dev/printer'not in Native(tmp_path,None).ports().values()

def test_identify_requires_exact_identity_and_serial_ack(tmp_path,monkeypatch):
 mac='02:00:00:00:00:01';native=Native(tmp_path,[mac]);native.labels[mac]=7
 class Unit:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def exchange(self,line,prefix=None,**kwargs):
   if line=='gig identity':return 'GIG IDENTITY '+mac+' esp32s3'
   assert line=='gig identify 7';return 'IDENTIFY LOCAL OLED 3000'
 monkeypatch.setattr(native,'unit',lambda mac:Unit())
 result=native.identify({'mac':mac,'chip':'esp32s3','product':'ghost'})
 assert result['label']=='Device 7'and result['radio_actions']==0 and result['authentication']is False
 with pytest.raises(ValueError,match='current identification'):native.identify({'mac':mac,'chip':'esp32s3','product':'ghost'})
 assert not native.active

@pytest.mark.parametrize('profile,command,reply',[
 (1,'help','WZLG0A5T firmware 0.15.0-dev38 GPLv3 | serial 115200'),
 (2,'help','WZLG0A5T firmware 0.15.0-dev39 GPLv3 | serial 115200'),
 (3,'gd hello','GHOST_DROP 0.15.0-dev29'),
])
def test_running_version_retries_and_is_bound_to_connection(tmp_path,monkeypatch,profile,command,reply):
 mac='02:00:00:00:00:01';ports={mac:'test'};native=Native(tmp_path)
 monkeypatch.setattr(native,'inventory',lambda:ports)
 reads=[]
 class Unit:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def exchange(self,line,prefix,**kwargs):
   if line=='gig identity':return 'GIG IDENTITY '+mac+' esp32c5'
   if line=='plan capability':return 'PLAN CAPABILITY 2 PROFILE '+str(profile)
   assert line==command and reply.startswith(prefix)
   reads.append(line)
   if len(reads)==1:raise TimeoutError()
   return reply
 monkeypatch.setattr(native,'unit',lambda mac:Unit())
 first=native.discover()[0]
 assert first['compatible'] and not first['firmware_version']
 native.cache[mac]['checked_at']-=11
 version=reply.split()[1 if profile==3 else 2]
 assert native.discover()[0]['firmware_version']==version
 assert native.discover()[0]['firmware_version']==version and len(reads)==2
 ports.clear()
 assert native.discover()==[]
 ports[mac]='new port'
 assert native.discover()[0]['firmware_version']==version and len(reads)==3
