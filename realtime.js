/* Genuine full-duplex WebRTC audio. Long-lived API credentials stay on the server. */
(function () {
  'use strict';
  const $=id=>document.getElementById(id);
  let state='idle',generation=0,peer=null,channel=null,mic=null,controller=null;
  let connectTimer=null,durationTimer=null,disconnectTimer=null,muted=false,responding=false;
  const rows=new Map(),audio=$('realtimeAudio');
  function active(){return state!=='idle';}
  function status(text,badge){$('realtimeStatus').textContent=text;if(badge)$('realtimeBadge').textContent=badge;}
  function controls(){
    $('realtimeStart').hidden=active();$('realtimeEnd').hidden=!active();
    $('realtimeMute').hidden=state!=='connected';$('realtimeInterrupt').hidden=state!=='connected';
    $('realtimeBadge').classList.toggle('connected',state==='connected');
  }
  function send(event){if(channel?.readyState==='open')channel.send(JSON.stringify(event));}
  function caption(key,role,text,append=false){
    if(!key)return;
    let row=rows.get(key);
    if(!row){
      if(rows.size===0)$('realtimeCaptions').replaceChildren();
      row=document.createElement('div');row.className='realtime-caption '+role;
      const label=document.createElement('strong');label.textContent=role==='user'?'你':'小白';
      const content=document.createElement('span');row.append(label,content);$('realtimeCaptions').append(row);rows.set(key,row);
      if(rows.size>60){const first=rows.keys().next().value;rows.get(first).remove();rows.delete(first);}
    }
    const span=row.querySelector('span');span.textContent=(append?span.textContent:'')+String(text||'');
    $('realtimeCaptions').scrollTop=$('realtimeCaptions').scrollHeight;
  }
  function end(message='通话已结束，麦克风已关闭。'){
    const wasActive=active();generation++;state='idle';
    controller?.abort();controller=null;
    clearTimeout(connectTimer);clearTimeout(durationTimer);clearTimeout(disconnectTimer);
    if(channel){channel.onmessage=null;channel.onopen=null;channel.onclose=null;channel.onerror=null;try{channel.close()}catch(e){}channel=null;}
    if(peer){peer.ontrack=null;peer.onconnectionstatechange=null;try{peer.close()}catch(e){}peer=null;}
    mic?.getTracks().forEach(t=>t.stop());mic=null;
    audio.pause();audio.srcObject=null;responding=false;muted=false;
    $('realtimeMute').textContent='麦克风静音';$('realtimeMute').setAttribute('aria-pressed','false');$('realtimeResume').hidden=true;
    controls();status(message,'未连接');
    if(wasActive)window.dispatchEvent(new Event('realtime:ended'));
  }
  window.xiaobaiRealtime={isActive:active,stop:()=>end()};
  async function playAudio(){
    try{await audio.play();$('realtimeResume').hidden=true;}
    catch(e){$('realtimeResume').hidden=false;status('已连接，但浏览器阻止播放声音。请点击“播放通话声音”。','已连接');}
  }
  function onEvent(event){
    let e;try{e=JSON.parse(event.data)}catch(error){return;}
    if(!active())return;
    const key=e.item_id||e.response_id;
    switch(e.type){
      case 'input_audio_buffer.speech_started':
        if(muted)return;
        responding=false;caption(e.item_id,'user','正在听…');status('我在听，你说完后我会回应。','正在听');break;
      case 'input_audio_buffer.speech_stopped':
        if(!muted)status('正在理解你的话…','正在回应');break;
      case 'conversation.item.input_audio_transcription.completed':
        caption(e.item_id,'user',e.transcript||'（未识别到清晰文字）');break;
      case 'conversation.item.input_audio_transcription.failed':
        caption(e.item_id,'user','（本次字幕识别失败，语音通话仍可继续）');break;
      case 'response.created':responding=true;break;
      case 'response.output_audio_transcript.delta':
        caption(key,'assistant',e.delta,true);status(muted?'麦克风已静音，小白正在回应。':'小白正在说话；你直接开口就能打断。','小白在说');break;
      case 'response.output_audio_transcript.done':caption(key,'assistant',e.transcript);break;
      case 'output_audio_buffer.started':responding=true;break;
      case 'output_audio_buffer.stopped':
        responding=false;status(muted?'麦克风已静音，点击“取消静音”后继续。':'我说完了，你可以继续说。',muted?'已静音':'已连接');break;
      case 'response.done':
        if(e.response?.status==='failed'){responding=false;status('这轮回复未完成，你可以再说一次，或结束后使用文字对话。','已连接');}
        break;
      case 'error':
        if(e.error?.code==='response_cancel_not_active')return;
        // Provider messages can contain implementation details; keep the visible message bounded and generic.
        status('实时服务遇到问题，可以重说一句；若仍无回应，请结束后重新连接。','连接提示');break;
    }
  }
  $('realtimeStart').addEventListener('click',async()=>{
    if(active())return;
    if(window.getCopilotState?.().busy){status('请等当前文字回复完成，或重启对话后再连接。');return;}
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.RTCPeerConnection){status('此浏览器不支持实时通话。请使用 HTTPS 网页及较新的 Safari 或 Chrome；下方录音和文字仍可使用。');return;}
    state='connecting';const token=++generation;controls();status('正在申请麦克风权限…','连接中');
    window.dispatchEvent(new Event('realtime:starting'));
    controller=new AbortController();
    connectTimer=setTimeout(()=>{if(token===generation)end('连接超时，麦克风已关闭。请检查网络后重试，或使用下方录音与文字。');},30000);
    try{
      // Ask for permission first. Cancellation invalidates the token, including a late permission grant.
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      if(token!==generation){stream.getTracks().forEach(t=>t.stop());return;}
      mic=stream;peer=new RTCPeerConnection();
      peer.ontrack=e=>{if(token!==generation)return;audio.srcObject=e.streams[0]||new MediaStream([e.track]);playAudio();};
      peer.onconnectionstatechange=()=>{
        if(token!==generation)return;
        if(peer.connectionState==='failed'||peer.connectionState==='closed')end('语音连接已断开，麦克风已关闭。可以重新连接或继续打字。');
        else if(peer.connectionState==='disconnected'){
          status('网络暂时中断，正在等待恢复…','重连中');
          clearTimeout(disconnectTimer);disconnectTimer=setTimeout(()=>{if(token===generation)end('网络连接未恢复，通话已结束，麦克风已关闭。');},8000);
        }else if(peer.connectionState==='connected'){clearTimeout(disconnectTimer);if(state==='connected')status(muted?'麦克风已静音。':'已连接，你可以直接和小白说话。',muted?'已静音':'已连接');else status('语音线路已接通，正在准备实时对话…','连接中');}
      };
      mic.getAudioTracks().forEach(track=>peer.addTrack(track,mic));
      channel=peer.createDataChannel('oai-events');channel.onmessage=onEvent;
      channel.onopen=()=>{
        if(token!==generation)return;
        clearTimeout(connectTimer);state='connected';controls();status('已连接，你可以直接说话；不用反复点击发送。','已连接');
        durationTimer=setTimeout(()=>end('本次通话已到15分钟，麦克风已关闭。需要时可以重新连接。'),15*60*1000);
      };
      channel.onclose=()=>{if(token===generation)end('实时通话已断开，麦克风已关闭。');};
      channel.onerror=()=>{if(token===generation)end('实时通道连接失败。请检查网络，或使用录音和文字。');};
      status('正在连接小白实时语音…','连接中');
      const response=await fetch('/api/realtime/session',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({module:$('copilotModule').value,voice:$('voiceTone').value}),signal:controller.signal});
      const credentials=await response.json();if(!response.ok||!credentials.client_secret)throw Error('实时会话暂不可用');
      if(token!==generation)return;
      const offer=await peer.createOffer();if(token!==generation)return;await peer.setLocalDescription(offer);
      if(token!==generation)return;
      const answer=await fetch('https://api.openai.com/v1/realtime/calls?model='+encodeURIComponent(credentials.model),{method:'POST',body:offer.sdp,
        headers:{Authorization:'Bearer '+credentials.client_secret,'Content-Type':'application/sdp'},signal:controller.signal});
      if(!answer.ok)throw Error('实时语音握手失败');
      const sdp=await answer.text();if(token!==generation)return;await peer.setRemoteDescription({type:'answer',sdp});
    }catch(e){
      if(token!==generation)return;
      end(e.name==='NotAllowedError'?'麦克风权限未开启，通话未开始。可以允许权限后重试，或继续打字。':'实时连接暂时失败，麦克风已关闭。请检查网络或模型权限；下方录音和文字仍可使用。');
    }
  });
  $('realtimeEnd').addEventListener('click',()=>end());
  $('realtimeMute').addEventListener('click',()=>{
    if(state!=='connected')return;muted=!muted;mic?.getAudioTracks().forEach(t=>t.enabled=!muted);
    if(muted)send({type:'input_audio_buffer.clear'});
    $('realtimeMute').textContent=muted?'取消静音':'麦克风静音';$('realtimeMute').setAttribute('aria-pressed',String(muted));
    status(muted?'麦克风已静音，小白不会收到你的声音。':'麦克风已开启，可以继续说话。',muted?'已静音':'已连接');
  });
  $('realtimeInterrupt').addEventListener('click',()=>{
    if(state!=='connected')return;if(responding)send({type:'response.cancel'});send({type:'output_audio_buffer.clear'});responding=false;
    status(muted?'已打断小白，麦克风仍静音。':'已打断小白，你可以继续说。',muted?'已静音':'正在听');
  });
  $('realtimeResume').addEventListener('click',playAudio);
  window.addEventListener('modulechange',e=>{if(active()&&e.detail.id!=='chat')end('已离开对话页，实时通话结束，麦克风已关闭。');});
  window.addEventListener('copilot:contextchange',()=>{if(active())end('已切换对话情境，上一段实时通话已结束。');});
  window.addEventListener('pagehide',()=>end());
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&active())end('页面已进入后台，实时通话结束，麦克风已关闭。');});
  controls();
})();
