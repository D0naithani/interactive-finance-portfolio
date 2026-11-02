'use strict';
const $ = id => document.getElementById(id);
const money = cents => cents == null ? '—' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(cents/100);
const esc = text => String(text ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const projects = {
 quality:{n:'01',title:'Financial Data Quality Engine',subtitle:'Compare ledger and bank records, inspect exceptions and export a reconciliation report.',api:'quality',table:'Transaction reconciliation'},
 investor:{n:'02',title:'Investor Operations Console',subtitle:'Review capital commitments, inspect investor balances and calculate a pro-rata distribution.',api:'investors',table:'Capital & allocation register'},
 gro:{n:'03',title:'M&A SaaS Product Studio',subtitle:'Review deal stages, screening metrics, ownership and product requirements.',api:'deals',table:'Opportunity pipeline'},
 kpi:{n:'04',title:'Founder KPI Operating System',subtitle:'Monitor recurring revenue and customer economics. Adjust growth and churn assumptions to compare scenarios.',api:'kpis',table:'Monthly revenue bridge'}
};
let project, params, requestNumber=0;
const sessionId=sessionStorage.getItem('demoSession') || crypto.randomUUID();
sessionStorage.setItem('demoSession',sessionId);
function field(label,id,type,options,value){return `<label>${label}${type==='select'?`<select id="${id}">${options.map(v=>`<option>${esc(v)}</option>`).join('')}</select>`:`<input id="${id}" type="${type}" value="${value??''}" ${type==='number'?'min="0" max="100" step="1"':''}>`}</label>`;}
function mount(){
 const key=location.hash.slice(1); project=projects[key]?key:'quality'; params=new URLSearchParams();
 document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+project));
 const p=projects[project]; $('eyebrow').textContent=`PROJECT ${p.n} / INTERACTIVE DEMONSTRATION`;$('title').textContent=p.title;$('subtitle').textContent=p.subtitle;$('workspace-title').textContent=p.table;$('detail').replaceChildren();$('chart').replaceChildren();
 let controls='';
 if(project==='quality') controls=field('Search reference or account','q','search',null,'')+field('Exception status','status','select',['all','matched','variance','missing_bank','missing_ledger','duplicate'])+field('Tolerance / cents','tolerance_cents','number',null,0);
 if(project==='investor') controls=field('Fund','fund','select',['All','Atlas I','Atlas II'])+field('Distribution / USD','distribution','number',null,100000);
 if(project==='gro') controls=field('Pipeline stage','stage','select',['All','Sourcing','Screening','Diligence','Negotiation']);
 if(project==='kpi') controls=field('Acquisition channel','channel','select',['All','Organic','Paid','Partner'])+field('History / months','period','select',['6','12','3','1'])+field('Monthly growth / %','growth','number',null,8)+field('Monthly churn / %','churn','number',null,3);
 $('controls').innerHTML=controls+'<button id="apply">Apply filters</button>'+(project==='quality'?'<button id="reset-review">Reset review session</button>':'');
 if($('distribution')){$('distribution').max='1000000000';$('distribution').step='.01';}
 if($('tolerance_cents')) $('tolerance_cents').max='10000';
 $('apply').onclick=()=>load();$('controls').querySelectorAll('select').forEach(el=>el.onchange=()=>load());$('controls').querySelectorAll('input').forEach(el=>el.onkeydown=e=>{if(e.key==='Enter')load();});
 if($('reset-review'))$('reset-review').onclick=async()=>{try{await api(`/api/quality/sessions/${sessionId}`,{method:'DELETE'});load();}catch(e){$('error').textContent=e.message;$('error').hidden=false;}};
 load();
}
function currentParams(){const p=new URLSearchParams();$('controls').querySelectorAll('input,select').forEach(el=>{if(!el.checkValidity())throw new Error('Please enter values within the displayed input limits.');p.set(el.id==='distribution'?'distribution_cents':el.id,el.id==='distribution'?Math.round(Number(el.value)*100):el.value);});if(project==='quality')p.set('session_id',sessionId);return p;}
async function api(path,options){const response=await fetch(path,options);if(!response.ok){let message=`Request failed (${response.status})`;try{const body=await response.json();message=typeof body.detail==='string'?body.detail:message;}catch{}throw new Error(message);}return response.json();}
function metric(label,value,sub){return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(sub)}</small></div>`;}
function table(headers,rows){$('thead').innerHTML='<tr>'+headers.map(h=>`<th scope="col">${esc(h)}</th>`).join('')+'</tr>';$('tbody').innerHTML=rows.map(cells=>'<tr>'+cells.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('');$('empty').hidden=rows.length>0;}
function badge(status){return `<span class="badge ${status==='matched'?'':'warn'}">${esc(status.replaceAll('_',' '))}</span>`;}
async function load(){const version=++requestNumber;try{params=currentParams();$('apply').disabled=true;$('export').disabled=true;$('error').hidden=true;$('connection').textContent='Loading analysis…';$('metrics').replaceChildren();$('tbody').replaceChildren();$('thead').replaceChildren();$('empty').hidden=true;const data=await api(`/api/${projects[project].api}?${params}`);if(version!==requestNumber)return;$('connection').textContent='API connected · Synthetic data';$('note').textContent=data.note+(data.session_note?' '+data.session_note:'');$('detail').replaceChildren();render(data);}catch(error){if(version===requestNumber){$('error').textContent=error.message;$('error').hidden=false;$('connection').textContent='Analysis unavailable';$('metrics').replaceChildren();$('tbody').replaceChildren();$('thead').replaceChildren();$('chart').replaceChildren();$('detail').replaceChildren();}}finally{if(version===requestNumber){$('apply').disabled=false;$('export').disabled=!$('error').hidden;}}}
function render(data){const s=data.summary;let metrics='';
 if(project==='quality'){
  metrics=metric('Records in view',s.records,'Identifiers reconciled across both sources')+metric('Control exceptions',s.exceptions,'Missing, duplicate or outside tolerance')+metric('Absolute matched-source variance',money(s.absolute_variance_cents),'Missing amounts excluded');
  table(['Reference','Account','Ledger / USD','Bank / USD','Variance / USD','Match status','Review'],data.rows.map(r=>[`<button class="row-button" data-tx="${esc(r.id)}">${esc(r.id)}</button>`,esc(r.account),money(r.ledger_cents),money(r.bank_cents),money(r.variance_cents),badge(r.status),r.resolution_status?badge(r.resolution_status):'—']));
  document.querySelectorAll('[data-tx]').forEach(el=>el.onclick=()=>{const r=data.rows.find(row=>row.id===el.dataset.tx);$('detail').innerHTML=`<h3>${esc(r.id)} · Reconciliation detail</h3><p>Source status: ${esc(r.status)} · Ledger: ${money(r.ledger_cents)} · Bank: ${money(r.bank_cents)} · Variance: ${money(r.variance_cents)}</p>`+(r.status==='matched'?'<p>This record reconciles within the selected tolerance.</p>':`<p>Review status: <b>${esc(r.resolution_status)}</b>. Marking a review does not change source amounts or reconcile a variance.</p><label>Review note<input id="review-note" maxlength="280" value="${esc(r.resolution_note)}"></label><div class="review-actions"><button id="reviewed">Mark reviewed</button><button id="resolved">Mark resolved</button><button id="reopen">Reopen</button></div>`);if(r.status==='matched')return;for(const state of ['reviewed','resolved','reopen'])$(state).onclick=async()=>{try{const path=`/api/quality/exceptions/${encodeURIComponent(r.id)}/resolution?session_id=${sessionId}&tolerance_cents=${params.get('tolerance_cents')}`;await api(path,state==='reopen'?{method:'DELETE'}:{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:state,note:$('review-note').value})});await load();}catch(e){$('error').textContent=e.message;$('error').hidden=false;}};});
 }
 if(project==='investor'){
  metrics=metric('Committed capital',money(s.commitment_cents),'Synthetic investor commitments')+metric('Paid-in capital',money(s.paid_in_cents),'Basis for pro-rata distribution')+metric('Scenario distribution',money(s.distribution_cents),'Largest remainder rounding to cents');
  table(['Investor','Fund','Commitment','Paid in','Uncalled','Allocation'],data.rows.map(r=>[`<button class="row-button" data-investor="${esc(r.id)}">${esc(r.investor)}</button>`,esc(r.fund),money(r.commitment_cents),money(r.paid_in_cents),money(r.uncalled_cents),money(r.allocation_cents)]));
  document.querySelectorAll('[data-investor]').forEach(el=>el.onclick=()=>{const r=data.rows.find(row=>row.id===el.dataset.investor);$('detail').innerHTML=`<h3>${esc(r.investor)} · ${esc(r.fund)}</h3><p>Paid-in share: ${(r.share*100).toFixed(2)}% · Prior distributions: ${money(r.prior_distributions_cents)} · Scenario allocation: ${money(r.allocation_cents)}</p><p>Uncalled capital: ${money(r.uncalled_cents)}. This is an illustrative allocation, with no contractual waterfall.</p>`;});
 }
 if(project==='gro'){
  metrics=metric('Active opportunities',s.deals,'Filter by stage to focus the review')+metric('Enterprise value pipeline',money(s.pipeline_cents),'Sum of illustrative enterprise values')+metric('Probability-weighted pipeline',money(s.weighted_pipeline_cents),'Sum of value × stage probability');
  table(['Opportunity','Sector','Stage','Revenue','EV / Revenue','Probability','Owner'],data.rows.map(r=>[`<button class="row-button" data-deal="${esc(r.id)}">${esc(r.company)}</button>`,esc(r.sector),badge(r.stage),money(r.revenue_cents),`${r.ev_revenue_multiple}×`,`${Math.round(r.probability*100)}%`,esc(r.owner)]));
  document.querySelectorAll('[data-deal]').forEach(el=>el.onclick=async()=>{const v=requestNumber;try{const d=await api(`/api/deals/${encodeURIComponent(el.dataset.deal)}`);if(v!==requestNumber)return;$('detail').innerHTML=`<h3>${esc(d.deal.company)} / Deal workspace</h3><p>Next action: ${esc(d.deal.next_action)} · Owner: ${esc(d.deal.owner)}</p><p>${d.workflow.map(esc).join(' → ')}</p><h4>Product requirements & acceptance criteria</h4><ul>${d.requirements.map(r=>`<li><b>${esc(r.feature)}</b> — ${esc(r.acceptance)}</li>`).join('')}</ul><p>Architecture: browser → FastAPI → pandas → synthetic CSV sources. Persistent workflow and audit storage are future production extensions.</p>`;}catch(e){$('detail').textContent=e.message;}});
 }
 if(project==='kpi'){
  metrics=metric('Monthly recurring revenue',money(s.mrr_cents),`Annualised run rate ${money(s.arr_cents)}`)+metric('Active customers',s.customers,`Latest monthly customer churn ${s.customer_churn_pct??'—'}%`)+metric('Customer acquisition cost',money(s.cac_cents),'Latest monthly marketing spend / new customers');
  table(['Month','Opening MRR','New MRR','Churned MRR','Closing MRR','Customers'],data.rows.map(r=>[esc(r.month),money(r.opening_mrr_cents),money(r.new_mrr_cents),money(r.churned_mrr_cents),money(r.closing_mrr_cents),esc(r.customers)]));
  const values=[s.mrr_cents,...data.forecast.map(r=>r.mrr_cents)], max=Math.max(...values,1), points=values.map((v,i)=>`${i/(values.length-1)*900},${110-v/max*95}`).join(' ');
  $('chart').innerHTML=`<div class="chart"><div class="chart-label">SCENARIO / SIX MONTHS FORWARD · Ending MRR ${money(values.at(-1))}</div><svg viewBox="0 0 900 130" role="img" aria-label="Six month MRR projection"><polyline points="${points}" fill="none" stroke="#3c7567" stroke-width="3" vector-effect="non-scaling-stroke"/></svg><div class="legend">Today → +6 months · <b>Illustrative forecast</b></div></div>`;
  $('detail').innerHTML='<h3>Forecast detail</h3><p>'+data.forecast.map(r=>`Month ${r.month}: <b>${money(r.mrr_cents)}</b>`).join(' &nbsp; / &nbsp; ')+'</p>';
 }
 $('metrics').innerHTML=metrics;
}
$('export').onclick=()=>{const link=document.createElement('a');link.href=`/api/${projects[project].api}?${params}&export=true`;link.download='';link.click();};
window.addEventListener('hashchange',mount);mount();
