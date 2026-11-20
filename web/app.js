'use strict';
const $=id=>document.getElementById(id);
let nextMember='',csrf='',handles=[],devices=[],active=null,polling=false,screen='prepare',selectedDevices={},automaticMode=false,queueBusy=false,homeStamp='',homePlans=[],deleteBusy=false,handoutStamp='',deviceStamp='',ending=null,deviceActionBusy=false;
let handoutPhrases=null;
const slots=[{product:'ghost',callsign:'STONEY',lead:true,profile:'any'},{product:'ghost',callsign:'BETTY',lead:false,profile:'any'},{product:'drop',callsign:'gh05t-we4zR',lead:false,profile:'headless'}];
function node(tag,text='',cls=''){const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;}
function error(e){$('alert').textContent=e.message||String(e);}
async function api(path,data,contentType='application/json'){const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':contentType,'X-CSRF-Token':csrf},body:contentType==='application/json'?JSON.stringify(data):data});let obj;try{obj=await r.json();}catch{throw Error('The application is temporarily unavailable. Try again.');}if(!r.ok){if(r.status===401)showLogin();throw Error(obj.detail||'Request failed');}return obj;}
function showLogin(){$('addUserForm').reset();$('accountList').replaceChildren();$('addUserStatus').textContent='';$('settingsNav').hidden=true;for(const id of ['home','prepare','teams','intelligence','equipment','settings','nav'])$(id).hidden=true;$('login').hidden=false;csrf='';automaticMode=false;}
function show(id){if(id!=='settings')$('addUserForm').reset();screen=id;sessionStorage.setItem('wzl_screen',id);for(const key of ['home','prepare','teams','intel','equipment','settings'])$(key+'Nav').classList.toggle('selected',key===id||(key==='intel'&&id==='intelligence'));for(const s of ['home','prepare','teams','intelligence','equipment','settings'])$(s).hidden=s!==id;$('login').hidden=true;$('nav').hidden=false;$('alert').textContent='';}
function options(select,values,current){for(const [value,label]of values){const o=node('option',label);o.value=value;o.selected=value===current;select.append(o);}}
function button(label,action,cls=''){const b=node('button',label,cls);b.type='button';b.onclick=action;return b;}
function saveDraft(){sessionStorage.setItem('wzl_team_draft',JSON.stringify({name:$('teamName').value,slots}));}
function renderSlots(){
 $('slots').replaceChildren();slots.forEach((s,i)=>{
  s.profile=s.product==='drop'?'headless':'any';const row=node('div','','slot');
  const type=node('label','Device'),select=node('select');select.setAttribute('aria-label','Device type '+(i+1));options(select,[['ghost','Ghost'],['drop','Drop']],s.product);select.onchange=()=>{s.product=select.value;if(s.product==='drop')s.lead=false;ensureLead();renderSlots();};type.append(select);row.append(type);
  const name=node('label','Codename'),call=node('select');call.setAttribute('aria-label','Codename '+(i+1));options(call,[...new Set([...handles,s.callsign])].map(x=>[x,x]),s.callsign);call.onchange=()=>{s.callsign=call.value;saveDraft();};name.append(call);row.append(name);
  if(s.product==='ghost'){const lead=node('label','Team lead'),radio=document.createElement('input');radio.type='radio';radio.name='lead';radio.checked=s.lead;radio.onchange=()=>{slots.forEach(x=>x.lead=false);s.lead=true;renderSlots();};lead.prepend(radio);row.append(lead);}else row.append(node('span','Area intelligence','note'));
  const remove=button('×',()=>{slots.splice(i,1);ensureLead();renderSlots();});remove.setAttribute('aria-label','Remove member '+(i+1));row.append(remove);$('slots').append(row);
 });$('addMember').disabled=slots.length>=5;$('ghostCount').value=String(slots.filter(x=>x.product==='ghost').length);$('dropCount').value=String(slots.filter(x=>x.product==='drop').length);saveDraft();
}
function ensureLead(){if(!slots.some(x=>x.lead&&x.product==='ghost')){const g=slots.find(x=>x.product==='ghost');if(g)g.lead=true;}}
function setCounts(){const ghosts=Number($('ghostCount').value),drops=Number($('dropCount').value);if(ghosts+drops>5){error(Error('A team has up to five devices. Reduce one count first.'));renderSlots();return;}const used=[];const next=[];for(const [type,count]of [['ghost',ghosts],['drop',drops]])for(let i=0;i<count;i++){const old=slots.filter(s=>s.product===type)[i];const name=old&&!used.includes(old.callsign)?old.callsign:handles.find(n=>!used.includes(n));used.push(name);next.push(old?{...old,callsign:name}:{product:type,callsign:name,lead:false,profile:'any'});}slots.splice(0,slots.length,...next);ensureLead();$('alert').textContent='';renderSlots();}
function compatible(m,d){return d.compatible&&!d.busy&&m.product===d.product&&(!m.profile||m.profile==='any'||m.profile===d.profile)&&(!m.binding||m.binding.mac===d.mac)&&!active.members.some(x=>x.id!==m.id&&x.binding&&x.binding.mac===d.mac);}
function deviceLabel(d){return (d.label||'Device')+' · '+(d.product==='drop'?'Drop':d.product==='ghost'?(d.profile==='xl'?'Ghost XL':'Ghost'):'Unidentified device');}
function typeLabel(m){const profile=m.binding?.profile||m.profile;return m.product==='drop'?'Drop':profile==='xl'?'Ghost XL':'Ghost';}
async function identify(d){try{const cue=await api('devices/identify',{device:d.mac});$('alert').textContent=cue.label+': '+cue.cue;}catch(e){error(e);}}
function identifyButton(d){const b=button('Identify',()=>identify(d));b.disabled=d.busy||!d.compatible;return b;}
async function clearDevice(d){if(!confirm('Clear '+deviceLabel(d)+'? Its local team and recordings will be removed. Firmware stays installed.'))return;deviceActionBusy=true;automaticMode=false;try{await api('devices/unassign',{device:d.mac,operation:crypto.randomUUID().replaceAll('-',''),confirm:'CLEAR LOCAL TEAM AND RECORDINGS'});$('alert').textContent='Device cleared and unassigned.';await refresh();}catch(e){error(e);}finally{deviceActionBusy=false;}}
function actions(d,menu=false){const wrap=node('div','','device-actions');const identify=identifyButton(d),clear=button('Clear device',()=>{closeContext();clearDevice(d);});clear.disabled=d.busy||!d.compatible||deviceActionBusy;if(menu){identify.setAttribute('role','menuitem');clear.setAttribute('role','menuitem');identify.onclick=()=>{closeContext();identifyDevice(d);};}wrap.append(identify,clear);return wrap;}
const identifyDevice=identify;
function closeContext(){$('deviceContext').hidden=true;}
function context(e,d){e.preventDefault();const menu=$('deviceContext');menu.replaceChildren(actions(d,true));menu.hidden=false;menu.style.left=Math.max(8,Math.min(e.clientX,innerWidth-230))+'px';menu.style.top=Math.max(8,Math.min(e.clientY,innerHeight-130))+'px';menu.querySelector('button').focus();}
function renderDevices(){const stamp=JSON.stringify(devices);if(stamp===deviceStamp)return;deviceStamp=stamp;$('devices').replaceChildren();for(const d of devices){const row=node('div','','device');row.dataset.mac=d.mac;row.tabIndex=0;row.append(node('strong',deviceLabel(d)));const assigned=active?.members.find(m=>m.binding?.mac===d.mac);let status=d.message||(d.busy?d.progress?.phase||'Preparing…':assigned?.status==='ready'?'Ready · safe to unplug':'Available');row.append(node('p',status,d.compatible?'note':'error'),actions(d));row.oncontextmenu=e=>context(e,d);row.onkeydown=e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))context({preventDefault:()=>e.preventDefault(),clientX:row.getBoundingClientRect().left,clientY:row.getBoundingClientRect().top},d);};$('devices').append(row);}$('deviceNote').textContent=devices.length?devices.length+' connected. One cable is enough.':'Connect a Ghost or Drop. Ready devices can leave immediately.';}
function showSteps(n){['stepPlan','stepPrepare','stepField'].forEach((id,i)=>{const el=$(id);el.classList.toggle('current',i===n);if(i===n)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});}
function progressNode(m,d){const bar=node('progress');bar.setAttribute('aria-label','Preparation progress for '+m.callsign);const p=d?.progress;if(p?.total){bar.max=p.total;bar.value=p.completed;}return bar;}
function renderHandouts(force=false){
 if(!active)return;const stamp=JSON.stringify([active,devices,automaticMode]);if(!force&&handoutStamp===stamp)return;handoutStamp=stamp;
 const ready=active.members.filter(m=>m.status==='ready').length,done=ready===active.members.length,busy=active.members.some(m=>['preparing','verifying'].includes(m.status));
 $('planForm').hidden=true;$('handouts').hidden=false;$('journeyTitle').textContent=active.name;$('journeyIntro').textContent=done?'Your team is prepared. Hand out the gear, place the Drops, and go.':'Automatic preparation includes clearing old gig state. Unplug each Ready device and connect the next.';showSteps(done?2:1);
 $('phaseTitle').textContent=done?active.name+' is ready':'Prepare & hand out';$('progress').textContent=ready+' / '+active.members.length+' ready to hand out';$('overallProgress').max=active.members.length;$('overallProgress').value=ready;
 const waiting=active.members.find(m=>m.status==='waiting'&&m.id===nextMember)||active.members.find(m=>m.status==='waiting');$('nextInstruction').textContent=done?'No final sync is needed. Earlier members can already be in the field.':busy?'Preparing automatically. Hand out any device already marked Ready.':waiting?'Next: connect a '+typeLabel(waiting)+' for '+waiting.callsign+'.':'Review the device below to continue.';
 $('resumeBox').hidden=done||automaticMode||busy;$('another').disabled=busy||queueBusy;$('endCurrent').disabled=busy||queueBusy;
 $('memberProgress').replaceChildren();const pending=active.members.filter(m=>m.status==='waiting');if(pending.length>1&&!busy){const label=node('label','Who gets the next matching device?'),sel=node('select');sel.setAttribute('aria-label','Next member');options(sel,pending.map(m=>[m.id,m.callsign+' · '+typeLabel(m)]),waiting?.id);sel.onchange=()=>{nextMember=sel.value;};label.append(sel);$('memberProgress').append(label);}for(const m of active.members){const row=node('div','','handout');row.dataset.member=m.id;const d=devices.find(d=>d.mac===m.binding?.mac);const heading=node('strong',m.callsign,'member-heading');if(m.lead)heading.append(leadBadge());row.append(heading,node('span',typeLabel(m),'badge'));
  if(m.status==='ready'){row.append(node('p',d?'Ready — safe to unplug.':'Ready — handed out / disconnected.','success'),node('small',m.product==='drop'?'Place it, then press once to arm. Four quick amber flashes confirm.':'Hand it out. Its full planned team is already installed.'));}
  else if(['preparing','verifying'].includes(m.status)){row.append(node('p',d?.progress?.phase||'Preparing and verifying…'),progressNode(m,d));row.append(button('Cancel preparation',async()=>{try{const r=await api('teams/'+active.id+'/cancel/'+m.id,{});$('alert').textContent=r.message;}catch(e){error(e);}}));}
  else if(['reissued','released','lost_state'].includes(m.status)){row.append(node('p','This assignment is no longer usable. Start a fresh team to issue new credentials.','note'));}
  else {if(m.error)row.append(node('p',m.error,'error'));const candidates=devices.filter(d=>compatible(m,d));if(m.status==='error'){const retry=button('Retry '+m.callsign,()=>prepareMember(m,candidates[0]),'primary');retry.disabled=!candidates.length||busy;row.append(retry);}
   else if(candidates.length>1){row.append(node('p','Queued — a matching device will be assigned automatically.','note'));}
   else row.append(node('p',candidates.length?(busy?'Queued — starts automatically after this device.':automaticMode?'Queued — preparing automatically.':'Waiting for you to continue preparation.'):'Waiting for a '+typeLabel(m)+'. Use the same cable as the last device.','note'));
  }$('memberProgress').append(row);
 }
 $('memberProgress').classList.toggle('complete',done);$('fieldGuide').hidden=!done;if(done)renderFieldGuide();deviceStamp='';renderDevices();
}
async function prepareMember(m,d){if(!d||queueBusy||deviceActionBusy)return;queueBusy=true;try{active=await api('teams/'+active.id+'/prepare/'+m.id,{device:d.mac});renderHandouts();}catch(e){automaticMode=false;error(e);}finally{queueBusy=false;}}
async function autoQueue(){if(screen!=='prepare'||!automaticMode||queueBusy||deviceActionBusy||!active||!csrf||active.members.some(m=>['preparing','verifying'].includes(m.status)))return;const waiting=active.members.filter(m=>m.status==='waiting');const m=waiting.find(m=>m.id===nextMember&&devices.some(d=>compatible(m,d)))||waiting.find(m=>devices.some(d=>compatible(m,d)));if(m)await prepareMember(m,devices.find(d=>compatible(m,d)));}
function renderFieldGuide(){const panel=$('fieldGuide');panel.replaceChildren(node('h2','Head into the field'),node('p','Setup is complete. These optional checks help you confirm the physical handout and communications. They never send radio messages from the app.','note'));const checks=active.journey?.checks||{};const rows=[['names','Ghosts show their assigned names','Check the names on their screens.'],['armed','Drops are placed and armed','One short press: four quick amber flashes. Double press disarms: two long flashes.'],['drop','Ghosts received a Drop briefing','On each Ghost: GHOST DROP → CHECK-IN → select the Drop → SEND. A report is a clue, not proof of a threat.'],['buddy','Buddy message received','TEAM → Send Message → choose teammate and message → confirm SEND.']];for(const [id,title,hint]of rows){if((id==='armed'||id==='drop')&&!active.members.some(m=>m.product==='drop'))continue;if(id==='buddy'&&active.members.filter(m=>m.product==='ghost').length<2)continue;const label=node('label','','field-check'),input=document.createElement('input');input.type='checkbox';input.checked=!!checks[id];input.onchange=async()=>{const next={...active.journey?.checks,[id]:input.checked};try{active=await api('teams/'+active.id+'/journey',{checks:next});}catch(e){input.checked=!input.checked;error(e);}};label.append(input,node('strong',title),node('small',hint));panel.append(label);}panel.append(node('p','Checks are your observations. Unchecked means not yet confirmed. You can head out now.','note'),button('Bring back intelligence',()=>loadIntelligence()));}
async function refresh(){if(polling||!csrf||document.hidden)return;polling=true;try{devices=await api('devices');renderDevices();if(screen==='equipment')await refreshEquipment();if(screen==='home'){homePlans=await api('teams');renderHome();}if(active){active=await api('teams/'+active.id);if(screen==='prepare'){renderHandouts();await autoQueue();}}}catch(e){error(e);}finally{polling=false;}}
function newTeam(){if(active)handoutPhrases=null;active=null;nextMember='';automaticMode=false;handoutStamp='';selectedDevices={};sessionStorage.removeItem('wzl_active_team');show('prepare');$('planForm').hidden=false;$('handouts').hidden=true;$('consent').checked=false;$('journeyTitle').textContent='Build your team.';$('journeyIntro').textContent='Plan up to five devices. Prepare and hand out each one using a single cable.';showSteps(0);renderSlots();}
async function openTeam(p){active=p;automaticMode=false;sessionStorage.setItem('wzl_active_team',p.id);show('prepare');renderHandouts(true);await refresh();}
function leadBadge(){const badge=node('span','','lead-badge');const image=document.createElement('img');image.src='/static/assets/lead-shield.svg';image.alt='Team lead';image.width=18;image.height=20;badge.append(image);badge.title='Team lead';return badge;}
function memberIcon(m){const wrap=node('div','','member-art');const key=String(m.callsign||'').trim().toLowerCase();const path=m.product==='drop'?'/static/assets/ghostdrop.png':['stoney','crawl','link','betty','nugget'].includes(key)?'/static/assets/handles/'+key+'.png':null;if(path){const img=document.createElement('img');img.src=path;img.alt=m.callsign+' · '+typeLabel(m);img.width=88;img.height=88;wrap.append(img);}else wrap.append(node('span',String(m.callsign||'?').slice(0,2),'avatar-fallback'));if(m.lead)wrap.append(leadBadge());return wrap;}
function memberState(m){return {ready:'Prepared',waiting:'Not issued',preparing:'Preparing',verifying:'Verifying',error:'Needs attention',reissued:'Reassigned',released:'Cleared',lost_state:'Needs reissue'}[m.status]||'Not verified';}
function currentTeam(p){return !['archived','deleted'].includes(p.state)&&p.members.some(m=>['ready','waiting','preparing','verifying','error'].includes(m.status));}
function teamCard(p){const card=node('article','','dashboard-team');card.dataset.team=p.id;const prepared=p.members.filter(m=>m.status==='ready').length;const busy=p.members.some(m=>['preparing','verifying'].includes(m.status));const resumable=p.members.some(m=>['waiting','preparing','verifying','error'].includes(m.status));const header=node('div','','team-card-heading');header.append(node('h3',p.name),node('span',prepared===p.members.length?'Prepared':busy?'Preparing':resumable?'Setup pending':prepared?'Partly reassigned':'Previous team','team-state'));card.append(header);const members=node('div','','team-members');for(const m of p.members){const tile=node('div','','member-tile');tile.append(memberIcon(m),node('strong',m.callsign),node('span',typeLabel(m),'member-type'),node('small',memberState(m),m.status==='ready'?'success':'note'));if(m.verified_at)tile.title='Configuration verified '+new Date(m.verified_at*1000).toLocaleString();members.append(tile);}card.append(members);const foot=node('div','','team-card-footer');foot.append(node('span',prepared+' / '+p.members.length+' devices prepared','note'));const controls=node('div','','card-actions');controls.append(button(resumable?'Continue setup':'Open team',()=>openTeam(p),'primary'),button('Delete team',()=>endTeam(p),'delete-link'));foot.append(controls);card.append(foot);return card;}
function renderHome(){const plans=homePlans.filter(currentTeam);const stamp=JSON.stringify([plans,devices.map(d=>[d.mac,d.compatible,d.busy])]);if(stamp===homeStamp)return;homeStamp=stamp;const ready=new Set(plans.flatMap(p=>p.members.filter(m=>m.status==='ready'&&m.binding).map(m=>m.binding.mac)));$('homeStats').replaceChildren();for(const [value,label]of [[plans.length,'Active teams'],[ready.size,'Assigned devices'],[devices.length,'Connected by USB']]){const stat=node('div','','stat');stat.append(node('strong',String(value)),node('span',label));$('homeStats').append(stat);}$('homeTeams').replaceChildren(...plans.sort((a,b)=>(b.created||0)-(a.created||0)).map(teamCard));$('homeEmpty').hidden=plans.length!==0;$('homeConnection').textContent='Prepared means the saved team configuration was verified. Radio contact and field checks happen deliberately on your Ghosts.';}
async function loadHome(){automaticMode=false;show('home');try{[homePlans,devices]=await Promise.all([api('teams'),api('devices')]);homeStamp='';renderHome();}catch(e){error(e);}}
async function endTeam(p){automaticMode=false;ending=p;$('deleteTitle').textContent='Delete '+p.name+'?';$('deleteDescription').textContent='You are removing '+p.name+' and its '+p.members.length+' member assignments from your active fleet.';$('deleteName').value='';$('deleteName').placeholder=p.name;$('deleteConfirm').disabled=true;$('deleteError').textContent='';$('deleteTeamDialog').showModal();$('deleteName').focus();}
$('deleteName').oninput=()=>{$('deleteConfirm').disabled=deleteBusy||$('deleteName').value!==ending?.name;};
$('deleteCancel').onclick=()=>{if(!deleteBusy)$('deleteTeamDialog').close();};$('deleteTeamDialog').addEventListener('cancel',e=>{if(deleteBusy)e.preventDefault();});
$('deleteTeamForm').onsubmit=async e=>{e.preventDefault();if(deleteBusy||$('deleteName').value!==ending?.name)return;deleteBusy=true;$('deleteConfirm').disabled=true;$('deleteCancel').disabled=true;try{await api('teams/'+ending.id+'/delete',{confirm:'REMOVE TEAM FROM LIST',team_name:$('deleteName').value});if(active?.id===ending.id){active=null;sessionStorage.removeItem('wzl_active_team');}const name=ending.name;$('deleteTeamDialog').close();ending=null;await loadHome();$('alert').textContent=name+' deleted. Prepare a new team whenever you are ready.';}catch(e){$('deleteError').textContent=e.message;}finally{deleteBusy=false;$('deleteCancel').disabled=false;$('deleteConfirm').disabled=$('deleteName').value!==ending?.name;}};
async function loadTeams(){automaticMode=false;show('teams');devices=await api('devices');optionsOffline();const plans=await api('teams');function draw(){const query=$('teamSearch').value.toLowerCase();$('teamList').replaceChildren();for(const p of plans.filter(p=>(p.state!=='archived'||$('showArchived').checked)&&p.name.toLowerCase().includes(query))){const row=teamCard(p);if(p.state==='archived')row.prepend(node('p','Archived','note'));$('teamList').append(row);}if(!$('teamList').children.length)$('teamList').append(node('p','No active teams. Prepare one when your gear is ready.'));}draw();$('teamSearch').oninput=draw;$('showArchived').onchange=draw;}
function clearOperatorDraft(){
 for(const key of Object.keys(sessionStorage))if(key.startsWith('wzl_'))sessionStorage.removeItem(key);
}
function renderAccounts(users){
 $('accountList').replaceChildren(...users.map(user=>{
  const row=node('li');row.append(node('strong',user.username),node('span',user.role==='admin'?'Administrator':'Operator'));return row;
 }));
}
async function openSettings(){
 show('settings');$('addUserStatus').textContent='';
 try{renderAccounts(await api('settings/users'));}catch(e){error(e);}
}
$('settingsNav').onclick=openSettings;
$('addUserForm').onsubmit=async event=>{
 event.preventDefault();const submit=$('addUser'),status=$('addUserStatus');
 submit.disabled=true;status.textContent='';
 try{
  const user=await api('settings/users',{username:$('newUsername').value.trim(),password:$('newPassword').value,role:$('newRole').value});
  event.target.reset();status.textContent=user.username+' can now sign in.';
  renderAccounts(await api('settings/users'));
 }catch(e){status.textContent=e.message;}finally{submit.disabled=false;}
};
$('loginForm').onsubmit=async e=>{e.preventDefault();const form=new FormData(e.target);try{const r=await api('login',{username:form.get('username'),password:form.get('password')});csrf=r.csrf;e.target.reset();clearOperatorDraft();location.replace('/');}catch(err){error(err);}};
$('planForm').onsubmit=async e=>{e.preventDefault();$('start').disabled=true;try{if(sessionStorage.getItem('wzl_draft_book')&&!handoutPhrases)throw Error('Reopen the handout and save your codebook before preparing.');const body={name:$('teamName').value.trim(),members:slots,...(handoutPhrases?{phrases:handoutPhrases}:{})};const encoded=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(body))))).join('.');let pending;try{pending=JSON.parse(sessionStorage.getItem('wzl_pending_plan'));}catch{}if(!pending||pending.body!==encoded){pending={body:encoded,id:crypto.randomUUID().replaceAll('-','')};sessionStorage.setItem('wzl_pending_plan',JSON.stringify(pending));}active=await api('teams',{...body,request_id:pending.id});sessionStorage.removeItem('wzl_pending_plan');sessionStorage.removeItem('wzl_team_draft');sessionStorage.removeItem('wzl_draft_book');sessionStorage.setItem('wzl_active_team',active.id);automaticMode=true;renderHandouts(true);await autoQueue();}catch(err){error(err);}finally{$('start').disabled=false;}};
$('addMember').onclick=()=>{if(slots.length<5){slots.push({product:'ghost',callsign:handles.find(x=>!slots.some(s=>s.callsign===x)),lead:false,profile:'any'});renderSlots();}};
$('ghostCount').onchange=setCounts;$('dropCount').onchange=setCounts;$('teamName').oninput=saveDraft;
$('homeNew').onclick=newTeam;$('emptyNew').onclick=newTeam;$('backHome').onclick=()=>loadHome();$('homeNav').onclick=()=>loadHome();document.querySelector('.brand').onclick=e=>{if(csrf){e.preventDefault();loadHome();}};$('another').onclick=newTeam;$('newFromTeams').onclick=newTeam;$('endCurrent').onclick=()=>endTeam(active);
$('resumeAuto').onclick=()=>{automaticMode=true;renderHandouts(true);autoQueue();};
$('prepareNav').onclick=()=>{if(!active){newTeam();return;}show('prepare');renderHandouts(true);};$('teamsNav').onclick=()=>loadTeams().catch(error);$('logout').onclick=async()=>{try{await api('logout',{});}finally{clearOperatorDraft();showLogin();location.replace('/');}};
document.addEventListener('click',e=>{if(!$('deviceContext').contains(e.target))closeContext();});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeContext();});window.addEventListener('resize',closeContext);
async function boot(){try{const s=await api('session');csrf=s.csrf;if(sessionStorage.getItem('wzl_owner')&&sessionStorage.getItem('wzl_owner')!==s.username)clearOperatorDraft();sessionStorage.setItem('wzl_owner',s.username);$('settingsNav').hidden=s.role!=='admin';handles=s.callsigns;handoutPhrases=s.handout_draft?.id===sessionStorage.getItem('wzl_draft_book')?s.handout_draft.phrases:null;try{const draft=JSON.parse(sessionStorage.getItem('wzl_team_draft'));if(draft&&Array.isArray(draft.slots)&&draft.slots.length<=5){slots.splice(0,slots.length,...draft.slots);$('teamName').value=draft.name||'';}}catch{}const previousScreen=sessionStorage.getItem('wzl_screen');renderSlots();showSteps(0);const id=sessionStorage.getItem('wzl_active_team');if(id){try{active=await api('teams/'+id);if(!['archived','deleted'].includes(active.state))renderHandouts(true);else active=null;}catch{sessionStorage.removeItem('wzl_active_team');}}if(previousScreen==='settings'&&s.role==='admin'){await openSettings();}else if(previousScreen==='equipment'){await openEquipment();}else if(previousScreen==='prepare'&&(active||sessionStorage.getItem('wzl_team_draft'))){show('prepare');if(!active)newTeam();await refresh();}else await loadHome();}catch{showLogin();}}
fetch('/api/health').then(r=>r.json()).then(r=>$('build').textContent=r.build).catch(()=>{});boot();setInterval(refresh,1000);
const reviewStates={unreviewed:'Needs review',watch:'Watching',reviewed:'Reviewed',expected:'Expected'};
let intelTeam='';
const lanes=['Changed since review','Needs first review','Watching','Reviewed / expected'];
function reviewLane(f){
 if(f.disposition==='watch')return 2;
 if(f.disposition!=='unreviewed')return 3;
 return f.reopened && (f.review_baseline || ['watch','expected','reviewed'].includes(f.previous_disposition))?0:1;
}
function findingMetric(label,start,end,marker=null){
 const metric=node('span','','finding-metric');
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('viewBox','0 0 100 8');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
 for(const [left,right,color] of [[0,100,'#393841'],[start,end,'currentColor']]){
  const bar=document.createElementNS(svg.namespaceURI,'rect');
  bar.setAttribute('x',Math.min(99,left));bar.setAttribute('y',2);bar.setAttribute('height',4);
  bar.setAttribute('width',Math.max(1,right-left));bar.setAttribute('fill',color);svg.append(bar);
 }
 if(marker!==null){
  const tick=document.createElementNS(svg.namespaceURI,'rect');
  for(const [key,value] of Object.entries({x:Math.max(0,Math.min(98,marker-1)),y:0,width:2,height:8,fill:'white'}))tick.setAttribute(key,value);
  svg.append(tick);
 }
 metric.append(node('small',label),svg);return metric;
}
async function loadIntelligence(){
 show('intelligence');const content=$('intelligenceContent');content.replaceChildren(node('p','Reading saved briefings…'));
 try{
  const [data,plans,catalog]=await Promise.all([api('intelligence'),api('teams'),fetch('/static/assets/intel-review/catalog.json').then(r=>r.json())]);content.replaceChildren();
  const choices=[];for(const p of plans.filter(p=>p.state!=='archived'))for(const m of p.members)if(m.product==='ghost'&&m.status==='ready'&&m.binding)choices.push({plan:p,member:m});
  const panel=node('div','','panel');panel.append(node('h2','Import from a Ghost'),node('p','Connect a prepared Ghost by USB to read its saved briefings and field decisions.'));
  const select=node('select');select.setAttribute('aria-label','Ghost briefings');options(select,choices.map((x,i)=>[String(i),x.member.callsign+' · '+x.plan.name]),'0');const btn=node('button','Import briefings','primary');btn.disabled=!choices.length;btn.onclick=async()=>{btn.disabled=true;try{const c=choices[Number(select.value)];const r=await api('intelligence/import',{team:c.plan.id,member:c.member.id});await loadIntelligence();$('alert').textContent=r.reports.length+' signed briefings imported. These are saved observations, not current presence.';}catch(e){error(e);btn.disabled=false;}};panel.append(select,btn);content.append(panel);
  const teams=new Map(plans.map(p=>[p.id,p]));
  const teamNames=new Map(data.findings.map(f=>[f.team_id,f.team_name]));
  function sourceLabel(record){
   const team=teams.get(record.team_id);
   const source=team?.members.find(m=>String(m.id)===String(record.source_id));
   return [team?.name||teamNames.get(record.team_id),source?.callsign||('Drop …'+String(record.source_id).slice(-4))].filter(Boolean).join(' · ');
  }
  const queue=node('section','','intel-queue');
  const teamFilter=node('select');teamFilter.setAttribute('aria-label','Filter findings by team');
  if(!teamNames.has(intelTeam))intelTeam='';
  options(teamFilter,[['','All teams'],...[...teamNames.entries()].sort((a,b)=>a[1].localeCompare(b[1]))],intelTeam);
  teamFilter.onchange=()=>{intelTeam=teamFilter.value;loadIntelligence();};
  const scoped=data.findings.filter(f=>!intelTeam||f.team_id===intelTeam);
  const unreviewed=scoped.filter(f=>f.disposition==='unreviewed').length;
  queue.append(node('h2','Triage queue'),teamFilter,node('p',scoped.length+' total · '+unreviewed+' awaiting review','note'));
  if(data.findings.length)queue.append(node('p','A radio signature alone cannot establish a person, exact device model, or intent.','note'));
  else queue.append(node('p','Imported findings will appear here.'));
  content.prepend(queue);
  const ordered=scoped.sort((a,b)=>reviewLane(a)-reviewLane(b) || Number(b.interpretation_supported)-Number(a.interpretation_supported) || b.priority-a.priority || b.imported_at-a.imported_at);
  const peaks=ordered.flatMap(f=>[f.max_rssi,f.review_baseline?.max_rssi??f.max_rssi]);
  const floor=Math.min(-100,...ordered.map(f=>f.min_rssi),...peaks),ceiling=Math.max(-20,...peaks);
  const peak=Math.max(1,...ordered.map(f=>f.observations));
  const level=value=>100*(value-floor)/(ceiling-floor);
  function findingCard(f){
   const card=node('details','','intel-card'),summary=node('summary');
   const title=f.rule==='BLE-FINDMY-FRAME-1'?'Find My Bluetooth frame':f.rule;
   const identity=node('span','','intel-identity');
   identity.append(node('strong',title),node('small',sourceLabel(f)));
   const samples=f.observations+' sample'+(f.observations===1?'':'s');
   const signal=(f.min_rssi===f.max_rssi?f.min_rssi:f.min_rssi+' to '+f.max_rssi)+' dBm';
   const lane=reviewLane(f),base=f.review_baseline;
   const comparable=lane===0 && base && base.rule===f.rule && base.radio===f.radio;
   const delta=comparable?f.max_rssi-base.max_rssi:null;
   let reason=lane===0?'Previously '+(base?.disposition||f.previous_disposition):lane===1?'Awaiting an operator decision':reviewStates[f.disposition];
   if(comparable)reason+=' · '+(delta===0?'Peak unchanged':'Peak '+(delta>0?'rose ':'fell ')+Math.abs(delta)+' dB');
   else if(lane===1 && f.rule.includes('-COR-'))reason+=' · Corroborated signature';
   identity.append(node('small',reason,'triage-reason'));
   summary.append(identity,findingMetric(samples,0,100*f.observations/peak),findingMetric(signal,level(f.min_rssi),level(f.max_rssi),comparable?level(base.max_rssi):null),node('span','Priority '+f.priority,'intel-state'));
   card.dataset.lane=lane;
   if(f.synthetic)identity.append(node('small','Synthetic test evidence','danger-text'));
   card.append(summary);
   const detail=node('div','','intel-detail');
   detail.append(node('p','Imported '+new Date(f.imported_at*1000).toLocaleString()+(comparable?' · Reviewed peak '+base.max_rssi+' dBm at revision '+base.revision:''),'note'),node('p',f.rule+' · Channel '+f.channel+' · Raw evidence '+f.evidence_availability.toLowerCase().replaceAll('_',' ')),
    node('p','Source '+f.source_id+' · Event '+f.event_id+' · Revision '+f.revision,'note'));
   const label=node('label','Review note'),note=node('textarea');note.rows=2;note.maxLength=2000;note.value=f.operator_note||'';label.append(note);detail.append(label);
   const actions=node('div','','intel-actions');
   for(const [action,text] of [['reviewed','Mark reviewed'],['expected','Mark expected'],['watch','Watch'],['unreviewed','Reopen']]){
    actions.append(button(text,async()=>{try{await api('intelligence/review',{id:f.id,revision:f.revision,disposition:action,note:note.value});await loadIntelligence();}catch(e){error(e);}}));
   }
   detail.append(actions);card.append(detail);return card;
  }
  {
   const families=new Map();
   for(const f of ordered){
    const known=catalog.findIndex(g=>g.rules.includes(f.rule)),index=known<0?24:known;
    if(!families.has(index))families.set(index,[]);
    families.get(index).push(f);
   }
   const grid=node('div','','finding-families');
   const result=node('section','','finding-result'),heading=node('h3');heading.tabIndex=-1;
   if(ordered.length)queue.append(node('p','Choose a family to compare its findings. Brighter cells mean more findings in that review state.','note'),grid);
   queue.insertBefore(result,grid.parentNode===queue?grid.previousSibling:null);
   function selectFamily(index,state,focus=true){
    const family=index<0?ordered:(families.get(index)||[]),items=state?family.filter(f=>f.disposition===state):family;
    heading.textContent=[catalog[index]?.name||'All findings',reviewStates[state],String(items.length)].filter(Boolean).join(' · ');
    const reset=button('Show all findings',()=>selectFamily(-1,null));
    result.replaceChildren(heading);
    if(index>=0)result.append(reset);
    const renderLanes=(list)=>{
     buckets.replaceChildren();
     lanes.forEach((title,i)=>{
      const matches=list.filter(f=>reviewLane(f)===i),section=node('details','','triage-lane');
      section.dataset.lane=i;section.open=matches.length>0 && (i<3 || !!state);
      const label=node('summary');label.append(node('strong',String(matches.length)),node('span',title));section.append(label);
      let shown=0;
      function nextPage(){
       more.remove();
       const batch=matches.slice(shown,shown+10);shown+=batch.length;
       section.append(...batch.map(findingCard));
       if(shown<matches.length){more.textContent='Show more ('+(matches.length-shown)+' remaining)';section.append(more);}
      }
      const more=button('',nextPage);
      if(matches.length)nextPage();else section.append(node('p','No findings in this group.','note'));
      buckets.append(section);
     });
    };
    const buckets=node('div','','triage-buckets');
    result.append(node('p','Signal scale '+floor+' to '+ceiling+' dBm · White tick marks the previously reviewed peak.','note'));
    const sources=new Map();
    for(const f of items){
     const group=[f.team_id,f.source_id,f.radio,catalog.findIndex(g=>g.rules.includes(f.rule))].join('/');
     if(!sources.has(group))sources.set(group,[]);
     sources.get(group).push(f);
    }
    const sort=node('select');sort.setAttribute('aria-label','Compare signal strength');
    options(sort,[['','Review priority'],...[...sources].filter(([,fs])=>fs.length>1).map(([k,fs])=>[k,'Strongest received · '+sourceLabel(fs[0])+' · '+(catalog.find(g=>g.rules.includes(fs[0].rule))?.name||fs[0].rule)+' · radio '+fs[0].radio])],'');
    sort.onchange=()=>renderLanes(sort.value?[...sources.get(sort.value)].sort((a,b)=>b.max_rssi-a.max_rssi):items);
    if(sort.options.length>1)result.append(sort);
    result.append(buckets);renderLanes(items);
    if(focus)heading.focus();
   }
   const counts=[...families.values()].flatMap(fs=>Object.keys(reviewStates).map(k=>fs.filter(f=>f.disposition===k).length));
   const hottest=Math.max(1,...counts);
   for(const [index,fs] of families){
    const tile=node('article','','family-tile'),pick=button('',()=>selectFamily(index,null),'family-pick');
    pick.append(node('span','','family-art art-'+index),node('strong',catalog[index].name),node('small',fs.length+' finding'+(fs.length===1?'':'s')));
    const heat=node('div','','review-heat');
    for(const [key,title] of Object.entries(reviewStates)){
     const n=fs.filter(f=>f.disposition===key).length;
     const cell=button('',()=>selectFamily(index,key),'heat-cell '+key);
     cell.dataset.heat=String(Math.ceil(n/hottest*3));cell.disabled=!n;
     cell.setAttribute('aria-label',catalog[index].name+' · '+title+' · '+n);
     cell.append(node('strong',String(n)),node('small',title));heat.append(cell);
    }
    tile.append(pick,heat);grid.append(tile);
   }
   const guide=node('details','','panel full-guide');
   const title=node('summary','Signature field guide');
   guide.append(title,node('p',catalog.length+' illustrated families · '+catalog.reduce((sum,g)=>sum+g.rules.length,0)+' firmware rules. Choose a family to see its signature rules and saved findings.','note'));
   const gallery=node('div','','guide-gallery');
   const ranked=catalog.map((family,index)=>({family,index,count:families.get(index)?.length||0}));
   ranked.sort((a,b)=>b.count-a.count || a.family.name.localeCompare(b.family.name));
   ranked.forEach(({family,index,count})=>{
    const pick=button('',()=>{
     selectFamily(index,null,false);
     const rules=node('p',family.rules.join(' · '),'guide-rules');
     heading.after(rules);
     if(!count)rules.after(node('p','No saved findings for this family.'));
     heading.focus({preventScroll:true});
     heading.scrollIntoView({block:'start',behavior:'instant'});
    },'family-pick');
    pick.append(node('span','','family-art art-'+index),node('strong',family.name),node('small',count+' saved finding'+(count===1?'':'s')));
    gallery.append(pick);
   });
   guide.append(gallery);queue.before(guide);
   selectFamily(-1,null,false);
  }
  const history=node('details','','panel intel-history');
  history.append(node('summary','Briefing history ('+data.briefings.length+')'));
  if(data.briefings.length)history.append(node('p','Times show when WeazlOps imported each snapshot. The source records device uptime. A snapshot with zero findings cannot establish that an area was clear.','note'));
  else history.append(node('p','No briefings imported yet.'));
  for(const b of [...data.briefings].sort((a,b)=>b.imported_at-a.imported_at)){
   const row=node('div','','intel-history-row');
   row.append(node('strong',sourceLabel(b)),node('span',b.card_count+' finding'+(b.card_count===1?'':'s')+' · '+b.coverage_gaps.toLocaleString()+' coverage gaps'),node('small','Imported '+new Date(b.imported_at*1000).toLocaleString()+' · Source '+b.source_id));
   history.append(row);
  }
  content.append(history);
  if(data.decisions.length){content.append(node('h2','Field decisions'));for(const d of data.decisions){const row=node('div','','teamrow');row.append(node('strong',d.callsign+' · '+d.action),node('p','Exact local observation '+d.identifier+' / revision '+d.observation_revision),node('p','Signed operator decision from this Ghost. Its local revision is not assumed to be a Drop finding revision; the two are kept separate.','note'));content.append(row);}}
  await appendRecordings(content,plans);
 }catch(e){error(e);content.replaceChildren(node('p','Saved intelligence could not be loaded. Try again.'));}
}
$('intelNav').onclick=()=>loadIntelligence();
async function appendRecordings(content,plans){
 const panel=node('div','','panel');panel.append(node('h2','Supporting recordings'),node('p','Optional deeper evidence. Preparing a new team never requires offloading old recordings.'));
 const choices=[];for(const p of plans.filter(p=>p.state!=='archived'))for(const m of p.members)if(m.product==='drop'&&m.binding&&m.status==='ready')choices.push({plan:p,member:m});
 const select=node('select');select.setAttribute('aria-label','Drop recordings');options(select,choices.map((c,i)=>[String(i),c.member.callsign+' · '+c.plan.name]),'0');const inspect=node('button','Inspect closed recordings');inspect.disabled=!choices.length;
 inspect.onclick=async()=>{inspect.disabled=true;try{const c=choices[Number(select.value)],files=await api('recordings/device',{team:c.plan.id,member:c.member.id});let list=node('div');if(!files.length)list.append(node('p','No recordings retained on this Drop. Its current field service can still be useful.'));for(const [i,f]of files.entries()){const row=node('div','','teamrow');row.append(node('strong','Recording '+(i+1)+' · '+Math.ceil(f.bytes/1024)+' KiB'),node('p',f.valid===f.bytes?'Stored segment; authentication checked during import.':'Incomplete segment; any readable content will be labeled.','note'));const read=node('button','Import and inspect');read.onclick=async()=>{read.disabled=true;try{const r=await api('recordings/import',{team:c.plan.id,member:c.member.id,segment:f.id});await showRecording(r.id);}catch(e){error(e);read.disabled=false;}};row.append(read);list.append(row);}panel.append(list);}catch(e){error(e);}finally{inspect.disabled=false;}};
 panel.append(select,inspect);const imported=await api('recordings');for(const r of imported){const row=node('div','','teamrow');row.append(node('strong','Imported recording · '+Math.ceil(r.bytes/1024)+' KiB'),node('p',r.sealed_footer?'Authenticated content · closed footer':'Authenticated content · missing closed footer','note'));const open=node('button','Open recording');open.onclick=()=>showRecording(r.id).catch(error);row.append(open);panel.append(row);}content.append(panel);
}
async function showRecording(id){const r=await api('recordings/'+id);show('intelligence');const content=$('intelligenceContent');content.replaceChildren(node('h2','Supporting recording'),node('p',r.sealed_footer?'Authenticated encrypted content, including a closed footer.':'Authenticated content; this recording has no closed footer. Its completeness is limited.'));const back=node('button','Back to intelligence');back.onclick=()=>loadIntelligence();content.append(back);const types={};for(const row of r.records)types[row.type]=(types[row.type]||0)+1;content.append(node('p',Object.entries(types).map(([k,v])=>k+': '+v).join(' · ')));const details=node('details');details.append(node('summary','Inspect source records (first 100)'));details.append(node('pre',JSON.stringify(r.records.slice(0,100),null,2)));content.append(details);}

function optionsOffline(){const s=$('offlineCreator');s.replaceChildren();options(s,devices.filter(d=>d.product==='ghost').map(d=>[d.mac,deviceLabel(d)]),'');$('offlinePreview').disabled=!s.children.length;}
$('offlinePreview').onclick=async()=>{const button=$('offlinePreview');button.disabled=true;try{const p=await api('offline/preview',{device:$('offlineCreator').value}),r=$('offlineReview');r.replaceChildren(node('h2',p.team.name),node('p',p.team.members.map(m=>m.callsign+(m.lead?' (lead)':'')).join(' · ')),node('p','Same authority and roster. Recovery custody transfers to this app after its durable save. No device is re-enrolled.'));const confirm=node('button','Import this team and transfer custody','primary');confirm.onclick=async()=>{confirm.disabled=true;try{const result=await api('offline/import',{preview:p.preview,confirm:'IMPORT SAME TEAM AND TRANSFER CUSTODY'});r.replaceChildren(node('p',result.message,result.lead_private_cleanup?'success':'note'));}catch(e){error(e);confirm.disabled=false;}};r.append(confirm);}catch(e){error(e);}finally{button.disabled=false;}};

let equipmentStamp = '';
const chosenRelease = new Map();
async function openEquipment(){
 automaticMode=false;
 show('equipment');
 equipmentStamp='';
 await refresh();
}
$('equipmentNav').onclick=openEquipment;
const modelNames={original:'WeazlGhost',xl:'WeazlGhost XL',headless:'GhostDrop'};
const releaseProducts={original:'weazlghost',xl:'weazlghost-xl',headless:'ghost-drop'};
const chipNames={esp32s3:'ESP32-S3',esp32c5:'ESP32-C5'};

function firmwareOptions(device,display,releases,opened){
 const details=node('details','','firmware-options');
 details.open=opened;
 details.dataset.device=device.mac;
 details.append(node('summary','Firmware options'));
 const controls=node('div','','flash-controls');
 const label=node('label','Firmware release');
 const select=node('select');
 options(select,[['','Choose a release'],...releases.map(r=>{
  const installed=device.firmware_version && r.running_versions?.[device.chip]===device.firmware_version;
  return [r.id,r.name+(installed?' (installed version)':'')];
 })],chosenRelease.get(device.mac)||'');
 select.disabled=device.busy;
 const flash=button('Flash firmware',async()=>{
  const release=releases.find(r=>r.id===select.value);
  if(!release)return;
  const same=device.firmware_version && release.running_versions?.[device.chip]===device.firmware_version;
  const prompt=(same?'Reinstall ':'Flash ')+release.name+' on '+display+'?';
  if(!confirm(prompt+'\nRunning firmware: '+(device.firmware_version||'unavailable')+'. Keep this device connected through verification.'))return;
  flash.disabled=true;
  try{await api('devices/flash',{device:device.mac,release:release.id,confirm:'FLASH SELECTED RELEASE'});}
  catch(e){error(e);}
  finally{equipmentStamp='';await refresh();}
 });
 flash.disabled=!select.value || device.busy;
 select.onchange=()=>{chosenRelease.set(device.mac,select.value);flash.disabled=!select.value || device.busy;};
 label.append(select);controls.append(label,flash);details.append(controls);
 return details;
}

function connectedCard(device,member,catalog,opened){
 const row=node('article','','usb-card');
 const display=member?.callsign||device.label||'Device';
 const liveModel=modelNames[device.profile];
 const facts=liveModel?device:member?.binding;
 const model=liveModel||modelNames[facts?.profile];
 const chip=chipNames[device.chip||facts?.chip];
 const hardware=[model,chip].filter(Boolean).join(' · ')||'USB device';
 const identity=node('div','','usb-identity');
 if(member)identity.append(memberIcon(member));
 const titles=node('div');
 titles.append(node('h2',display),node('p',(!liveModel && model?'Last assigned as ':'')+hardware));
 identity.append(titles);row.append(identity);
 const releases=catalog.releases.filter(r=>r.product===releaseProducts[device.profile] && r.targets[device.chip]);
 const job=catalog.jobs.find(j=>j.device===device.mac);
 const writing=job?.running;
 const version=writing?null:device.firmware_version;
 const firmware=node('div','','usb-version');
 firmware.append(node('span','Running firmware'),node('strong',version||(writing?'Updating…':'Unverified')));
 const recorded=member?.receipt?.firmware_version;
 if(version){
  const available=[...new Set(releases.map(r=>r.running_versions?.[device.chip]).filter(Boolean))];
  const matches=available.includes(version);
  const comparison=available.length?'In library: '+available.join(', '):'No matching release in library';
  firmware.append(node('small',matches?'Matches library release':comparison,matches?'version-match':''));
 }else if(!writing){
  if(recorded)firmware.append(node('small','Last verified: '+recorded));
  firmware.append(node('small',device.message||'Waiting for a version reply. Retrying automatically.'));
 }
 if(job)firmware.append(flashReceipt(job));
 row.append(firmware);
 if(device.compatible)row.append(identifyButton(device));
 if(device.compatible && releases.length)row.append(firmwareOptions(device,display,releases,opened));
 return row;
}

function flashReceipt(job){
 const parts=[job.stage];
 if(job.boot){
  const date=new Date(job.boot.verified_at*1000);
  parts.push(job.boot.version+' · uptime '+(job.boot.uptime_ms/1000).toFixed(1)+' s at '+date.toLocaleTimeString());
  if(typeof job.boot.auto_pocket_lock==='boolean')parts.push('Auto Pocket Lock was '+(job.boot.auto_pocket_lock?'on':'off')+' at verification');
 }
 return node('p',parts.join(' · '),'note');
}

async function refreshEquipment(){
 const [catalog,teams]=await Promise.all([api('firmware'),api('teams')]);
 if(screen!=='equipment')return;
 const members=new Map();
 for(const team of teams.filter(currentTeam)){
  for(const member of team.members){
   if(!member.binding || member.status!=='ready')continue;
   const previous=members.get(member.binding.mac);
   if(!previous || (member.verified_at||0)>(previous.verified_at||0))members.set(member.binding.mac,member);
  }
 }
 const stamp=JSON.stringify([devices.map(({checked_at,...device})=>device),catalog,[...members]]);
 if(stamp===equipmentStamp)return;
 equipmentStamp=stamp;
 const list=$('usbUnits');
 const opened=new Set([...list.querySelectorAll('details[open]')].map(d=>d.dataset.device));
 list.replaceChildren(...devices.map(d=>connectedCard(d,members.get(d.mac),catalog,opened.has(d.mac))));
 $('usbCount').textContent=devices.length+' connected by USB';
 if(!devices.length)list.append(node('p','Connect a Ghost or Drop by USB.'));
 renderFirmwareLibrary(catalog.releases);
 $('flashStatus').replaceChildren(...catalog.jobs.filter(j=>!devices.some(d=>d.mac===j.device)).map(j=>{
  const item=node('div');item.append(node('strong',members.get(j.device)?.callsign||j.label),flashReceipt(j));return item;
 }));
}

let libraryStamp = '';
function renderFirmwareLibrary(releases){
 const stamp=JSON.stringify(releases);
 if(stamp===libraryStamp)return;
 libraryStamp=stamp;
 const library=$('firmwareLibrary');
 library.replaceChildren();
 $('libraryCount').textContent=releases.length+' release'+(releases.length===1?'':'s');
 if(!releases.length)library.append(node('p','Add a release ZIP to get started.','library-empty'));
 for(const [profile,product] of Object.entries(releaseProducts)){
  const rows=releases.filter(release=>release.product===product);
  if(!rows.length)continue;
  const group=node('section','','library-group');
  const list=node('ul');
  group.append(node('h3',modelNames[profile]),list);
  rows.sort((a,b)=>b.version.localeCompare(a.version,undefined,{numeric:true}));
  for(const release of rows){
   const row=node('li');
   const chips=Object.keys(release.targets).map(chip=>chipNames[chip]||chip);
   row.append(node('strong',release.version),node('span',chips.join(' · ')));
   list.append(row);
  }
  library.append(group);
 }
}

function showFirmwareImport(show){
 $('firmwareImport').hidden=!show;
 const toggle=$('showFirmwareImport');
 toggle.textContent=show?'Close':'Add firmware';
 toggle.setAttribute('aria-expanded',String(show));
 if(show)$('firmwareZip').focus();
}

$('showFirmwareImport').onclick=()=>showFirmwareImport($('firmwareImport').hidden);
$('firmwareZip').onchange=()=>{
 $('importFirmware').disabled=!$('firmwareZip').files.length;
 $('firmwareImportStatus').textContent='';
};

$('firmwareImport').onsubmit=async event=>{
 event.preventDefault();
 const input=$('firmwareZip'),submit=$('importFirmware'),toggle=$('showFirmwareImport');
 const status=$('firmwareImportStatus'),file=input.files[0];
 if(!file || submit.disabled)return;
 if(!file.name.toLowerCase().endsWith('.zip') || file.size>64*1024*1024){
  status.className='danger-text';
  status.textContent='Choose a packaged release ZIP up to 64 MB.';
  return;
 }
 input.disabled=submit.disabled=toggle.disabled=true;
 status.className='';
 status.textContent='Checking both firmware builds…';
 try{
  const {release,added}=await api('firmware/import',file,'application/zip');
  status.className='library-success';
  status.textContent=release.name+(added?' added to the library.':' is already in the library.');
  input.value='';
  showFirmwareImport(false);
  equipmentStamp='';
  await refresh();
 }catch(e){
  status.className='danger-text';
  status.textContent=e.message;
 }finally{
  input.disabled=toggle.disabled=false;
  submit.disabled=!input.files.length;
  if($('firmwareImport').hidden && screen==='equipment')toggle.focus();
 }
};
