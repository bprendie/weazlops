"""Real browser + real API/store, synthetic USB adapter. No physical timing claim."""
import json,os,secrets,socket,threading,time
from pathlib import Path
import pytest,uvicorn
from playwright.sync_api import sync_playwright,expect
from app.main import create_app
BASE=Path(__file__).resolve().parents[1]
class Cable:
 def __init__(self):self.devices=[];self.calls=[];self.cleared=[];self.active=set();self.gate=threading.Event();self.gate.set()
 def discover(self):return [dict(d,busy=d['mac']in self.active,progress={'phase':'Sending team configuration','completed':96,'total':1024}if d['mac']in self.active else None)for d in self.devices]
 def prepare(self,binding,image,plan,member):
  self.calls.append((binding['mac'],member['id']));self.active.add(binding['mac']);assert image.startswith(b'WZLPK002');self.gate.wait(15);self.active.remove(binding['mac'])
  result={'fixture':True,'hardware_verified':False}
  if 'handout' in plan:
   from app.protocol import load,sign
   nonce=secrets.token_bytes(32);manifest=bytes.fromhex(plan['handout']['manifest'])
   msg=b'WZL-CB-PROOF-V2\0'+nonce+manifest+bytes.fromhex(plan['certificate'])[16:24]+bytes(12)
   result.update(nonce=nonce.hex(),handout={'manifest':manifest.hex(),'signature':sign(load(bytes.fromhex(member['secret'])),msg).hex()})
  return result
 def unassign(self,binding,operation):self.cleared.append(binding['mac']);return {'unassigned':True,'mac':binding['mac'],'fixture':True}
 def identify(self,binding):return {'label':'Device 1','cue':'synthetic fixture cue'}
def device(i,product='ghost',profile='original'):
 return {'mac':'02:00:00:00:00:'+f'{i:02X}','chip':'esp32s3','profile':profile,'product':product,'compatible':True,'connected':True,'label':'Device '+str(i)}
@pytest.fixture
def ui(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));bootstrap=tmp_path/'bootstrap';bootstrap.write_text(json.dumps({'username':'adminguy','password':'synthetic-wizard-password'}));cable=Cable();app=create_app(tmp_path/'data',key,cable,bootstrap)
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
 limit=time.monotonic()+5
 while not server.started and time.monotonic()<limit:time.sleep(.02)
 assert server.started
 os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(Path.home()/'.cache/ms-playwright'))
 with sync_playwright()as pw:
  browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(f'http://127.0.0.1:{port}');page.locator('[name=username]').fill('adminguy');page.locator('[name=password]').fill('synthetic-wizard-password');page.get_by_role('button',name='Sign in',exact=True).click();expect(page.locator('#home')).to_be_visible();page.locator('#homeNew').click();expect(page.locator('#planForm')).to_be_visible()
  yield page,cable,app
  browser.close();assert not errors,errors
 server.should_exit=True;thread.join(5);sock.close()
def create(page,name):
 page.locator('#teamName').fill(name);page.locator('#consent').check();page.locator('#start').click();expect(page.locator('#journeyTitle')).to_have_text(name)
def waitready(page,count,total):expect(page.locator('#progress')).to_have_text(f'{count} / {total} ready to hand out',timeout=15000)
def test_five_single_cable_unknown_arrivals_reload_and_end(ui):
 page,cable,app=ui
 page.locator('#ghostCount').select_option('3');page.locator('#dropCount').select_option('2');expect(page.locator('.slot')).to_have_count(5)
 assert page.get_by_label('Display 1',exact=True).count()==0
 create(page,'One cable crew');waitready(page,0,5)
 assert not cable.calls
 cable.gate.clear();cable.devices=[device(1)];expect(page.locator('.handout progress')).to_be_visible(timeout=12000);expect(page.locator('.handout progress')).to_have_attribute('value','96');expect(page.locator('.handout')).to_have_count(5)
 cable.gate.set();waitready(page,1,5)
 # Same prepared device remains attached: must not be assigned to slot 2.
 page.wait_for_timeout(1400);assert len(cable.calls)==1
 cable.devices=[];expect(page.locator('.device')).to_have_count(0)
 page.reload();expect(page.locator('#resumeAuto')).to_be_visible();waitready(page,1,5)
 cable.devices=[device(2,profile='xl')];expect(page.locator('.device')).to_have_count(1);page.wait_for_timeout(1200);assert len(cable.calls)==1
 page.locator('#resumeAuto').click();waitready(page,2,5);assert page.locator('.handout').nth(1).get_by_text('Ghost XL',exact=True).count()==1
 for i in (3,4,5):
  cable.devices=[];expect(page.locator('.device')).to_have_count(0)
  cable.devices=[device(i,'ghost'if i==3 else'drop','original'if i==3 else'headless')];waitready(page,i,5)
 assert len(cable.calls)==5 and len(set(x[0]for x in cable.calls))==5
 expect(page.locator('#fieldGuide')).to_be_visible();expect(page.locator('#phaseTitle')).to_have_text('One cable crew is ready')
 page.locator('#fieldGuide input').nth(0).check();page.reload();expect(page.locator('#fieldGuide input').nth(0)).to_be_checked()
 # Visible actions and right-click use same handlers; no details accordion.
 expect(page.locator('.device details')).to_have_count(0);page.locator('.device').click(button='right');expect(page.get_by_role('menu')).to_be_visible();expect(page.get_by_role('menuitem',name='Clear device')).to_be_visible();page.keyboard.press('Escape');expect(page.get_by_role('menu')).to_be_hidden()
 if os.environ.get('WZL_BROWSER_EVIDENCE'):
  out=Path(os.environ['WZL_BROWSER_EVIDENCE']);out.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out/'fixture-five-ready.png'),full_page=True);page.set_viewport_size({'width':420,'height':920});page.screenshot(path=str(out/'fixture-five-ready-phone.png'),full_page=True);assert page.locator('body').bounding_box()['width']==420
 page.locator('#teamsNav').click();page.locator('#teamList').get_by_role('button',name='Delete team',exact=True).click();expect(page.locator('#deleteConfirm')).to_be_disabled();page.locator('#deleteName').fill('One cable crew');page.locator('#deleteConfirm').click();expect(page.locator('#home')).to_be_visible();expect(page.locator('#homeEmpty')).to_be_visible();assert not cable.cleared
 assert app.state.store.all('team')[0]['state']=='deleted'
def test_multiple_connected_auto_queue_and_direct_device_cleanup(ui):
 page,cable,app=ui;cable.devices=[device(1),device(2,profile='xl'),device(3,'drop','headless')];create(page,'All cables');waitready(page,3,3);assert len(cable.calls)==3
 # No extra Prepare/Assign click needed with two same-type Ghosts attached.
 expect(page.get_by_role('button',name='Assign selected device')).to_have_count(0)
 page.on('dialog',lambda d:d.accept());page.locator('.device').first.get_by_role('button',name='Clear device',exact=True).click();expect(page.locator('#alert')).to_have_text('Device cleared and unassigned.');assert len(cable.cleared)==1
 assert app.state.store.all('team')[0]['members'][0]['status']=='released'


def test_home_member_art_lead_shield_breakglass_and_return(ui):
 page,cable,app=ui;cable.devices=[device(1),device(2,profile='xl'),device(3,'drop','headless')]
 create(page,'Blue crew');waitready(page,3,3)
 expect(page.locator('.handout img[alt="Team lead"]')).to_have_count(1)
 page.locator('#backHome').click();expect(page.locator('#home')).to_be_visible();card=page.locator('#homeTeams .dashboard-team');expect(card).to_have_count(1)
 expect(card.locator('.member-tile')).to_have_count(3);expect(card.locator('img[alt="Team lead"]')).to_have_attribute('src','/static/assets/lead-shield.svg')
 card.locator('.member-art>img').evaluate_all('(items)=>Promise.all(items.map(i=>i.decode()))')
 assert card.locator('.member-art>img').evaluate_all('(items)=>items.every(i=>i.complete&&i.naturalWidth>0)')
 expect(card.locator('.member-art>img').first).to_have_attribute('src','/static/assets/handles/stoney.png')
 expect(card.locator('.member-art>img').nth(2)).to_have_attribute('src','/static/assets/ghostdrop.png')
 expect(page.locator('#homeStats .stat').nth(0)).to_contain_text('1');expect(page.locator('#homeStats .stat').nth(1)).to_contain_text('3')
 cable.devices=[];expect(page.locator('#homeStats .stat').nth(2).locator('strong')).to_have_text('0')
 expect(card).to_contain_text('Prepared');assert 'Online'not in card.inner_text()
 # Fully reassigned teams are historical, not active fleet or resumable work.
 original=app.state.store.all('team')[0];previous=json.loads(json.dumps(original));previous['id']='e'*32;previous['name']='Previous crew'
 for member in previous['members']:member['status']='reissued'
 app.state.store.put('team',previous['id'],previous)
 page.reload();expect(page.locator('#home')).to_be_visible();expect(page.locator('#homeTeams .dashboard-team')).to_have_count(1);expect(page.locator('#homePrevious')).to_have_count(0);expect(page.locator('#homeStats .stat').first.locator('strong')).to_have_text('1')
 page.locator('#teamsNav').click();oldcard=page.locator('#teamList .dashboard-team').filter(has=page.get_by_role('heading',name='Previous crew',exact=True));expect(oldcard).to_contain_text('Previous team');expect(oldcard.get_by_role('button',name='Continue setup')).to_have_count(0);page.locator('#homeNav').click()
 if os.environ.get('WZL_BROWSER_EVIDENCE'):
  out=Path(os.environ['WZL_BROWSER_EVIDENCE']);out.mkdir(parents=True,exist_ok=True);page.locator('#home img').evaluate_all('(imgs)=>Promise.all(imgs.map(i=>i.decode()))');page.screenshot(path=str(out/'home-team-desktop.png'),full_page=True)
  page.set_viewport_size({'width':420,'height':920});page.screenshot(path=str(out/'home-team-phone.png'),full_page=True)
  assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
 page.locator('#homeTeams').get_by_role('button',name='Delete team',exact=True).click();expect(page.get_by_role('dialog')).to_be_visible();expect(page.locator('#deleteConfirm')).to_be_disabled()
 page.locator('#deleteName').fill('wrong');expect(page.locator('#deleteConfirm')).to_be_disabled();page.keyboard.press('Escape');expect(page.get_by_role('dialog')).not_to_be_visible()
 assert app.state.store.all('team')[0]['state']=='ready'
 page.locator('#homeTeams').get_by_role('button',name='Delete team',exact=True).click();page.locator('#deleteName').fill('Blue crew')
 if os.environ.get('WZL_BROWSER_EVIDENCE'):page.screenshot(path=str(Path(os.environ['WZL_BROWSER_EVIDENCE'])/'delete-confirmation.png'),full_page=True)
 before=app.state.store.get('team',original['id']);page.locator('#deleteConfirm').click();expect(page.locator('#homeEmpty')).to_be_visible();expect(page.locator('#homeTeams .dashboard-team')).to_have_count(0)
 assert not cable.cleared and len(cable.calls)==3
 after=app.state.store.get('team',original['id']);assert after['state']=='deleted'and after['members']==before['members']and after['recovery_private']==before['recovery_private']
 page.reload();expect(page.locator('#homeEmpty')).to_be_visible();page.locator('#prepareNav').click();expect(page.locator('#planForm')).to_be_visible();expect(page.locator('#handouts')).not_to_be_visible()


def test_handout_saved_to_team_before_provisioning(ui):
 page,cable,app=ui
 page.locator('#teamName').fill('Handout crew')
 page.locator('#planHandout').click()
 page.locator('#paper-callsign-0').select_option('Custom callsign…')
 page.get_by_label('Custom callsign for Ghost · Lead').fill('RAVEN')
 page.locator('#paperSummary').click()
 page.locator('#paperChoice').select_option('Custom team draft')
 for severity in range(1,4):
  group=page.get_by_role('group',name=f'Sev{severity}',exact=True)
  expect(group.get_by_role('heading',name='Possible responses')).to_be_visible()
  group.get_by_label(f'Response {5+2*severity}',exact=True).fill(f'Handout reply {severity}')
 page.get_by_role('button',name='Save team handout').click()
 expect(page.locator('#paperResult')).to_contain_text('RAVEN · Ghost · Lead')
 expect(page.locator('#paperResult')).to_contain_text('Handout reply 3')
 assert not app.state.store.all('team') and not cable.calls
 page.locator('#paperClose').click();page.reload();expect(page.locator('#teamName')).to_have_value('Handout crew')
 create(page,'Handout crew')
 page.locator('#teamHandout').click()
 expect(page.locator('#paperResult')).to_be_visible()
 expect(page.locator('#paperResult')).to_contain_text('Handout reply 3')
 plan=app.state.store.all('team')[0];assert plan['members'][0]['callsign']=='RAVEN' and plan['phrases'][10]=='Handout reply 3'
 page.reload();page.locator('#teamHandout').click();expect(page.locator('#paperResult')).to_contain_text('Handout reply 3')
 page.locator('#paperClose').click();cable.devices=[device(1)];page.locator('#resumeAuto').click();waitready(page,1,3)
 assert 'handout' in app.state.store.all('team')[0]['members'][0]['receipt']


def test_devices_hotplug_and_operator_selected_flash(ui):
 page,cable,app=ui
 release={'id':'weazlghost-test','product':'weazlghost','version':'test','name':'WeazlGhost test','running_versions':{'esp32s3':'0.15.0-dev39'},'targets':{'esp32s3':'fixture'}}
 cable.firmware_catalog=lambda:{'releases':[release],'jobs':[]}
 calls=[]
 def flash(device,version):
  calls.append((device['mac'],version))
  return {'running':True}
 cable.flash=flash
 page.locator('#equipmentNav').click()
 expect(page.locator('#usbUnits')).to_contain_text('Connect a Ghost')
 cable.devices=[dict(device(1),firmware_version='0.15.0-dev39')]
 expect(page.locator('#usbUnits')).to_contain_text('Device 1')
 expect(page.locator('#usbUnits')).not_to_contain_text(cable.devices[0]['mac'])
 expect(page.locator('#usbUnits')).to_contain_text('WeazlGhost · ESP32-S3')
 expect(page.locator('.usb-version')).to_contain_text('0.15.0-dev39')
 expect(page.locator('.usb-version')).to_contain_text('Matches library release')
 expect(page.locator('#equipment select')).to_be_hidden()
 page.get_by_text('Firmware options',exact=True).click()
 action=page.get_by_role('button',name='Flash firmware')
 expect(action).to_be_disabled()
 page.get_by_label('Firmware release').select_option(release['id'])
 page.once('dialog',lambda d:d.dismiss())
 action.click()
 assert not calls
 page.once('dialog',lambda d:d.accept())
 action.click()
 expect(action).to_be_enabled()
 assert calls==[(device(1)['mac'],release['id'])]
 cable.devices=[]
 expect(page.locator('#usbUnits')).to_contain_text('Connect a Ghost')

def test_devices_saved_details_are_distinct_from_live_version(ui):
 page,cable,app=ui
 cable.firmware_catalog=lambda:{'releases':[],'jobs':[]}
 create(page,'Version fallback')
 cable.devices=[device(1)]
 waitready(page,1,3)
 page.locator('#equipmentNav').click()
 plan=app.state.store.all('team')[0]
 member=next(m for m in plan['members'] if m['status']=='ready')
 member['receipt']['firmware_version']='0.15.0-dev38'
 app.state.store.put('team',plan['id'],plan)
 cable.devices=[dict(device(1),chip=None,profile='unknown',product='unknown',compatible=False,message='Waiting for a USB reply.')]
 card=page.locator('.usb-card')
 expect(card).to_contain_text('STONEY')
 expect(card).to_contain_text('Last assigned as WeazlGhost · ESP32-S3')
 expect(card).to_contain_text('Last verified: 0.15.0-dev38')
 expect(card.locator('.usb-version strong')).to_have_text('Unverified')
 expect(card.locator('.firmware-options')).to_have_count(0)
 cable.devices=[dict(device(1),firmware_version='0.15.0-dev40')]
 expect(card.locator('.usb-version strong')).to_have_text('0.15.0-dev40')
 expect(card).not_to_contain_text('Last verified')

def test_add_firmware_from_devices_without_usb(ui):
 page,cable,_=ui
 releases=[]
 release={'id':'ghost-drop-1.2.3','product':'ghost-drop','version':'1.2.3',
          'name':'GhostDrop 1.2.3','targets':{'esp32s3':'fixture','esp32c5':'fixture'}}
 def import_firmware(bundle):
  if bundle!=b'test release':
   raise ValueError('Invalid firmware ZIP.')
  added=not releases
  if added:releases.append(release)
  return {'release':release,'added':added}
 cable.firmware_catalog=lambda:{'releases':releases,'jobs':[]}
 cable.import_firmware=import_firmware
 page.locator('#equipmentNav').click()
 expect(page.get_by_text('Add a release ZIP to get started.')).to_be_visible()
 upload={'name':'release.zip','mimeType':'application/zip','buffer':b'test release'}
 for file,message in [(dict(upload,buffer=b'bad'), 'Invalid firmware ZIP.'),
                      (upload, 'GhostDrop 1.2.3 added to the library.'),
                      (upload, 'GhostDrop 1.2.3 is already in the library.')]:
  if not page.locator('#firmwareImport').is_visible():
   page.get_by_role('button',name='Add firmware').click()
  page.get_by_label('Release ZIP').set_input_files(file)
  page.get_by_role('button',name='Import release').click()
  expect(page.locator('#firmwareImportStatus')).to_have_text(message)
 expect(page.locator('#firmwareLibrary li')).to_have_count(1)
 expect(page.locator('#firmwareLibrary')).to_contain_text('ESP32-S3 · ESP32-C5')
 assert cable.calls==[]

def test_admin_adds_user_and_operator_signs_in(ui):
 page,_,_=ui
 page.get_by_role('button',name='Settings',exact=True).click()
 expect(page.locator('#accountList')).to_contain_text('adminguy')
 page.get_by_label('Username',exact=True).filter(visible=True).fill('Liz')
 page.locator('#newPassword').fill('synthetic-operator-password')
 expect(page.locator('#newRole')).to_have_value('operator')
 page.get_by_role('button',name='Add user',exact=True).click()
 expect(page.locator('#addUserStatus')).to_have_text('Liz can now sign in.')
 expect(page.locator('#accountList')).to_contain_text('Liz')
 expect(page.locator('#newPassword')).to_have_value('')
 page.reload();expect(page.locator('#accountList')).to_contain_text('Liz')
 page.get_by_role('button',name='Sign out').click()
 page.locator('[name=username]').fill('liz')
 page.locator('[name=password]').fill('synthetic-operator-password')
 page.get_by_role('button',name='Sign in',exact=True).click()
 expect(page.locator('#home')).to_be_visible()
 expect(page.get_by_role('button',name='Settings',exact=True)).to_have_count(0)
