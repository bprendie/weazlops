"""Paired target-specific configuration provenance, independent image validation."""
import hashlib,io,json,struct,zipfile
import pytest
from backend.releases import validate_release

def release_zip(product='ghost-drop',version='test1',single=False):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for chip in (['esp32s3'] if single else ['esp32s3','esp32c5']):
            from esptool.bin_image import ESP32S3FirmwareImage,ESP32C5FirmwareImage,ImageSegment
            image=(ESP32S3FirmwareImage if chip=='esp32s3' else ESP32C5FirmwareImage)();segment=ImageSegment(0x3fc88000,b'synthetic-test-fw');segment.name='synthetic';image.segments=[segment];binary=image.save(None)
            partition=struct.pack('<HBBII16sI',0x50aa,0,0,65536,10000,b'factory',0)+b'\xff'*32
            blobs={'bootloader.bin':binary,'firmware.bin':binary,'partitions.bin':partition}
            images=[{'offset':({'bootloader.bin':0 if chip=='esp32s3' else 8192,'firmware.bin':65536,'partitions.bin':32768}[name]),'file':name,'sha256':hashlib.sha256(data).hexdigest()} for name,data in blobs.items()]
            z.writestr(chip+'/manifest.json',json.dumps({'chip':chip,'board':{'esp32s3':'seeed_xiao_esp32s3','esp32c5':'seeed-xiao-esp32-c5'}[chip],'product':product,'version':version,'source_sha256':'0'*64,'toolchain':{'test':'synthetic'},'partitions':[{'label':'factory','type':0,'subtype':0,'offset':65536,'size':10000,'flags':0}],'images':images,'flash_size':'8MB'}))
            for name,data in blobs.items():z.writestr(chip+'/'+name,data)
    return out.getvalue()

def source_release(tamper=None):
    outer=io.BytesIO();source=io.BytesIO();original=zipfile.ZipFile(io.BytesIO(release_zip('weazlghost','test1')))
    with zipfile.ZipFile(source,'w') as src,zipfile.ZipFile(outer,'w') as z:
        for chip in ('esp32s3','esp32c5'):
            files={'firmware/main.cpp':b'common firmware','platformio.ini':chip.encode()}
            if tamper=='different_firmware' and chip=='esp32c5':files['firmware/main.cpp']=b'different'
            m=json.loads(original.read(chip+'/manifest.json'));h=hashlib.sha256()
            for name,data in files.items():h.update(name.encode()+b'\0'+data)
            m.update(source_sha256=h.hexdigest(),environment=chip,configuration_sha256=hashlib.sha256(chip.encode()).hexdigest(),build_sha256='1'*64)
            for name,data in files.items():src.writestr('targets/'+chip+'/'+name,data if tamper!='source' else data+b'tampered')
            src.writestr('targets/'+chip+'/sdkconfig.'+chip,chip.encode() if tamper!='config' else b'tampered')
            for name in original.namelist():
                if name.startswith(chip+'/') and not name.endswith('manifest.json'):z.writestr(name,original.read(name))
            z.writestr(chip+'/manifest.json',json.dumps(m))
    rebuilt=io.BytesIO()
    with zipfile.ZipFile(rebuilt,'w') as z,zipfile.ZipFile(io.BytesIO(outer.getvalue())) as old:
        for name in old.namelist():z.writestr(name,old.read(name))
        if tamper!='missing':z.writestr('corresponding-source.zip',source.getvalue())
    return rebuilt.getvalue()

def test_different_target_configurations_with_common_firmware(tmp_path):
    p=tmp_path/'valid.zip';p.write_bytes(source_release());m=validate_release(p,'weazlghost','test1',tmp_path/'out')
    assert m['esp32s3']['source_sha256']!=m['esp32c5']['source_sha256']

@pytest.mark.parametrize('tamper',['source','config','different_firmware','missing'])
def test_corresponding_sources_cannot_mask_mixed_or_stale_builds(tmp_path,tamper):
    p=tmp_path/'invalid.zip';p.write_bytes(source_release(tamper))
    with pytest.raises(ValueError):validate_release(p,'weazlghost','test1',tmp_path/'out')
