'use strict';
const $=id=>document.getElementById(id);
function el(tag,text='',cls=''){const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;}
const concepts={
 atlas:['Field guide','Which signature families appeared? Each illustrated card groups findings from the same family.'],
 volume:['Sample counts','Which findings had repeated observations? Bar length counts samples within one finding.'],
 signal:['Signal ranges','How much did reception vary? Each line spans the weakest to strongest recorded signal.'],
 queue:['Review board','What needs attention next? Findings are grouped by their current review state.']
};
const states={unreviewed:'Needs review',watch:'Watching',reviewed:'Reviewed',expected:'Expected'};
const examples=[
 ['BLE-FINDMY-FRAME-1',29,-74,-53,'unreviewed'],['BLE-FINDMY-FRAME-1',1,-68,-68,'reviewed'],
 ['BLE-AXON-BWC-1',8,-81,-61,'watch'],['WIFI-RING-VENDOR-1',13,-73,-65,'unreviewed'],
 ['BLE-TILE-DATA-1',5,-79,-70,'expected'],['RID-MESSAGE-1',3,-86,-81,'unreviewed']
].map(([rule,observations,min_rssi,max_rssi,disposition],i)=>({rule,observations,min_rssi,max_rssi,disposition,event_id:String(i+1),revision:1,team_name:'Example crew',source_id:'Demo Drop'}));
let catalog=[],saved=[],session=null,view='atlas',rows=[],snapshot='',reviews={},drafts=new Map(),generation=0;
function family(f){const i=catalog.findIndex(g=>g.rules.includes(f.rule));return i<0?24:i;}
function art(i){const n=el('span','','art art-'+i);n.setAttribute('aria-hidden','true');return n;}
function evidence(f){return el('small',[f.synthetic?'Synthetic evidence':'',f.rule,f.team_name,'Source '+f.source_id,'Event '+f.event_id,'Revision '+f.revision,f.observations+' samples',f.min_rssi+' to '+f.max_rssi+' dBm',states[f.disposition]||f.disposition].filter(Boolean).join(' · '));}
function groupCard(i,findings,guide){
 const card=el('details','','tile'),sum=el('summary');
 sum.append(art(i),el('strong',catalog[i].name));
 sum.append(el('small',guide?catalog[i].rules.length+' signature rules':findings.length+' finding'+(findings.length===1?'':'s')));
 card.append(sum);
 if(guide){const list=el('ul');for(const rule of catalog[i].rules)list.append(el('li',rule));card.append(list);}
 else for(const f of findings)card.append(evidence(f));
 return card;
}
function renderChart(container,signal){
 const ordered=[...rows].sort((a,b)=>signal?b.max_rssi-a.max_rssi:b.observations-a.observations);
 const min=signal?Math.min(-100,...rows.map(f=>f.min_rssi)):0;
 const max=signal?Math.max(-20,...rows.map(f=>f.max_rssi)):Math.max(1,...rows.map(f=>f.observations));
 const scale=x=>4+992*(x-min)/(max-min);
 const axis=el('div','','axis');axis.append(el('span',String(min)),el('span',max+(signal?' dBm':' samples')));container.append(axis);
 for(const f of ordered){
  const d=el('details','','row'),s=el('summary');
  const label=catalog[family(f)].name+' · '+(signal?f.min_rssi+' to '+f.max_rssi+' dBm':f.observations+' sample'+(f.observations===1?'':'s'));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 1000 18');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('class','chart');svg.setAttribute('aria-hidden','true');
  function line(start,end,color,width){const l=document.createElementNS(svg.namespaceURI,'line');for(const [k,v] of Object.entries({x1:start,x2:end,y1:9,y2:9,stroke:color,'stroke-width':width,'stroke-linecap':'round'}))l.setAttribute(k,v);svg.append(l);}
  line(4,996,'#38373f',2);line(scale(signal?f.min_rssi:0),scale(signal?f.max_rssi:f.observations),signal?'#bc9aff':'#e6e68a',7);
  s.append(art(family(f)),el('span',label),svg);d.append(s,evidence(f));container.append(d);
 }
}
function remember(){if(snapshot)drafts.set(snapshot+'/'+view,{rating:$('rating').value,note:$('note').value});}
function draw(){
 for(const b of $('tabs').children)b.setAttribute('aria-pressed',String(b.dataset.view===view));
 const root=$('preview');root.replaceChildren(el('h2',concepts[view][0]),el('p',concepts[view][1]));
 if(!rows.length)root.append(el('p','No saved findings in this snapshot.'));
 else if(view==='atlas'){
  const grid=el('div','','grid');
  catalog.forEach((g,i)=>{const fs=rows.filter(f=>family(f)===i);if(fs.length)grid.append(groupCard(i,fs,false));});root.append(grid);
 }else if(view==='queue'){
  const lanes=el('div','','lanes');
  for(const [key,name] of Object.entries(states)){
   const lane=el('section','','lane'),fs=rows.filter(f=>f.disposition===key);lane.append(el('h3',name+' · '+fs.length));
   for(const f of fs){const d=el('details'),s=el('summary');s.append(art(family(f)),el('strong',catalog[family(f)].name));d.append(s,evidence(f));lane.append(d);}lanes.append(lane);
  }root.append(lanes);
 }else renderChart(root,view==='signal');
 const prior=drafts.get(snapshot+'/'+view)||reviews[view]||{};
 $('rating').value=prior.rating||'';$('note').value=prior.note||'';$('feedbackTitle').textContent='Critique · '+concepts[view][0];
 $('status').textContent=session?(reviews[view]?'Previously saved.':''):'Sign in to WeazlOps to save feedback.';
 $('feedback').querySelector('button').disabled=!session||!snapshot;
}
async function changeDataset(){
 const gen=++generation;remember();snapshot='';reviews={};
 const demo=$('dataset').value==='examples';rows=demo?examples:saved;
 $('scope').textContent=(demo?'Illustrative data':'Saved station snapshot')+' · '+rows.length+' findings. All four views use these observations.';
 draw();
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(['review-v1',demo,rows])));
 const hash=Array.from(new Uint8Array(bytes),n=>n.toString(16).padStart(2,'0')).join('');
 const prior=session?await request('/api/intelligence/design-feedback/'+hash):{};
 if(gen===generation){reviews=prior;snapshot=hash;draw();}
}
async function request(url,options){const r=await fetch(url,options);if(!r.ok)throw Error(r.status===401?'Sign in to WeazlOps to open saved findings.':'Could not complete request. Please retry.');return r.json();}
async function init(){
 catalog=await request('/static/assets/intel-review/catalog.json');
 try{session=await request('/api/session');saved=(await request('/api/intelligence')).findings;}catch(e){$('dataset').options[1].disabled=true;}
 for(const [key,[title]] of Object.entries(concepts)){const b=el('button',title);b.dataset.view=key;b.onclick=()=>{remember();view=key;draw();};$('tabs').append(b);}
 catalog.forEach((g,i)=>$('gallery').append(groupCard(i,[],true)));
 $('dataset').onchange=()=>changeDataset().catch(e=>$('status').textContent=e.message);
 await changeDataset();
}
$('feedback').onsubmit=async e=>{
 e.preventDefault();if(!session||!snapshot)return;const hash=snapshot,key=view;
 const value={view:key,rating:$('rating').value,note:$('note').value};remember();
 try{await request('/api/intelligence/design-feedback/'+hash,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},body:JSON.stringify(value)});
 if(hash===snapshot){reviews[key]=value;if(key===view)$('status').textContent='Critique saved.';}}
 catch(err){$('status').textContent=err.message;}
};
init().catch(e=>$('scope').textContent=e.message);
