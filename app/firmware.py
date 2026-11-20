"""Operator-selected updates from the locally imported, paired release catalog."""
import fcntl
import hashlib
import json
import re
import threading
import time
from pathlib import Path

PRODUCTS = {'original':'weazlghost', 'xl':'weazlghost-xl', 'headless':'ghost-drop'}
PROFILES = {'original':1, 'xl':2, 'headless':3}


def running_version(unit, profile):
    command, prefix = ('gd hello', 'GHOST_DROP ') if profile == 'headless' else ('help', 'WZLG0A5T firmware ')
    reply = unit.exchange(command, prefix, timeout=2)
    fields = reply.removeprefix(prefix).split()
    if not reply.startswith(prefix) or not fields:
        raise ValueError('Missing firmware version.')
    return fields[0]


def boot_sample(unit, profile, chip, version):
    """Read the live application's clock. A queued help banner carries no boot evidence."""
    if profile == 'headless':
        if running_version(unit, profile) != version:
            raise ValueError('Different firmware version')
        state = unit.exchange('gd status', 'STATE ', timeout=3)
        match = re.search(r'\bUPTIME (\d+)\b', state)
        if not match:
            raise ValueError('Missing Drop uptime')
        return {'uptime_ms':int(match[1])}
    state = json.loads(unit.exchange('poll status', 'STATUS ', timeout=4).removeprefix('STATUS '))
    if not isinstance(state,dict) or state.get('firmware') != version:
        raise ValueError('Different firmware version')
    if state.get('chip',chip) != chip or state.get('display_profile',profile) != profile:
        raise ValueError('Different hardware profile')
    uptime = state.get('uptime_ms')
    if type(uptime) is not int or uptime < 0:
        raise ValueError('Missing Ghost uptime')
    result = {'uptime_ms':uptime}
    if 'pocket_locked' in state and state.get('pocket') in (0,1):
        result['auto_pocket_lock'] = bool(state['pocket'])
    return result


def verify_boot(native, mac, chip, profile, version, reset_started):
    deadline = reset_started + 35
    while time.monotonic() < deadline:
        try:
            with native.unit(mac) as unit:
                if native.identity(unit,mac) != chip:
                    raise ValueError('Different chip')
                capability = unit.exchange('plan capability','PLAN CAPABILITY ',timeout=3)
                if capability != f'PLAN CAPABILITY 2 PROFILE {PROFILES[profile]}':
                    raise ValueError('Different profile')
                first_started = time.monotonic()
                first = boot_sample(unit,profile,chip,version)
                first_finished = time.monotonic()
                time.sleep(.4)
                second_started = time.monotonic()
                second = boot_sample(unit,profile,chip,version)
                now = time.monotonic()
                # Both samples must belong to a boot recent enough to have
                # started after this job's ROM reset, including same-version flashes.
                advance = second['uptime_ms']-first['uptime_ms']
                if (now <= deadline and first['uptime_ms'] <= (first_finished-reset_started)*1000+100
                        and second['uptime_ms'] <= (now-reset_started)*1000+100
                        and (second_started-first_finished)*1000-100 <= advance <= (now-first_started)*1000+100
                        and advance > 0):
                    return dict(second,version=version,chip=chip,profile=profile,verified_at=time.time())
        except (OSError,TimeoutError,ValueError):
            pass  # USB can re-enumerate and the app may still be initializing.
        time.sleep(.25)
    raise ValueError('Image written. Could not confirm a fresh boot of the selected firmware on this device.')


class Firmware:
    def __init__(self, native, repository):
        self.native = native
        self.root = Path(repository)
        self.jobs = {}

    def entries(self):
        return [json.loads(p.read_text()) for p in sorted(self.root.glob('*/entry.json'))
                if not p.parent.name.startswith('tmp')]

    def listing(self):
        with self.native.lock:
            jobs = [dict(j) for j in self.jobs.values()]
        releases = self.entries()
        for entry in releases:
            entry['running_versions'] = {
                chip: json.loads((self.root/entry['id']/chip/'manifest.json').read_text()).get('firmware_version')
                for chip in entry['targets']
            }
        return {'releases': releases, 'jobs': jobs}

    def start(self, binding, release_id):
        n = self.native
        mac = binding['mac']
        with n.lock:
            live = n.cache.get(mac, {})
            if mac not in n.ports() or not live.get('compatible') or any(
                    live.get(k) != binding.get(k) for k in ('product','profile','chip')):
                raise ValueError('Reconnect and identify the selected device.')
            if mac in n.active:
                raise ValueError('Device is busy.')
            entry = next((r for r in self.entries() if r['id'] == release_id), None)
            if not entry or entry['product'] != PRODUCTS.get(live['profile']) or live['chip'] not in entry['targets']:
                raise ValueError('Choose a release matching this device.')
            job = {'device':mac, 'label':f'Device {n.labels[mac]}', 'release':entry['name'],
                   'stage':'Checking release', 'running':True}
            n.active.add(mac)
            self.jobs[mac] = job
            try:
                threading.Thread(target=self.run,args=(binding,entry,job),daemon=True).start()
            except BaseException:
                n.active.discard(mac)
                self.jobs.pop(mac,None)
                raise
            return dict(job)

    def run(self, binding, entry, job):
        mac, chip, profile = (binding[k] for k in ('mac','chip','profile'))
        n = self.native
        def stage(message):
            with n.lock:
                job['stage'] = message
        try:
            folder = self.root/entry['id']/chip
            data = (folder/'manifest.json').read_bytes()
            if hashlib.sha256(data).hexdigest() != entry['targets'][chip]:
                raise ValueError('Release manifest changed.')
            manifest = json.loads(data)
            images = {}
            for image in manifest['images']:
                data = (folder/image['file']).read_bytes()
                if hashlib.sha256(data).hexdigest() != image['sha256']:
                    raise ValueError('Release image failed verification.')
                images[image['file']] = (image['offset'],data)
            with (n.private/(mac.replace(':','')+'.lock')).open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                stage('Checking device')
                with n.unit(mac) as unit:
                    if n.identity(unit,mac) != chip or unit.exchange('plan capability','PLAN CAPABILITY ',timeout=3) != f'PLAN CAPABILITY 2 PROFILE {PROFILES[profile]}':
                        raise ValueError('Device identity or display profile changed.')
                    if profile == 'headless':
                        state = unit.exchange('gd status','STATE ',timeout=3)
                        if ' ARMED 0 ' not in state or not state.startswith('STATE IDLE_UNARMED '):
                            raise ValueError('Stop recording and disarm this Drop before updating.')
                port = n.ports().get(mac)
                if not port:
                    raise ValueError('Selected device disconnected.')
                reset_started = self.program(port, mac, chip, manifest['flash_size'], images, stage)
                stage('Checking firmware on the restarted device')
                receipt = verify_boot(n,mac,chip,profile,manifest['firmware_version'],reset_started)
                with n.lock:
                    job.update(stage='Reboot verified',boot=receipt)
        except ValueError as exc:
            # Keep native addresses, paths and third-party diagnostics out of the UI.
            reason = str(exc)
            stage(reason if reason in USER_ERRORS else 'Firmware update failed. Reconnect and inspect the device.')
        except Exception:
            stage('Firmware update interrupted. Reconnect and inspect the device.')
        finally:
            with n.lock:
                job['running'] = False
                n.active.discard(mac)
                n.cache.pop(mac,None)

    @staticmethod
    def program(port, mac, chip, size, images, stage):
        import esptool
        esp = esptool.detect_chip(port)
        try:
            if esp.CHIP_NAME.lower().replace('-','') != chip or bytes(esp.read_mac()).hex() != mac.lower().replace(':',''):
                raise ValueError('Bootloader identity differs from the selected device.')
            esp = esptool.run_stub(esp)
            esptool.attach_flash(esp)
            if esptool.detect_flash_size(esp) != size:
                raise ValueError('Flash capacity differs from the release.')
            offset,table = images['partitions.bin']
            if esptool.read_flash(esp,offset,len(table),no_progress=True) != table:
                raise ValueError('Partition layouts differ. This update requires a separate migration.')
            payload = sorted(images.values())
            stage('Writing firmware')
            esptool.write_flash(esp,payload)
            stage('Verifying flash contents')
            esptool.verify_flash(esp,payload)
        finally:
            try:
                stage('Rebooting device')
                reset_started = time.monotonic()
                esptool.reset_chip(esp)
            finally:
                esp._port.close()
        return reset_started

USER_ERRORS = {
    'Release manifest changed.', 'Release image failed verification.',
    'Device identity or display profile changed.', 'Selected device disconnected.',
    'Stop recording and disarm this Drop before updating.',
    'Image written. Could not confirm a fresh boot of the selected firmware on this device.',
    'Bootloader identity differs from the selected device.',
    'Flash capacity differs from the release.',
    'Partition layouts differ. This update requires a separate migration.',
}
