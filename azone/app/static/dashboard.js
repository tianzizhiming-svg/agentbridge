const BP=location.pathname.startsWith("/azone")?"/azone":"";const A=location.origin+BP;
let aT=null;

async function api(p){
  const r=await fetch(A+p);
  if(!r.ok) throw r.status;
  return r.json();
}

function ta(t){
  if(!t) return '-';
  const d=new Date(t)-Date.now();
  const m=Math.abs(Math.floor(d/6e4));
  if(m<1) return 'just now';
  if(m<60) return m+'m ago';
  const h=Math.floor(m/60);
  if(h<24) return h+'h ago';
  return Math.floor(h/24)+'d ago';
}

function esc(s){
  const d=document.createElement('div');
  d.textContent=s;
  return d.innerHTML;
}

async function lH(){
  try{
    const h=await api('/v1/health');
    document.getElementById('hs').textContent=h.status+' | V'+h.version.slice(1);
  }catch(e){
    document.getElementById('hs').textContent='Offline';
  }
}

async function lS(){
  try{
    const s=await api('/v1/stats');
    document.getElementById('sa').textContent=s.total_agents;
    document.getElementById('sv').textContent=s.active_agents;
    document.getElementById('sc2').textContent=s.capabilities;
    document.getElementById('se').textContent=s.events;
  }catch(e){}
}

async function lA(tag){
  try{
    let u='/v1/discover?limit=50';
    if(tag) u+='&tag='+encodeURIComponent(tag);
    const d=await api(u);
    const g=document.getElementById('agents');
    if(!d.results.length){
      g.innerHTML='<div class="empty">No agents found</div>';
      return;
    }
    g.innerHTML=d.results.map(a=>{
      const pc=a.probe_status==='reachable'||a.probe_status==='probed'?'pr':a.probe_status==='self_declared'?'ps':'pp';
      return '<div class="ac"><div class="top"><div class="nm">'+esc(a.name)+'</div><div class="pb '+pc+'">'+esc(a.probe_status)+'</div></div><div class="ds">'+esc(a.description||'')+'</div><div class="ep"><a href="'+esc(a.endpoint)+'" target="_blank">'+esc(a.endpoint)+'</a></div><div class="cs">'+(a.capabilities||[]).map(c=>'<span class="ct">'+esc(c.tag)+'</span>').join('')+'</div><div class="mt"><span>ID: '+esc(a.azone_id)+'</span><span>Seen: '+ta(a.last_seen_at)+'</span></div></div>';
    }).join('');
  }catch(e){}
}

async function lE(){
  try{
    const ev=await api('/v1/events?limit=30');
    const l=document.getElementById('events');
    if(!ev.length){
      l.innerHTML='<div class="empty">No events yet</div>';
      return;
    }
    l.innerHTML=ev.map(e=>{
      const tc=e.event_type.includes('JOIN')||e.event_type.includes('SUCCESS')||e.event_type.includes('ONLINE')?'ej':e.event_type.includes('FAIL')||e.event_type.includes('OFFLINE')?'ef':'ed';
      return '<div class="er"><span class="et '+tc+'">'+esc(e.event_type)+'</span><span class="ea">'+esc(e.actor_id)+'</span><span class="eg">'+esc(e.target_id||'-')+'</span><span class="em">'+ta(e.created_at)+'</span></div>';
    }).join('');
  }catch(e){}
}

async function lT(){
  try{
    const d=await api('/v1/discover?limit=100');
    const tags={};
    (d.results||[]).forEach(a=>(a.capabilities||[]).forEach(c=>{tags[c.tag]=(tags[c.tag]||0)+1}));
    const c=document.getElementById('tags');
    const sorted=Object.entries(tags).sort((a,b)=>b[1]-a[1]);
    c.innerHTML=sorted.map(([t,n])=>'<span class="ti'+(aT===t?' act':'')+'" data-tag="'+esc(t)+'">'+esc(t)+'<span class="cn">'+n+'</span></span>').join('');
    c.querySelectorAll('.ti').forEach(el=>{
      el.onclick=()=>{
        const t=el.dataset.tag;
        aT=aT===t?null:t;
        lT();
        lA(aT);
      };
    });
  }catch(e){}
}

async function refresh(){
  await Promise.all([lH(),lS(),lT(),lA(),lE()]);
}

refresh();
setInterval(refresh,30000);
