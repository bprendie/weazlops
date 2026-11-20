"""Fail-closed paired release ingestion. No archive path extraction."""
import hashlib,json,re,zipfile,struct
from esptool.bin_image import LoadFirmwareImage
from pathlib import Path

CHIPS=('esp32s3','esp32c5')
def validate_release(path,product,version,output):
    if product not in ('weazlghost','weazlghost-xl','ghost-drop') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',version):raise ValueError('Invalid product or version')
    results={};output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path) as z:
        members=z.infolist()
        if len(members)>100 or sum(i.file_size for i in members)>64*1024*1024:raise ValueError('Release archive exceeds limits')
        names=[i.filename for i in members]
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive paths')
        for name in names:
            if name.startswith('/') or '..' in Path(name).parts or '\\' in name:raise ValueError('Unsafe archive path')
        for chip in CHIPS:
            candidates=[n for n in names if Path(n).name=='manifest.json' and Path(n).parent.name==chip]
            if len(candidates)!=1:raise ValueError('Exactly one manifest for each required chip is necessary')
            source=candidates[0];base=source.rsplit('/',1)[0]
            if z.getinfo(source).file_size>65536:raise ValueError('Manifest too large')
            manifest=json.loads(z.read(source))
            if manifest.get('chip')!=chip or manifest.get('board')!={'esp32s3':'seeed_xiao_esp32s3','esp32c5':'seeed-xiao-esp32-c5'}[chip] or manifest.get('product')!=product or manifest.get('version')!=version:raise ValueError('Manifest target does not match upload')
            if not re.fullmatch('[0-9a-f]{64}',manifest.get('source_sha256','')) or not manifest.get('toolchain') or not manifest.get('partitions'):raise ValueError('Manifest provenance incomplete')
            if product=='weazlghost-xl' and (manifest.get('display_profile')!='xl' or manifest.get('display_pixels')!=[128,64]):raise ValueError('XL display profile mismatch')
            if product=='weazlghost' and manifest.get('display_profile','original')!='original':raise ValueError('Original display profile mismatch')
            images=manifest.get('images',[])
            if not 2<=len(images)<=10:raise ValueError('Invalid image count')
            if manifest.get('flash_size') not in ('4MB','8MB','16MB'):raise ValueError('Unsupported physical flash size')
            flash_size=int(manifest['flash_size'][:-2])*1024*1024
            if not {'bootloader.bin','firmware.bin','partitions.bin'}.issubset({i.get('file') for i in images}):raise ValueError('Bootloader, partition table and application required')
            if len({i.get('file') for i in images})!=len(images):raise ValueError('Duplicate image filename')
            seen=[];chipdir=output/chip;chipdir.mkdir(exist_ok=True)
            for image in images:
                name=image.get('file','');offset=image.get('offset')
                if name not in ('bootloader.bin','partitions.bin','boot_app0.bin','ota_data_initial.bin','firmware.bin') or Path(name).name!=name or not name.endswith('.bin') or type(offset) is not int or not 0<=offset<16*1024*1024:raise ValueError('Invalid flash map')
                data=z.read(base+'/'+name)
                if not data or len(data)>8*1024*1024 or hashlib.sha256(data).hexdigest()!=image.get('sha256'):raise ValueError('Image hash mismatch')
                end=offset+len(data)
                if end>flash_size or any(offset<b and end>a for a,b in seen):raise ValueError('Overlapping flash map')
                if name in ('boot_app0.bin','ota_data_initial.bin') and (offset!=57344 or len(data)>8192):raise ValueError('Boot app data outside fixed public bootstrap area')
                if name in ('bootloader.bin','firmware.bin'):
                    parsed=LoadFirmwareImage(chip,data)
                    if parsed.chip_id!=({'esp32s3':9,'esp32c5':23}[chip]) or parsed.checksum!=parsed.calculate_checksum() or (parsed.append_digest and parsed.stored_digest!=parsed.calc_digest):raise ValueError('Executable chip/header integrity mismatch')
                    if name=='bootloader.bin' and offset!=({'esp32s3':0,'esp32c5':8192}[chip]):raise ValueError('Wrong bootloader offset for chip')
                    if name=='firmware.bin' and not any(p.get('type')==0 and p.get('offset')==offset and len(data)<=p.get('size',0) for p in manifest['partitions']):raise ValueError('Application outside declared partition')
                if name=='partitions.bin':
                    if offset!=32768:raise ValueError('Unexpected partition-table address')
                    actual=[]
                    for at in range(0,len(data)-31,32):
                        magic,kind,subtype,part_offset,size,label,flags=struct.unpack_from('<HBBII16sI',data,at)
                        if magic!=0x50aa:break
                        actual.append((label.rstrip(b'\x00').decode('ascii'),kind,subtype,part_offset,size,flags))
                    expected=[(p['label'],p['type'],p['subtype'],p['offset'],p['size'],p.get('flags',0)) for p in manifest['partitions']]
                    if actual!=expected:raise ValueError('Partition table differs from manifest')
                seen.append((offset,end));(chipdir/name).write_bytes(data)
            (chipdir/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');results[chip]=manifest
        if results[CHIPS[0]]['source_sha256']!=results[CHIPS[1]]['source_sha256']:validate_target_sources(z,results)
    return results

def validate_target_sources(archive,results):
    """Different target configurations are valid only with reproducible sources.

    Match the firmware packager's ordered source digest for each target, then
    require byte-identical common firmware. Never paper over different sources
    by rewriting immutable manifests to share an invented hash.
    """
    import io
    if 'corresponding-source.zip' not in archive.namelist():raise ValueError('Different target source hashes require corresponding target sources')
    with zipfile.ZipFile(io.BytesIO(archive.read('corresponding-source.zip'))) as source:
        names=source.namelist()
        if len(names)>10000 or len(names)!=len(set(names)):raise ValueError('Invalid corresponding source archive')
        firmware=[]
        for chip in CHIPS:
            prefix='targets/'+chip+'/'
            available={n[len(prefix):]:n for n in names if n.startswith(prefix) and not n.endswith('/')}
            paths=sorted(n for n in available if n.startswith('firmware/'))+['platformio.ini']+sorted(n for n in available if re.fullmatch(r'partitions[^/]*\.csv',n))
            paths += ['tools/'+n for n in ('firmware_manifest.py','pio_usb_upload.py','build.sh') if 'tools/'+n in available]
            paths += [n for n in ('CMakeLists.txt','sdkconfig.defaults') if n in available]
            if not paths or sum(source.getinfo(available[n]).file_size for n in paths)>32*1024*1024:raise ValueError('Missing or oversized target source')
            digest=hashlib.sha256();common={}
            for name in paths:
                data=source.read(available[name]);digest.update(name.encode()+b'\0'+data)
                if name.startswith('firmware/'):common[name]=hashlib.sha256(data).hexdigest()
            manifest=results[chip]
            if digest.hexdigest()!=manifest['source_sha256']:raise ValueError('Corresponding source digest mismatch')
            config='sdkconfig.'+manifest['environment']
            if hashlib.sha256(source.read(available[config])).hexdigest()!=manifest.get('configuration_sha256'):raise ValueError('Target configuration digest mismatch')
            if not re.fullmatch('[0-9a-f]{64}',manifest.get('build_sha256','')):raise ValueError('Target build identity missing')
            firmware.append(common)
        if not firmware[0] or firmware[0]!=firmware[1]:raise ValueError('Paired common firmware differs')
