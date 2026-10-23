const $ = id => document.getElementById(id);
let lastId = 0, commentCount = 0, giftCount = 0, replyCount = 0;
const spoken = new Set();
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function say(text,id){
  if(!$('voice').checked || !('speechSynthesis' in window) || spoken.has(id)) return;
  spoken.add(id);
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = 'pt-BR'; utter.rate = 1.05; utter.pitch = 1.08;
  window.speechSynthesis.speak(utter);
}
function addItem(e){
  $('empty')?.remove();
  const item=document.createElement('article');
  item.className='item '+(e.kind==='ai'?'ai':e.kind==='gift'?'gift':'');
  item.innerHTML=`<div class="meta"><strong>${esc(e.kind==='ai'?'🤖 MIGO AI':e.kind==='gift'?'🎁 PRESENTE':e.kind==='comment'?'💬 COMENTÁRIO':'ℹ️ SISTEMA')} · ${esc(e.user)}</strong><span>${esc(e.time)}</span></div><div class="message">${esc(e.message)}</div>${e.extra?`<div class="extra">${esc(e.extra)}</div>`:''}`;
  $('feed').prepend(item);
  while($('feed').children.length>80)$('feed').lastElementChild.remove();
  if(e.kind==='comment') $('comments').textContent=++commentCount;
  if(e.kind==='gift') $('gifts').textContent=++giftCount;
  if(e.kind==='ai'){ $('replies').textContent=++replyCount; say(e.message,e.id); }
}
async function poll(){
  try{
    const r=await fetch('/api/events?after='+lastId,{cache:'no-store'});
    const events=await r.json();
    for(const e of events){addItem(e);lastId=Math.max(lastId,e.id);}
    const sr=await fetch('/api/status',{cache:'no-store'}), s=await sr.json();
    $('status').textContent=s.status||'Desconectado';
    $('dot').classList.toggle('on',(s.status||'').includes('Conectado à LIVE'));
    $('error').textContent=s.error||'';
  }catch(e){$('status').textContent='Reconectando ao painel…';}
  setTimeout(poll,1800);
}
$('connect').addEventListener('click',async()=>{
  const username=$('username').value.trim().replace(/^@/,'');
  if(!username){$('error').textContent='Digite seu @ do TikTok.';return;}
  $('connect').disabled=true;$('error').textContent='';
  try{
    const r=await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username})});
    const data=await r.json();
    if(!r.ok) $('error').textContent=data.error||'Não foi possível conectar.';
    else $('status').textContent='Tentando conectar…';
  }catch(e){$('error').textContent='Não consegui falar com o servidor.';}
  setTimeout(()=>$('connect').disabled=false,3500);
});
poll();
