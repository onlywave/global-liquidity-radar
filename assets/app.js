/* Global Liquidity & Stress Radar — front-end */
(() => {
const $ = s => document.querySelector(s);
const BANDS = [[0,20,'--b0','Siccità'],[20,40,'--b1','Stretta'],[40,60,'--b2','Neutrale'],[60,80,'--b3','Allentamento'],[80,100,'--b4','Abbondanza']];
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const KIND = {QE:['#38d39f','Acquisti / QE'], tassi:['#18b6f0','Tassi'], 'liquidità':['#ffb547','Liquidità d\'emergenza'], guidance:['#cdb6ff','Comunicazione / guidance'], fiscale:['#ff8fab','Governo / fiscale']};
const fmt = (x,d=1,sign=false) => x==null||isNaN(x) ? '—' : (sign&&x>0?'+':'')+Number(x).toLocaleString('it-CH',{minimumFractionDigits:d,maximumFractionDigits:d});
const cls = x => x==null ? '' : x>0 ? 'pos' : x<0 ? 'neg' : '';
const dIt = s => s ? new Date(s+'T00:00:00').toLocaleDateString('it-CH',{day:'2-digit',month:'short',year:'numeric'}) : '—';
const bandOf = v => BANDS.find(b => v>=b[0] && v<b[1]) || BANDS[4];
const store = { get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}} };

let L, H, E, A, S, charts = {}, lastGen = null;

async function j(p){ const r = await fetch(p+'?t='+Date.now()); if(!r.ok) throw new Error(p); return r.json(); }

async function load(first){
  try{
    [L,H,E,A] = await Promise.all([j('data/latest.json'),j('data/history.json'),j('data/episodes.json'),j('data/alerts.json')]);
    try{ S = await j('data/signal.json'); }catch(e){ S = null; }
  }catch(e){ $('#fresh').textContent='dati non disponibili: il primo aggiornamento automatico è in corso'; return; }
  if(!first && L.generated===lastGen) return; lastGen = L.generated;
  renderTop(); gauge(); renderSignal(); renderAlerts(first); renderComps(); renderEpisodes(); renderSources();
  if(first){ histChart(); spxChart(); } else { charts.hist?.destroy(); charts.spx?.destroy(); histChart(); spxChart(); }
}

function renderTop(){
  const b = bandOf(L.score), col = css(b[2]);
  $('#k-score').textContent = fmt(L.score); $('#k-score').style.color = col;
  $('#k-regime').textContent = L.regime_it; $('#k-regime').style.color = col;
  if(L.to_up!=null){ $('#k-up').textContent = '+'+fmt(L.to_up)+' pt'; $('#k-up-l').textContent = 'A '+(bandOf(Math.min(L.band_hi,99.9)+0.01)[3]||'').toUpperCase(); }
  else { $('#k-up').textContent='—'; }
  $('#k-neutral').textContent = L.to_neutral===0 ? 'in fascia' : (L.score<40?'+':'−')+fmt(Math.abs(L.to_neutral))+' pt';
  [ '#k-up','#k-neutral' ].forEach(s=>$(s).style.color=col);
  const gen = new Date(L.generated.replace('Z',':00Z')), age = (Date.now()-gen)/36e5;
  $('#fresh').textContent = `dati al ${dIt(L.date)} · aggiornato ${gen.toLocaleString('it-CH',{dateStyle:'short',timeStyle:'short'})}`;
  document.querySelector('.fresh .pulse').classList.toggle('stale', age>8);
  $('#s-liq').textContent = fmt(L.liq,2,true); $('#s-str').textContent = fmt(L.stress,2,true);
  $('#s-liq-t').textContent = L.liq>0.5?'sopra la media':L.liq<-0.5?'sotto la media':'vicino alla media';
  $('#s-str-t').textContent = L.stress>1?'stress elevato':L.stress>0.3?'stress sopra la media':L.stress<-0.3?'stress basso':'nella media';
  [['#c1',L.chg_1w],['#c4',L.chg_4w],['#c13',L.chg_13w]].forEach(([s,v])=>{$(s).textContent=fmt(v,1,true)+' pt';$(s).className=cls(v)});
  $('#pct').textContent = fmt(L.percentile,0)+'°';
  $('#gnl').textContent = fmt(L.gnl/1000,2)+' bln $';
  $('#gnlc').innerHTML = [L.gnl_4w,L.gnl_13w,L.gnl_52w].map(v=>`<span class="${cls(v)}">${fmt(v,1,true)}%</span>`).join(' / ');
  $('#spxsrc').textContent = L.spx_source || 'FRED';
  $('#thr').textContent = E.threshold;
}

function gauge(){
  const svg = $('#gauge'), cx=300, cy=300, R=250, r=175;
  const ang = v => Math.PI*(1-v/100);
  const P = (a,rad) => [cx+rad*Math.cos(a), cy-rad*Math.sin(a)];
  const arc = (v0,v1,ro,ri) => { const a0=ang(v0),a1=ang(v1),[x0,y0]=P(a0,ro),[x1,y1]=P(a1,ro),[x2,y2]=P(a1,ri),[x3,y3]=P(a0,ri);
    return `M${x0},${y0} A${ro},${ro} 0 0 1 ${x1},${y1} L${x2},${y2} A${ri},${ri} 0 0 0 ${x3},${y3}Z`; };
  const cur = bandOf(L.score);
  let h = `<defs><filter id="gl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
  BANDS.forEach(b => { const on = b===cur;
    h += `<path d="${arc(b[0]+0.6,b[1]-0.6,R,r)}" fill="${css(b[2])}" opacity="${on?1:.42}" ${on?'filter="url(#gl)"':''}/>`; });
  [0,20,40,60,80,100].forEach(v=>{ const a=ang(v),[x,y]=P(a,R+22); const [tx,ty]=P(a,R+6),[ux,uy]=P(a,R-2);
    h += `<line x1="${tx}" y1="${ty}" x2="${ux}" y2="${uy}" stroke="#8792ad"/><text x="${x}" y="${y+5}" fill="#8792ad" font-size="15" text-anchor="middle">${v}</text>`; });
  h += `<path d="${arc(0,100,r-6,r-8)}" fill="#1a2547"/>`;
  const [nx,ny] = P(ang(L.score), R-18);
  h += `<line id="needle" x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="#eaf2ff" stroke-width="5" stroke-linecap="round" filter="url(#gl)"/>`;
  h += `<circle cx="${cx}" cy="${cy}" r="12" fill="#03050c" stroke="#eaf2ff" stroke-width="4"/><circle cx="${cx}" cy="${cy}" r="5" fill="#1f8bff"/>`;
  h += `<text x="${cx}" y="${cy-88}" fill="#fff" font-size="76" font-weight="800" text-anchor="middle">${fmt(L.score)}</text>`;
  h += `<text x="${cx}" y="${cy-58}" fill="${css(cur[2])}" font-size="17" font-weight="700" letter-spacing="1.2" text-anchor="middle">${({Drought:'LIQUIDITY DROUGHT',Tightening:'TIGHTENING',Neutral:'NEUTRAL',Easing:'EASING',Flood:'LIQUIDITY FLOOD'})[L.regime]}</text>`;
  const sub = `${cur[3]} · ` + (L.to_up!=null ? `${fmt(L.to_up)} pt alla fascia superiore` : `${fmt(L.to_down)} pt sopra ${cur[0]}`);
  h += `<text x="${cx}" y="${cy-34}" fill="#8792ad" font-size="13.5" text-anchor="middle">${sub}</text>`;
  svg.innerHTML = h;
}


function renderSignal(){
  if(!S){ $('#sig-sec').style.display='none'; return; }
  const lc = $('#sig-long').closest('.sigcard'), shc = $('#sig-short').closest('.sigcard');
  $('#sig-long').textContent = S.state;
  $('#sig-long').style.color = S.state.startsWith('LONG') ? 'var(--green)' : S.state.startsWith('ALLERTA') ? 'var(--amber)' : 'var(--mut)';
  lc.classList.toggle('on', S.state.startsWith('LONG')); lc.classList.toggle('pre', S.state.startsWith('ALLERTA'));
  $('#sig-long-since').textContent = S.since ? 'dal '+dIt(S.since)+' (validità 12 mesi)' : 'condizioni per un ingresso long:';
  $('#sig-long-checks').innerHTML = S.checks.map(c=>`<li class="${c.ok?'ok':''}">${c.text}<code>${fmt(c.value,1)}</code></li>`).join('');
  $('#sig-short').textContent = S.short_state;
  $('#sig-short').style.color = S.short_state==='SHORT ATTIVO' ? 'var(--red)' : S.short_state.startsWith('PRE') ? 'var(--amber)' : 'var(--mut)';
  shc.classList.toggle('on', S.short_state==='SHORT ATTIVO'); shc.classList.toggle('pre', S.short_state.startsWith('PRE'));
  $('#sig-short-since').textContent = S.short_since ? 'dal '+dIt(S.short_since)+' · si chiude quando cade una condizione' : 'si attiva con tutte e tre le condizioni:';
  $('#sig-short-checks').innerHTML = S.short_checks.map((c,i)=>`<li class="${c.ok?'ok':''}">${c.text}<code>${fmt(c.value,i==2?1:2,true)}${i==2?'%':''}</code></li>`).join('');
  const lab = {ALLERTA:'Allerta long (siccità)',ANTICIPATO:'Long anticipato',CONFERMATO:'Long confermato',SHORT:'Short / riduzione rischio',BASE:'Riferimento'};
  const cell = (x,inv) => x&&x.mean!=null ? `<span class="${cls(inv?-x.mean:x.mean)}">${fmt(x.mean,1,true)}%</span> <small class="note">${x.pos!=null?(inv?100-x.pos:x.pos)+'% '+(inv?'neg.':'pos.'):''}</small>` : '—';
  $('#sigstats tbody').innerHTML = ['CONFERMATO','ANTICIPATO','ALLERTA','SHORT','BASE'].map(k=>{ const t=S.stats[k]; if(!t) return '';
    const n = k==='SHORT' ? t.r3m.n+' sett.' : k==='BASE' ? t.r3m.n+' sett.' : t.r12m.n+' (+12m)';
    const extra = k==='SHORT' && t.r3m_2003_14 ? `<br><small>+3m: 2003–14 ${fmt(t.r3m_2003_14.mean,1,true)}% · 2015–26 ${fmt(t.r3m_2015_26.mean,1,true)}%</small>` : '';
    return `<tr><td><b>${lab[k]}</b></td><td>${t.rule}${extra}</td><td>${n}</td><td>${cell(t.r3m,k==='SHORT')}</td><td>${cell(t.r6m,k==='SHORT')}</td><td>${cell(t.r12m,k==='SHORT')}</td><td>${t.mdd6m&&t.mdd6m.mean!=null?fmt(t.mdd6m.mean,1)+'%':'—'}</td></tr>`; }).join('');
  $('#sighist tbody').innerHTML = S.history.map(h=>`<tr><td>${h.date}</td><td style="color:${h.tier==='SHORT'?'var(--red)':h.tier==='ALLERTA'?'var(--amber)':'var(--green)'}">${lab[h.tier]}</td><td>${fmt(h.score)}</td><td>${fmt(h.spx,0)}</td>${['r3m','r6m','r12m','mdd6m'].map(k=>`<td class="${cls(h[k])}">${h[k]==null?'—':fmt(h[k],1,true)+'%'}</td>`).join('')}</tr>`).join('');
  $('#sig-note').textContent = S.note;
}

function renderAlerts(first){
  const act = A.active || [];
  $('#active').innerHTML = act.length ? act.map(a=>`<div class="al ${a.level}"><span class="tag">${a.code}</span><span>${a.text}<br><small class="note">${dIt(a.date)}</small></span></div>`).join('')
    : `<div class="al ok"><span class="tag">OK</span><span>Nessun alert attivo nell'ultima settimana di dati.</span></div>`;
  $('#alog').innerHTML = (A.log||[]).slice(0,120).map(a=>`<li><time>${a.date}</time>[${a.code}] ${a.text}</li>`).join('') || '<li>Nessun alert registrato.</li>';
  $('#rlog').innerHTML = (A.regime_changes||[]).slice(0,150).map(r=>`<li><time>${r.date}</time>${r.frm} → <b>${r.to}</b> (${fmt(r.score)})</li>`).join('');
  const key = (A.log&&A.log[0]) ? A.log[0].date+A.log[0].code : '';
  const seen = store.get('glsi_seen');
  if(!first && key && key!==seen && 'Notification' in window && Notification.permission==='granted'){
    new Notification('GLSI '+fmt(L.score)+' — '+L.regime_it, {body: A.log[0].text});
  }
  if(key) store.set('glsi_seen', key);
}

$('#notif').addEventListener('click', async ()=>{
  if(!('Notification' in window)) { $('#notif').textContent='Browser senza notifiche'; return; }
  const p = await Notification.requestPermission();
  $('#notif').textContent = p==='granted' ? 'Notifiche attive (con la pagina aperta)' : 'Notifiche bloccate';
});
if('Notification' in window && Notification.permission==='granted') $('#notif').textContent='Notifiche attive (con la pagina aperta)';

function renderComps(){
  $('#comps').innerHTML = L.components.map(c=>{
    const z = c.z, w = z==null?0:Math.min(Math.abs(z),3)/3*50;
    const good = c.group==='Liquidità' ? z>0 : z<0;
    const col = z==null ? '#333' : good ? 'var(--b4)' : 'var(--red)';
    const left = z>=0 ? 50 : 50-w;
    return `<div class="comp"><span><span class="g">${c.group.toUpperCase()}</span>${c.name}</span><div class="bar"><i style="left:${left}%;width:${w}%;background:${col}"></i></div><b class="${good?'pos':'neg'}">${fmt(z,2,true)}</b></div>`;
  }).join('');
}

function heat(z){ const t = Math.max(0,Math.min(1,(z-0.5)/2.5)); return `rgba(255,93,115,${0.12+0.6*t})`; }

function renderEpisodes(){
  const eps = E.episodes;
  $('#ep-sub').textContent = `${eps.length} episodi dal 2006 · soglia stress z > ${E.threshold}`;
  $('#eps tbody').innerHTML = eps.map((e,i)=>{
    const ivs = e.interventions.length ? e.interventions.map(v=>`<span class="iv"><time>${v.date}</time><b style="color:${(KIND[v.kind]||['#ccc'])[0]}">${v.bank}</b> — ${v.action}</span>`).join('')
      : `<span class="unc">${e.catalogued?'nessun intervento in catalogo':'da verificare'}</span>`;
    return `<tr data-i="${i}">
      <td>${e.name}${e.ongoing?'<span class="ongoing">in corso</span>':''}</td>
      <td>${e.start.slice(0,7)} → ${e.end.slice(0,7)}</td>
      <td>${dIt(e.peak)}</td>
      <td><span class="heat" style="background:${heat(e.stress_z)}">${fmt(e.stress_z,2,true)}</span></td>
      <td>${fmt(e.score_min)}</td><td>${fmt(e.stlfsi,2)}</td><td>${fmt(e.nfci,2)}</td><td>${fmt(e.vix)}</td><td>${fmt(e.hy,2)}</td>
      <td>${fmt(e.spx_peak,0)}</td><td class="${cls(e.spx_dd)}">${fmt(e.spx_dd,1,true)}%</td>
      <td class="${cls(e.fwd_3m)}">${e.fwd_3m==null?'—':fmt(e.fwd_3m,1,true)+'%'}</td>
      <td class="${cls(e.fwd_6m)}">${e.fwd_6m==null?'—':fmt(e.fwd_6m,1,true)+'%'}</td>
      <td class="${cls(e.fwd_12m)}">${e.fwd_12m==null?'—':fmt(e.fwd_12m,1,true)+'%'}</td>
      <td>${ivs}</td></tr>`;
  }).join('');
  document.querySelectorAll('#eps tbody tr').forEach(tr=>tr.addEventListener('click',()=>{
    document.querySelectorAll('#eps tr.sel').forEach(x=>x.classList.remove('sel')); tr.classList.add('sel');
    const e = eps[+tr.dataset.i], a = new Date(e.start), b = new Date(e.end);
    a.setMonth(a.getMonth()-6); b.setMonth(b.getMonth()+12);
    zoom('spx', a, b); document.getElementById('spx').scrollIntoView({behavior:'smooth',block:'center'});
  }));
}

function renderSources(){
  $('#src tbody').innerHTML = L.series.map(s=>`<tr><td><a href="${s.url}" target="_blank" rel="noopener" style="color:#8fb3ff">${s.name}</a> <code>${s.id}</code></td><td>${s.src}</td><td>${s.ok?dIt(s.last_date):'<span class="neg">non disponibile</span>'}</td><td>${s.last_value==null?'—':fmt(s.last_value,2)}</td><td>${s.unit}</td></tr>`).join('');
}

/* ------------------------------------------------ charts */
Chart.defaults.color = '#8792ad'; Chart.defaults.font.family = 'Inter'; Chart.defaults.borderColor = '#121b33';
const pts = (key) => H.dates.map((d,i)=>({x:d, y:H[key][i]})).filter(p=>p.y!=null);
function rangeOf(years){ const end = new Date(H.dates[H.dates.length-1]); if(!years) return [new Date(H.dates[0]), end]; const a=new Date(end); a.setFullYear(a.getFullYear()-years); return [a,end]; }
function zoom(id,a,b){ const c=charts[id]; c.options.scales.x.min=a; c.options.scales.x.max=b; c.update(); }

function histChart(){
  const ann = {};
  BANDS.forEach((b,i)=>ann['b'+i]={type:'box',yMin:b[0],yMax:b[1],backgroundColor:css(b[2])+'22',borderWidth:0,drawTime:'beforeDatasetsDraw'});
  [20,40,60,80].forEach(v=>ann['l'+v]={type:'line',yMin:v,yMax:v,borderColor:'#26324f',borderWidth:1,borderDash:[4,4]});
  const [a,b] = rangeOf(20);
  charts.hist = new Chart($('#hist'),{type:'line',
    data:{datasets:[{label:'GLSI',data:pts('score'),borderColor:'#eaf2ff',borderWidth:1.6,pointRadius:0,tension:.15,
      segment:{borderColor:ctx=>css(bandOf(ctx.p1.parsed.y)[2])||'#fff'}}]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},
      scales:{x:{type:'time',min:a,max:b,time:{unit:'year'},grid:{display:false}},y:{min:0,max:100,ticks:{stepSize:20}}},
      plugins:{legend:{display:false},annotation:{annotations:ann},
        tooltip:{callbacks:{label:c=>` GLSI ${fmt(c.parsed.y)} · ${bandOf(c.parsed.y)[3]}`}}}}});
}

function spxChart(){
  const ann = {};
  E.episodes.forEach((e,i)=>{ ann['e'+i]={type:'box',xMin:e.start,xMax:e.end,yScaleID:'y',backgroundColor:heat(e.stress_z).replace(/[\d.]+\)$/,m=>(parseFloat(m)*0.55).toFixed(2)+')'),borderWidth:0,drawTime:'beforeDatasetsDraw',
    label:{display:e.stress_z>=2.3,content:e.name.split(' → ')[0].split(' / ')[0],position:{x:'center',y:'start'},color:'#ffb3bf',font:{size:10,weight:600},rotation:0}}; });
  const spxAt = d => { const i = H.dates.findIndex(x=>x>=d); return i<0?null:H.spx[i] ?? H.spx[i+1]; };
  const ivAll = (E.interventions||[]).map(v=>({x:v.date,y:spxAt(v.date),v})).filter(p=>p.y!=null);
  const ds = Object.entries(KIND).map(([k,[col,lab]])=>({type:'scatter',label:lab,data:ivAll.filter(p=>p.v.kind===k),yAxisID:'y',
    pointStyle:'triangle',pointRadius:7,pointHoverRadius:10,backgroundColor:col,borderColor:'#03050c',borderWidth:1,order:0}));
  if(S){
    const sp = t => (S.history||[]).filter(h=>h.tier===t).map(h=>({x:h.date,y:h.spx,s:h}));
    ds.push({type:'scatter',label:'Long confermato',data:sp('CONFERMATO'),yAxisID:'y',pointStyle:'circle',pointRadius:8,backgroundColor:'#38d39f',borderColor:'#fff',borderWidth:1.5,order:-1});
    ds.push({type:'scatter',label:'Long anticipato',data:sp('ANTICIPATO'),yAxisID:'y',pointStyle:'circle',pointRadius:6,backgroundColor:'#38d39f55',borderColor:'#38d39f',borderWidth:2,order:-1});
    ds.push({type:'scatter',label:'Ingresso short',data:sp('SHORT'),yAxisID:'y',pointStyle:'crossRot',pointRadius:9,borderColor:'#ff5d73',borderWidth:3,order:-1});
  }
  const [a,b] = rangeOf(20);
  charts.spx = new Chart($('#spx'),{
    data:{datasets:[
      {type:'line',label:'S&P 500',data:pts('spx'),borderColor:'#18b6f0',borderWidth:1.6,pointRadius:0,yAxisID:'y',order:2},
      {type:'line',label:'Stress composito (z)',data:pts('stress'),borderColor:'#b06cffaa',backgroundColor:'#b06cff18',fill:{target:{value:0},above:'#b06cff22',below:'transparent'},borderWidth:1.2,pointRadius:0,yAxisID:'y2',order:3},
      ...ds]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'nearest',intersect:false},
      scales:{x:{type:'time',min:a,max:b,time:{unit:'year'},grid:{display:false}},
        y:{type:'logarithmic',position:'left',title:{display:true,text:'S&P 500'},ticks:{callback:v=>[500,1000,2000,3000,4000,5000,6000,7000,8000,10000].includes(v)?v.toLocaleString('it-CH'):''}},
        y2:{position:'right',min:-2,max:3.2,grid:{display:false},title:{display:true,text:'stress z'}}},
      plugins:{legend:{display:false},annotation:{annotations:ann},
        tooltip:{callbacks:{
          title:it=>it[0]?.raw?.s ? dIt(it[0].raw.s.date) : it[0]?.raw?.v ? dIt(it[0].raw.v.date) : dIt(String(it[0]?.raw?.x).slice(0,10)),
          label:c=> c.raw.s ? ` ${c.dataset.label} · GLSI ${fmt(c.raw.s.score)} · +12m ${c.raw.s.r12m==null?'—':fmt(c.raw.s.r12m,1,true)+'%'}` : c.raw.v ? ` ${c.raw.v.bank}: ${c.raw.v.action}` : ` ${c.dataset.label}: ${fmt(c.parsed.y, c.dataset.yAxisID==='y2'?2:0)}`}}}}});
  $('#kinds').innerHTML = Object.values(KIND).map(([c,l])=>`<span><i style="--c:${c}"></i>${l}</span>`).join('') + `<span><span style="display:inline-block;width:14px;height:10px;background:#ff5d7366;margin-right:6px"></span>Episodio di stress</span><span style="color:#38d39f">● Long confermato</span><span style="color:#38d39f">○ Long anticipato</span><span style="color:#ff5d73">✕ Ingresso short</span>`;
}

document.querySelectorAll('.seg').forEach(seg=>seg.addEventListener('click',ev=>{
  const btn = ev.target.closest('button'); if(!btn) return;
  const id = seg.dataset.target;
  if(btn.id==='logtog'){ btn.classList.toggle('on'); charts.spx.options.scales.y.type = btn.classList.contains('on')?'logarithmic':'linear'; charts.spx.update(); return; }
  seg.querySelectorAll('button[data-r]').forEach(b=>b.classList.remove('on')); btn.classList.add('on');
  const [a,b] = rangeOf(+btn.dataset.r); zoom(id,a,b);
}));

load(true);
setInterval(()=>load(false), 10*60*1000);
})();
