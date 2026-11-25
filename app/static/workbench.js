import {request, element} from './client.js';
import {snapshot, history} from './view.js';
import {visualize} from './plots.js';

const form = document.querySelector('#source');
const file = document.querySelector('#file');
const profile = document.querySelector('#profile');
const status = document.querySelector('#notice');
const detail = document.querySelector('#review');
const evidence = document.querySelector('#evidence');
const scope = document.querySelector('#scope');
const stages = [...document.querySelectorAll('[data-stage]')];
let stage = 'balance';
let report, selected, batch, running = false;

function source() {
  const data = new FormData();
  if (file.files.length) data.append('file',file.files[0]);
  else data.append('sample',profile.value);
  return data;
}

function announce(text, failure = false) {
  status.textContent = text;
  status.dataset.failure = String(failure);
}

function decisionOf(caseId) {
  return batch?.decisions?.find(item=>item.case===caseId);
}

function currentNote() {
  if (!batch) return '';
  if (!scope.value) return batch.note || '';
  return decisionOf(scope.value)?.note || '';
}

function syncScope() {
  const current = scope.value;
  scope.replaceChildren(element('option','整批（全部批组）',{value:''}));
  for (const row of report.cases || []) {
    const decision = decisionOf(row.case);
    scope.append(element('option',`批组 ${row.case}${decision ? ` · ${decision.status}` : ''}`,{value:row.case}));
  }
  scope.value = [...scope.options].some(option=>option.value===current) ? current : (selected || '');
}

function draw() {
  if (!report) return;
  snapshot(report, selected, stage, batch?.decisions);
  visualize(report, selected);
  for (const button of stages) button.setAttribute('aria-pressed',String(button.dataset.stage===stage));
  document.querySelector('#panel-title').textContent = stages.find(button => button.dataset.stage===stage)?.textContent || '运行对账';
  detail.hidden = !batch;
  if (batch) {
    const release = report.balance?.release;
    document.querySelector('#run-status').textContent =
      `${batch.id.slice(0,10)} · ${batch.status} · r${batch.revision}` + (release?.blocked ? ' · 整单待查' : '');
    syncScope();
    const finalized = batch.status==='APPROVED';
    let approveDisabled = finalized, holdDisabled = finalized;
    if (scope.value) {
      const decision = decisionOf(scope.value);
      approveDisabled = approveDisabled || decision?.status==='APPROVED' || !(release?.cases?.[scope.value]?.releasable ?? false);
      holdDisabled = holdDisabled || decision?.status==='APPROVED';
    } else {
      approveDisabled = approveDisabled || !report.balance?.releasable;
    }
    detail.querySelector('[value="APPROVED"]').disabled = approveDisabled;
    detail.querySelector('[value="HELD"]').disabled = holdDisabled;
    detail.elements.note.value = currentNote();
    evidence.href = `/api/runs/${batch.id}/evidence`;
  }
}

function show(payload, committed = false) {
  batch = committed ? payload : null;
  report = committed ? payload.report : payload;
  selected = report.cases?.[0]?.case;
  draw();
}

async function refresh() {
  const data = await request('/api/runs');
  history(data.items, batch?.id);
}

async function perform(action) {
  if (running) return;
  running = true;
  document.body.setAttribute('aria-busy','true');
  announce('处理中…');
  try { await action(); }
  catch (error) { announce(error.message,true); }
  finally { running = false; document.body.removeAttribute('aria-busy'); }
}

function preview(next) {
  return perform(async () => {
    const payload = await request(`/api/stages/${next}`,{method:'POST',body:source()});
    stage = next;
    show(payload);
    announce('阶段预览已更新');
    await refresh();
  });
}

stages.forEach(button => button.addEventListener('click',()=>preview(button.dataset.stage)));
form.addEventListener('submit', event => {
  event.preventDefault();
  perform(async () => {
    const result = await request('/api/runs',{method:'POST',body:source()});
    stage = 'balance'; show(result,true);
    announce('批次已保存'); await refresh();
  });
});
const filename = document.querySelector('#file-name');
profile.addEventListener('change',()=>{file.value=''; filename.textContent=''; preview(stage);});
file.addEventListener('change',()=>{filename.textContent=file.files[0]?.name || ''; preview(stage);});
document.querySelector('#rows').addEventListener('click',event=>{
  const button = event.target.closest('[data-case]');
  if (button) { selected = button.dataset.case; scope.value = selected; draw(); document.querySelector(`[data-case="${CSS.escape(selected)}"]`).focus(); }
});
scope.addEventListener('change',()=>{ draw(); });
document.querySelector('#history').addEventListener('click',event=>{
  const button = event.target.closest('[data-run]');
  if (button) perform(async()=>{
    const result = await request(`/api/runs/${button.dataset.run}`);
    stage='balance'; show(result,true); announce('已载入历史批次'); await refresh();
  });
});
detail.addEventListener('submit',event=>{
  event.preventDefault();
  perform(async()=>{
    const note = detail.elements.note.value;
    const decision = event.submitter.value;
    let result, label;
    if (scope.value) {
      const revision = decisionOf(scope.value)?.revision ?? 0;
      result = await request(`/api/runs/${batch.id}/cases/${encodeURIComponent(scope.value)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:decision,revision,note})});
      label = `批组 ${scope.value}`;
    } else {
      result = await request(`/api/runs/${batch.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:decision,revision:batch.revision,note})});
      label = '批次';
    }
    show(result,true); announce(decision==='APPROVED'?`${label}已签发`:`${label}已暂缓`); await refresh();
  });
});
preview(stage);
