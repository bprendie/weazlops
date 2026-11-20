(() => {
'use strict';

const byId = id => document.getElementById(id);

const defaults = ['CHILLIN BUDDY','CRUISIN THE GIG','GIG IS TAXED','ALL IS NOT CHILL','ATZ NO CARRIER','MAYDAY! ZERO CHILL!','STAY CRUSTY BUD','MELLOW HASH ACK','OMW BUUUUDDY','SENDING JUICE','OMW BARE-METAL!','NUKING THE GIG'];
let rows = [];
function openHandout(teamName, roster, teamKey) {
    const committed=teamKey!=='draft';
    const phrases=committed?active.phrases:handoutPhrases;
    byId('paperMembers').replaceChildren();
    byId('paperForm').reset();
    byId('paperChoice').selectedIndex=phrases?1:0;
    for(const [id,input] of fields)input.value=(phrases||defaults)[id-1];
    byId('paperChoice').onchange();
    byId('paperBook').open = false;
    byId('paperTeam').value = teamName;
    rows = roster.map(({callsign,product,lead}, index) => {
      const role = product === 'drop' ? 'Drop' : lead ? 'Ghost · Lead' : 'Ghost';
      const row = document.createElement('div');
      row.className = 'member';
      const label = document.createElement('label');
      label.textContent = role;
      const controls = document.createElement('div');
      const select = document.createElement('select');
      select.id = 'paper-callsign-' + index;
      label.htmlFor = select.id;
      select.setAttribute('aria-label',role + ' callsign');
      for (const handle of [...handles,'Custom callsign…']) select.add(new Option(handle,handle));
      select.value = handles.includes(callsign)?callsign:'Custom callsign…';
      const input = document.createElement('input');
      input.placeholder = 'Enter callsign';
      input.setAttribute('aria-label','Custom callsign for ' + role);
      input.maxLength=16;
      input.pattern='[A-Za-z0-9_\\-]{1,16}';
      input.hidden = input.disabled = handles.includes(callsign);
      input.value=input.hidden?'':callsign;
      input.required = true;
      select.onchange = () => {
        input.hidden = input.disabled = handles.includes(select.value);
        clearErrors();
        if (!input.hidden) input.focus();
      };
      input.oninput = clearErrors;
      controls.append(select,input);
      row.append(label,controls);
      byId('paperMembers').append(row);
      return {role,select,input,callsign};
    });
    byId('paperForm').hidden = committed;
    byId('paperHandout').hidden = !committed;
    byId('paperBack').hidden=committed;
    if(committed)renderHandout(teamName,rows.map(row=>row.callsign+' · '+row.role),!!phrases);
  byId('paperDialog').showModal();
}
function clearErrors(){for (const row of rows) for (const el of [row.select,row.input]) el.setCustomValidity('');}
// Entry numbers match the standard Buddy codebook, including its reply pairs.
const tiers = [
  {name:'Sev1', messages:[1,2], responses:[7,8]},
  {name:'Sev2', messages:[3,4], responses:[9,10]},
  {name:'Sev3', messages:[5,6], responses:[11,12]},
];
const fields = new Map();
for (const tier of tiers) {
  const group = document.createElement('fieldset');
  group.className = 'severity';
  const legend = document.createElement('legend');
  legend.textContent = tier.name;
  group.append(legend);
  for (const [title,kind,ids] of [
    ['Messages','Message',tier.messages],
    ['Possible responses','Response',tier.responses],
  ]) {
    const heading = document.createElement('h3');
    heading.textContent = title;
    group.append(heading);
    for (const id of ids) {
      const label = document.createElement('label');
      label.className = 'phrase';
      label.textContent = kind + ' ' + id;
      const input = document.createElement('input');
      input.required = true;
      input.maxLength = 84;
      input.pattern = '[ -~]+';
      input.defaultValue = defaults[id-1];
      input.disabled = true;
      fields.set(id,input);
      label.append(input);
      group.append(label);
    }
  }
  byId('paperPhrases').append(group);
}
function handoutCodebook() {
  return tiers.map(tier => [
    tier.name,
    ...tier.messages.map(id => 'Message ' + id + ' · ' + fields.get(id).value),
    'Possible responses',
    ...tier.responses.map(id => 'Response ' + id + ' · ' + fields.get(id).value),
  ].join('\n')).join('\n\n');
}
byId('paperChoice').onchange = () => {
  const standard = byId('paperChoice').selectedIndex === 0;
  byId('paperEditor').hidden = standard;
  for (const input of fields.values()) input.disabled = standard;
  byId('paperSummary').textContent = 'Buddy codebook · ' + (standard ? 'Standard' : 'Custom team draft');
};
function renderHandout(name,members,custom) {
  byId('paperHeading').textContent=name;
  byId('paperResult').textContent=members.join('\n')+'\n\nBuddy codebook · '+(custom?'Custom':'Standard')+'\n'+handoutCodebook()+'\nReply / ACK · confirm to acknowledge the sender.';
}
byId('paperForm').onsubmit = async event => {
  event.preventDefault();
  const names = new Set();
  const members = [];
  for (const row of rows) {
    const field = row.input.disabled ? row.select : row.input;
    const name = field.value.trim();
    if (!name || names.has(name.toLowerCase())) {
      field.setCustomValidity('Enter a unique callsign for this member.');
      field.reportValidity();return;
    }
    names.add(name.toLowerCase());members.push(name);
  }
  const custom=byId('paperChoice').selectedIndex===1;
  const phrases=custom?Array.from({length:12},(_,i)=>fields.get(i+1).value):null;
  try {
    const saved=await api('session/handout',{phrases});
    if(saved.id)sessionStorage.setItem('wzl_draft_book',saved.id);else sessionStorage.removeItem('wzl_draft_book');
  }catch(e){byId('paperError').textContent=e.message;return;}
  byId('paperError').textContent='';
  handoutPhrases=phrases;
  byId('teamName').value=byId('paperTeam').value.trim();
  members.forEach((name,i)=>{slots[i].callsign=name;});
  renderSlots();
  renderHandout(byId('teamName').value,members.map((name,i)=>name+' · '+rows[i].role),custom);
  byId('paperForm').hidden = true;
  byId('paperHandout').hidden = false;
  byId('paperBack').focus();
};
byId('paperBack').onclick = () => {
  byId('paperForm').hidden = false;byId('paperHandout').hidden = true;byId('paperTeam').focus();
};

byId('planHandout').onclick = () => openHandout(byId('teamName').value, slots, 'draft');
byId('teamHandout').onclick = () => { if (active) openHandout(active.name, active.members, active.id); };
byId('logout').addEventListener('click', () => {
  handoutPhrases=null;
  sessionStorage.removeItem('wzl_draft_book');
  sessionStorage.removeItem('wzl_team_draft');
  byId('paperForm').reset();
  byId('paperResult').textContent = '';
  byId('paperMembers').replaceChildren();
  rows = [];
});
byId('paperClose').onclick = () => byId('paperDialog').close();
byId('paperPrint').onclick = () => window.print();
})();
