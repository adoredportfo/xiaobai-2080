/* One copilot, explicit context, opt-in audio. Audio stays in memory until discarded. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const names = {general:'自由对话',learning:'学业领航',growth:'成长发展',experience:'情感陪伴',status:'生活助手'};
  const sessions = Object.fromEntries(Object.keys(names).map(id => [id, []]));
  let context = 'general', ready = false, voiceReady = false, busy = false;
  let latestReply = '', requestController = null;
  const baseBubble = window.bubble, baseDemo = window.submitChat;
  const status = document.createElement('div');
  status.className = 'ai-banner offline'; status.textContent = '正在检查小白连接…';
  document.querySelector('.chat-panel').prepend(status);
  function tell(text) { $('voiceStatus').textContent = text; }
  function add(who, text, record=true) {
    baseBubble(who,text);
    if (record) sessions[context].push({role:who==='user'?'user':'assistant',content:text});
    if (who==='bot') latestReply=text;
  }
  window.bubble=(who,text)=>add(who,text);
  function switchContext(next) {
    if (!names[next]) return;
    if (busy && next!==context) { $('copilotModule').value=context; tell('小白正在回答。请稍等，或先重启当前对话。'); return; }
    stopSpeech(); context=next; $('copilotModule').value=next;
    $('chatMessages').replaceChildren(); latestReply='';
    chatState.topic=''; chatState.turn=0;
    $('copilotContextNote').textContent='当前：'+names[next]+'。只使用本情境中你主动发送的内容，不自动读取情绪日记或健康记录。';
    const history=sessions[next];
    add('bot','我是小白。当前是「'+names[next]+'」。你可以打字，也可以录音转成文字；是否采取下一步由你决定。',false);
    history.forEach(m=>add(m.role==='user'?'user':'bot',m.content,false));
    options(next==='learning'?['我知道原理，但不知道怎么开始','帮我拆一个小练习']:next==='growth'?['我想试试校园观察','我想整理实践记录']:next==='experience'?['先听我说，不急着给建议','我想休息一下']:next==='status'?['帮我梳理今天的安排','我的两件事时间冲突了']:chatOptions);
  }
  window.openCopilot=(module,draft)=>{
    if (busy && module!==context) { go('chat'); tell('请等当前回复完成后再切换情境。'); return; }
    switchContext(module); go('chat');
    if (draft) $('chatText').value=draft;
    $('chatText').focus();
  };
  $('copilotModule').addEventListener('change',()=>switchContext($('copilotModule').value));
  document.querySelectorAll('[data-copilot-open]').forEach(b=>b.addEventListener('click',()=>openCopilot(b.dataset.copilotOpen)));
  function traceLearning(text) {
    if(context!=='learning')return;
    try { const k='xb2080_learning_trace_v1',a=JSON.parse(localStorage.getItem(k)||'[]');
      a.push({time:new Date().toLocaleString('zh-CN'),text:text.slice(0,100),type:'学习问题'});
      localStorage.setItem(k,JSON.stringify(a.slice(-20)));
    } catch(e) { /* Conversation works even without persistent storage. */ }
  }
  window.submitChat=async function(text) {
    const value=String(text||'').trim(); if(!value||busy)return;
    stopSpeech(); traceLearning(value);
    if(!ready) {
      baseDemo(value);
      if($('voiceAuto').checked) playReply();
      return;
    }
    add('user',value); $('chatText').value=''; busy=true; $('chatText').disabled=true;
    $('copilotModule').disabled=true; options([]);
    const pending=document.createElement('p'); pending.className='muted'; pending.textContent='小白正在想…'; $('chatMessages').append(pending);
    requestController=new AbortController();
    try {
      const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({module:context,messages:sessions[context].slice(-24)}),signal:requestController.signal});
      const j=await r.json(); if(!r.ok||!j.reply)throw Error(j.error||'暂时没有收到回复');
      add('bot',j.reply); insight('当前情境：'+names[context],'结合本轮问题与上下文','建议由你确认，不会自动执行','这里是服务提示，不是模型内部思维。');
      if($('voiceAuto').checked)playReply();
    } catch(e) {
      if(e.name!=='AbortError') { sessions[context].pop(); add('bot','连接暂时遇到问题：'+e.message+'。你的问题已保留，可以检查后重试。',false); $('chatText').value=value; }
    } finally { pending.remove();busy=false;requestController=null;$('chatText').disabled=false;$('copilotModule').disabled=false; }
  };
  window.restartChat=()=>{
    requestController?.abort();stopSpeech();sessions[context]=[];switchContext(context);
  };
  document.querySelectorAll('[data-copilot-action]').forEach(b=>b.addEventListener('click',()=>{
    const last=[...sessions[context]].reverse().find(m=>m.role==='user');
    if(!last){$('copilotActionStatus').textContent='先说出你想解决的一件事，再带到工作台。';return;}
    const target=b.dataset.copilotAction;
    go(target);
    if(target==='learning') { document.querySelector('[data-learning-feature="plan"]').click();$('learnGoal').value=last.content.slice(0,180);$('learnGoal').focus(); }
    if(target==='growth') { $('gxContext').value=last.content.slice(0,300);$('gxForm').scrollIntoView({block:'center',behavior:'smooth'}); }
    if(target==='status') { $('taskTitle').value=last.content.slice(0,100);$('lifeSchedulePanel').scrollIntoView({block:'start',behavior:'smooth'});$('dayPlanAdvice').textContent='从对话带入的日程草稿；请检查事项、日期与时间，再点击添加，目前尚未保存。'; }
    $('copilotActionStatus').textContent='已填入草稿，未自动保存、执行或公开。';
  }));
  // Reveal optional tools before scrolling to them, while keeping the page's primary path focused.
  document.addEventListener('click',e=>{
    const b=e.target.closest('[data-module-target],button[onclick]');if(!b)return;
    const id=b.dataset.moduleTarget||(/getElementById\(['"]([^'"]+)/.exec(b.getAttribute('onclick')||'')||[])[1];
    const el=id&&$(id);if(el){for(let parent=el.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;}
  },true);

  // Recording lifecycle: off -> recording -> local preview -> explicit upload -> editable text.
  let recorder=null,stream=null,chunks=[],recorded=null,recordTimer=null,recording=false,transcribing=false,acquiring=false,recordGeneration=0,transcribeController=null,transcribeTimer=null;
  const maxBytes=8*1024*1024;
  function stopTracks(){stream?.getTracks().forEach(t=>t.stop());stream=null;clearTimeout(recordTimer);}
  function discardRecording(){recordGeneration++;transcribeController?.abort();clearTimeout(transcribeTimer);if(recorder&&recorder.state==='recording')recorder.stop();stopTracks();recorder=null;recorded=null;chunks=[];recording=false;$('voiceRecord').textContent='开始录音';$('voiceTranscribe').hidden=true;$('voiceDiscard').hidden=true;}
  function stopRecording(){if(recorder?.state==='recording')recorder.stop();stopTracks();recording=false;$('voiceRecord').textContent='开始录音';}
  $('voiceRecord').addEventListener('click',async()=>{
    if(transcribing)return;
    if(recording){stopRecording();return;}
    if(!ready||!voiceReady){tell('录音转写需要已配置的模型服务；当前可以打字，语音回答可选择设备朗读。');return;}
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){tell('当前浏览器不支持网页录音。请在 HTTPS 网页中使用较新的 Safari 或 Chrome；也可以用键盘自带听写输入。');return;}
    discardRecording();stopSpeech();const token=recordGeneration;
    acquiring=true;$('voiceRecord').disabled=true;tell('请允许本页使用麦克风。只有确认转写后才上传音频。');
    try {
      const acquired=await navigator.mediaDevices.getUserMedia({audio:true});
      if(token!==recordGeneration){acquired.getTracks().forEach(t=>t.stop());return;}
      stream=acquired;const mime=['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus'].find(t=>MediaRecorder.isTypeSupported(t));
      recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
      chunks=[];
      recorder.ondataavailable=e=>{if(e.data.size&&token===recordGeneration)chunks.push(e.data);if(chunks.reduce((n,b)=>n+b.size,0)>maxBytes)stopRecording();};
      recorder.onerror=()=>{discardRecording();tell('录音出错，已关闭麦克风。请重试或打字。');};
      recorder.onstop=()=>{
        if(token!==recordGeneration)return;
        recorded=new Blob(chunks,{type:recorder.mimeType||mime||'audio/webm'});stopTracks();recording=false;$('voiceRecord').textContent='重新录音';
        if(!recorded.size||recorded.size>maxBytes){discardRecording();tell('录音为空或超过8 MB，请缩短后重录。');return;}
        $('voiceTranscribe').hidden=false;$('voiceDiscard').hidden=false;tell('录音已停止，尚未上传。点击“确认转成文字”，或删除重录。');
      };
      recorder.start();recording=true;$('voiceRecord').textContent='停止录音';$('voiceDiscard').hidden=false;tell('正在录音，最长60秒。再次点击停止；不会自动发送给小白。');recordTimer=setTimeout(stopRecording,60000);
    } catch(e) { discardRecording();tell(e.name==='NotAllowedError'?'麦克风权限未开启。可以在浏览器设置中允许，或继续打字。':'无法启动麦克风，请关闭其他录音应用后重试。'); }
    finally{acquiring=false;$('voiceRecord').disabled=false;}
  });
  $('voiceDiscard').addEventListener('click',()=>{discardRecording();tell('录音已删除，麦克风已关闭。');});
  $('voiceTranscribe').addEventListener('click',async()=>{
    if(!recorded||transcribing)return;transcribing=true;
    const token=recordGeneration;transcribeController=new AbortController();transcribeTimer=setTimeout(()=>transcribeController?.abort(),65000);$('voiceTranscribe').disabled=true;$('voiceRecord').disabled=true;
    tell('正在转写。完成后请检查文字，再点击发送。');
    try {
      const r=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':recorded.type},body:recorded,signal:transcribeController.signal});const j=await r.json();if(!r.ok)throw Error(j.error||'转写失败');
      if(token!==recordGeneration)return;
      $('chatText').value=[$('chatText').value.trim(),j.text].filter(Boolean).join(' ');discardRecording();tell('已填入文字，尚未发送。请检查识别结果后点击发送。');$('chatText').focus();
    } catch(e) {if(token===recordGeneration)tell((e.name==='AbortError'?'转写超时':e.message)+'。录音仍在本页，可重试或删除。');}
    finally{clearTimeout(transcribeTimer);transcribeController=null;transcribing=false;$('voiceTranscribe').disabled=false;$('voiceRecord').disabled=false;}
  });
  // Voice replies: no hidden playback, explicit stop cancels requests and revokes blob URLs.
  let player=null,audioURL=null,speechController=null,speechGeneration=0;
  function stopSpeech(){speechGeneration++;speechController?.abort();speechController=null;player?.pause();player=null;if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null;}window.speechSynthesis?.cancel();}
  function deviceSpeak(text){if(!window.speechSynthesis||!window.SpeechSynthesisUtterance){tell('设备不支持朗读，可以继续查看文字回复。');return;}const u=new SpeechSynthesisUtterance(text);u.lang='zh-CN';u.rate=.95;u.onend=()=>tell('朗读结束。');u.onerror=()=>tell('设备朗读中断，文字回复仍保留。');speechSynthesis.speak(u);tell('正在使用设备朗读，可随时停止。');}
  async function playReply(){
    if(!latestReply){tell('还没有可播放的回复。先和小白聊一句吧。');return;}
    stopSpeech();const token=speechGeneration,text=latestReply.slice(0,1000);
    if($('voiceMode').value==='device'){deviceSpeak(text);return;}
    if(!ready||!voiceReady){tell('自然语音服务暂不可用。可选择“设备朗读”，或继续查看文字。');return;}
    tell('正在生成小白语音…');speechController=new AbortController();
    try {const r=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,voice:$('voiceTone').value}),signal:speechController.signal});
      if(!r.ok){const j=await r.json();throw Error(j.error||'语音生成失败');}
      const blob=await r.blob();if(token!==speechGeneration)return;
      audioURL=URL.createObjectURL(blob);player=new Audio(audioURL);player.onended=()=>{if(token===speechGeneration){stopSpeech();tell('小白说完了，你可以继续说。');}};
      await player.play();tell('小白正在说话。点击“停止播放”可以打断。');
    } catch(e){if(e.name!=='AbortError'&&token===speechGeneration){stopSpeech();tell(e.name==='NotAllowedError'?'浏览器限制自动播放，请点击“播放最新回复”，或选择设备朗读。':e.message+'。文字回复不受影响，可切换设备朗读。');}}
  }
  $('voicePlay').addEventListener('click',playReply);$('voiceStop').addEventListener('click',()=>{stopSpeech();tell('语音已停止。');});
  $('voiceAuto').addEventListener('change',()=>{if(!$('voiceAuto').checked)stopSpeech();});$('voiceMode').addEventListener('change',stopSpeech);$('voiceTone').addEventListener('change',stopSpeech);
  window.addEventListener('pagehide',()=>{discardRecording();stopSpeech();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){if(recording)stopRecording();stopSpeech();}});
  window.addEventListener('modulechange',e=>{if(e.detail.id!=='chat'){if(acquiring)discardRecording();else if(recording)stopRecording();stopSpeech();}});
  switchContext('general');
  fetch('/api/status',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(j=>{
    ready=!!j.ready;voiceReady=!!j.voice?.transcribe&&!!j.voice?.speech;
    status.className='ai-banner'+(ready?'':' offline');status.textContent=ready?'已配置模型服务 · 可以发送问题，实际连接结果以本轮回复为准':'当前为文字情境演示 · 设备朗读仍可使用';
    document.querySelector('.chat-status .small').textContent=ready?'在线服务 · 多轮对话':'情境演示 · 非实时大模型';
    if(!voiceReady)tell('录音转写与自然语音尚未就绪。可以打字；需要朗读时选择“设备朗读”。');
  }).catch(()=>{status.textContent='当前无法连接模型服务，先使用文字演示。';tell('录音转写暂不可用；你仍可打字或选择设备朗读。');});
})();
