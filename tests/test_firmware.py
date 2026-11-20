import sys
from types import SimpleNamespace
import pytest
from app.firmware import Firmware

MAC='00:11:22:33:44:55'

@pytest.mark.parametrize('mismatch',['chip','mac','capacity','layout',None])
def test_write_only_after_exact_hardware_and_layout(monkeypatch,mismatch):
    table=b'partition table'
    writes=[]
    events=[]
    def written(esp,images):
        writes.append(images)
        events.append('write')
    esp=SimpleNamespace(CHIP_NAME='ESP32-S3' if mismatch!='chip' else 'ESP32-C5',
        read_mac=lambda:bytes.fromhex('001122334455' if mismatch!='mac' else '000000000000'),
        _port=SimpleNamespace(close=lambda:events.append('close')))
    module=SimpleNamespace(detect_chip=lambda port:esp,run_stub=lambda esp:esp,
        attach_flash=lambda esp:None,detect_flash_size=lambda esp:'4MB' if mismatch=='capacity' else '8MB',
        read_flash=lambda *a,**kw:b'other' if mismatch=='layout' else table,
        write_flash=written,verify_flash=lambda esp,data:events.append('verify'),
        reset_chip=lambda esp:events.append('reset'))
    monkeypatch.setitem(sys.modules,'esptool',module)
    images={'partitions.bin':(32768,table),'firmware.bin':(65536,b'firmware')}
    if mismatch:
        with pytest.raises(ValueError):
            Firmware.program('fixture',MAC,'esp32s3','8MB',images,lambda msg:None)
        assert not writes
    else:
        Firmware.program('fixture',MAC,'esp32s3','8MB',images,lambda msg:None)
        assert writes==[sorted(images.values())]
        assert events==['write','verify','reset','close']

@pytest.mark.parametrize('profile,problem',[
    ('headless',None),('original',None),('xl',None),('original','old uptime'),
    ('original','absent uptime'),('xl','wrong profile'),('headless','wrong chip'),
    ('headless','wrong version'),('headless','frozen clock'),('original','reboot loop'),
])
def test_postflash_receipt_requires_live_clock_identity_and_profile(monkeypatch,profile,problem):
    import json
    import app.firmware as fw
    clock=[100.]
    def wait(seconds):clock[0]+=seconds
    monkeypatch.setattr(fw,'time',SimpleNamespace(sleep=wait,monotonic=lambda:clock[0],time=lambda:100000+clock[0]))
    class Unit:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def exchange(self,line,prefix,timeout):
            version='wrong-version' if problem=='wrong version' else 'dev46'
            age=round((clock[0]-100)*1000)
            if problem=='old uptime':age+=60000
            if problem=='frozen clock':age=0
            if problem=='reboot loop':age%=400
            if line=='plan capability':return 'PLAN CAPABILITY 2 PROFILE '+str(fw.PROFILES['original' if problem=='wrong profile' else profile])
            if line=='gd hello':return 'GHOST_DROP '+version
            if line=='gd status':return f'STATE IDLE_UNARMED ARMED 0 UPTIME {age} SIGNAL NONE'
            assert line=='poll status'
            state={'firmware':version,'chip':'esp32s3','display_profile':profile,'uptime_ms':age,'pocket_locked':0,'pocket':0}
            if problem=='absent uptime':state.pop('uptime_ms')
            return 'STATUS '+json.dumps(state)
    native=SimpleNamespace(unit=lambda mac: Unit(),identity=lambda u,mac:'esp32c5' if problem=='wrong chip' else 'esp32s3')
    if problem:
        with pytest.raises(ValueError,match='confirm a fresh boot'):fw.verify_boot(native,MAC,'esp32s3',profile,'dev46',100)
    else:
        boot=fw.verify_boot(native,MAC,'esp32s3',profile,'dev46',100)
        assert boot['version']=='dev46' and boot['profile']==profile and boot['uptime_ms']>=300
        assert ('auto_pocket_lock' in boot)==(profile!='headless')
