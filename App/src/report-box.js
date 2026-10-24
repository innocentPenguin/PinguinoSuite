/* ============ Report a problem (every page): note + screenshots -> core writes Data\feedback\<time>-<page>.md/.json for 00 / the engines ============
   Loaded by index.html after the main script (shares its globals: $, $$, post, titles, route, modOf).
   One small fixed button; the form is a compact modal, closed by default. Nothing here takes layout space. */
const RP={imgs:[],busy:false};
function initReport(){
  const KEY='pinguino.reportbox.open';
  const mem=v=>{try{if(v===undefined)return localStorage.getItem(KEY)==='1';localStorage.setItem(KEY,v?'1':'0')}catch{return false}};
  const st=document.createElement('style');st.textContent=`
  #rp-fab{position:fixed;right:12px;bottom:12px;z-index:60;opacity:.6;padding:2px 9px;font-size:11px;line-height:18px;border-radius:999px;width:auto;height:auto;min-height:0}#rp-fab:hover,#rp-fab:focus-visible{opacity:1}
  #rp-box{position:fixed;right:12px;bottom:40px;z-index:61;box-sizing:border-box;width:min(420px,calc(100vw - 24px));max-height:calc(100vh - 64px);overflow:auto;background:var(--panel2);border:1px solid var(--line2);border-radius:12px;padding:12px;box-shadow:0 8px 30px rgba(0,0,0,.45);display:none}
  #rp-box textarea{width:100%;box-sizing:border-box;min-height:84px;max-height:30vh;margin:6px 0}#rp-box .th{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}#rp-box .th span{position:relative}#rp-box .th img{height:46px;border-radius:6px;border:1px solid var(--line2)}#rp-box .th b{position:absolute;top:-6px;right:-6px;cursor:pointer;background:#000a;border-radius:50%;width:16px;height:16px;text-align:center;font-size:11px;line-height:16px}`;
  document.head.append(st);
  const fab=document.createElement('button');fab.id='rp-fab';fab.className='sm';fab.textContent='⚑ Report';fab.title='Report a problem on this page. Saved on this PC only.';fab.setAttribute('aria-haspopup','dialog');fab.setAttribute('aria-expanded','false');
  const box=document.createElement('div');box.id='rp-box';box.hidden=true;box.style.display='none';box.setAttribute('role','dialog');box.setAttribute('aria-label','Report a problem');   // hidden on the element itself, not only by the injected stylesheet
  box.innerHTML=`<b>Report a problem</b> <span class="sm faint" id="rp-where"></span><textarea id="rp-note" maxlength="8000" placeholder="What is wrong, or what did you expect? You can paste a screenshot here (Ctrl+V) or attach one."></textarea>
   <div class="th" id="rp-th"></div><div class="row wrap" style="gap:8px"><label class="sm" style="cursor:pointer"><input type="file" id="rp-file" accept="image/*" multiple hidden><span class="pill">📎 Attach screenshot</span></label><span class="sp"></span><button class="sm" id="rp-close">Close</button><button class="pri sm" id="rp-send">Send</button></div>
   <div class="sm" id="rp-msg" style="margin-top:6px"></div><div class="sm faint" style="margin-top:4px">Saved in Data\feedback on this PC (nothing is sent anywhere). <a href="#" id="rp-open">Open folder</a></div>`;
  document.body.append(fab,box);
  const isOpen=()=>box.style.display==='block';
  const msg=t=>{$('#rp-msg').textContent=t},th=()=>{$('#rp-th').innerHTML=RP.imgs.map((m,i)=>`<span><img src="${m.data}" alt=""><b data-i="${i}" title="remove">×</b></span>`).join('');$$('#rp-th b').forEach(b=>b.onclick=()=>{RP.imgs.splice(+b.dataset.i,1);th()})};
  const add=files=>{for(const f of files){if(!/^image\//.test(f.type))continue;if(RP.imgs.length>=6){msg('At most 6 screenshots');break}if(f.size>8*1024*1024){msg('That image is over 8 MB');continue}
    const r=new FileReader();r.onload=()=>{RP.imgs.push({name:f.name||'pasted.png',data:r.result});th()};r.readAsDataURL(f)}};
  const shut=(refocus=true)=>{box.style.display='none';fab.setAttribute('aria-expanded','false');mem(false);if(refocus&&typeof refocus==='boolean')fab.focus()};   // closing hands the focus back to the button that opened it
  const show=(focus=true)=>{box.style.display='block';fab.setAttribute('aria-expanded','true');mem(true);$('#rp-where').textContent='· '+(titles[route]||(modOf(route)&&modOf(route).name)||route);msg('');if(focus)$('#rp-note').focus()};
  fab.onclick=()=>{if(isOpen())shut();else show()};
  $('#rp-close').onclick=()=>shut();
  $('#rp-file').onchange=e=>{add([...e.target.files]);e.target.value=''};
  box.addEventListener('paste',e=>{const fs=[...(e.clipboardData&&e.clipboardData.files||[])];if(fs.length){e.preventDefault();add(fs)}});
  document.addEventListener('mousedown',e=>{if(isOpen()&&!box.contains(e.target)&&!fab.contains(e.target))shut(false)});   // click outside closes
  document.addEventListener('keydown',e=>{if(!isOpen())return;
    if(e.key==='Escape'){shut();return}
    if(e.key==='Tab'){const fs=[...box.querySelectorAll('textarea,button:not([disabled]),a[href],input:not([hidden])')].filter(x=>x.offsetParent!==null);   // keep Tab inside the open box
      if(!fs.length)return;const first=fs[0],last=fs[fs.length-1];
      if(e.shiftKey&&(document.activeElement===first||!box.contains(document.activeElement))){e.preventDefault();last.focus()}
      else if(!e.shiftKey&&(document.activeElement===last||!box.contains(document.activeElement))){e.preventDefault();first.focus()}}});
  $('#rp-open').onclick=async e=>{e.preventDefault();try{const r=await post('/api/feedback/open');if(r.detail)msg('Could not open the folder: '+r.detail)}catch{msg('Could not open the folder')}};
  $('#rp-send').onclick=async()=>{if(RP.busy)return;const note=$('#rp-note').value.trim();if(!note&&!RP.imgs.length){msg('Write a note or attach a screenshot first');return}
    RP.busy=true;$('#rp-send').disabled=true;msg('Saving…');
    try{const r=await post('/api/feedback',{note,page:titles[route]||route,route,url:location.href.split('#')[0]+'#'+route,images:RP.imgs});
      if(r&&r.ok){msg('Saved. Thank you.');$('#rp-note').value='';RP.imgs=[];th();setTimeout(()=>{if(isOpen())shut(box.contains(document.activeElement)||document.activeElement===document.body)},1200)}else msg('Not saved: '+((r&&r.detail)||'unknown error'))}
    catch(e){msg('Not saved: '+(e.message||e))}
    RP.busy=false;$('#rp-send').disabled=false}
  if(mem())show(false);   // reopen where the person left it (per browser)
}
initReport();
