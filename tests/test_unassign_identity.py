import pytest
from app.native import Native

def test_wrong_chip_never_reaches_reissue_or_disarm(tmp_path):
 native=Native(tmp_path);commands=[]
 class Unit:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def exchange(self,*args,**kwargs):commands.append(args);raise AssertionError('Wrong-chip unit must not receive cleanup commands')
 native.unit=lambda mac:Unit();native.identity=lambda unit,mac:'esp32c5'
 binding={'mac':'AA:BB:CC:DD:EE:01','chip':'esp32s3','product':'drop','profile':'headless'}
 with pytest.raises(ValueError,match='Physical chip differs'):native.unassign(binding,'12'*16)
 assert commands==[]and native.active==set()
