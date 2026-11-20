"""Host-only transport fault fixture exercises real Native commit boundary."""
import threading,pytest
from app.native import Native
from app.protocol import new_plan,package
class FakeUSB:
 def __init__(self,native,mac):self.native=native;self.mac=mac;self.calls=[]
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def exchange(self,line,prefix=None,**kwargs):
  self.calls.append(line.split()[0:2])
  if line=='gig identity':return 'GIG IDENTITY '+self.mac+' esp32s3'
  if line=='plan capability':return 'PLAN CAPABILITY 2 PROFILE 1'
  if line=='plan status':return 'PLAN phase=0 operation=NONE member=1'
  if line.startswith('plan begin '):return 'PLAN STAGING'
  if line.startswith('plan chunk '):
   self.native.cancel(self.mac);return 'PLAN CHUNK 96'
  raise AssertionError('Unexpected operation after cancellation: '+str(line.split()[:2]))
def test_cancel_staged_package_never_commits_or_creates_intent(tmp_path,monkeypatch):
 native=Native(tmp_path);mac='02:00:00:00:00:01';usb=FakeUSB(native,mac);monkeypatch.setattr(native,'unit',lambda _:usb)
 plan=new_plan('Cancel fixture',[{'product':'ghost','callsign':'STONEY','lead':True}]);member=plan['members'][0];binding={'mac':mac,'chip':'esp32s3','profile':'original','product':'ghost'};image=package(plan,member,mac,'esp32s3','original')
 with pytest.raises(ValueError,match='cancelled before commit'):native.prepare(binding,image,plan,member)
 assert ['plan','commit']not in usb.calls and not list(tmp_path.glob('*.json'))
 assert not native.active and not native.cancels and not native.committed

def test_cancel_committed_install_does_not_claim_rollback(tmp_path):
 native=Native(tmp_path);mac='02:00:00:00:00:01';event=threading.Event();native.active.add(mac);native.cancels[mac]=event;native.committed.add(mac)
 result=native.cancel(mac);assert result['cancelled']is False and 'committed'in result['message']and not event.is_set()
