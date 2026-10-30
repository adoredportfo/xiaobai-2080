import unittest
import test_browser_workflows as harness


FAKE_WEBRTC = '''
window.rtTracks=[];window.rtPeers=[];window.rtSent=[];
Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
 const track={enabled:true,stopped:false,stop(){this.stopped=true}};window.rtTracks.push(track);
 return {getTracks:()=>[track],getAudioTracks:()=>[track]};
}});
window.RTCPeerConnection=class {
 constructor(){this.connectionState='new';window.rtPeers.push(this)}
 addTrack(track){this.track=track}
 createDataChannel(){this.channel={readyState:'connecting',send:data=>window.rtSent.push(JSON.parse(data)),close(){this.readyState='closed'}};return this.channel}
 async createOffer(){return {type:'offer',sdp:'mock-offer-sdp'}}
 async setLocalDescription(o){this.localDescription=o}
 async setRemoteDescription(o){this.answer=o;this.connectionState='connected';this.channel.readyState='open';this.channel.onopen?.();this.onconnectionstatechange?.()}
 close(){this.closed=true;this.connectionState='closed'}
};
window.rtEmit=e=>window.rtPeers.at(-1).channel.onmessage({data:JSON.stringify(e)});
'''


class RealtimeBrowser(unittest.TestCase):
    setUpClass = classmethod(harness.Workflows.setUpClass.__func__)
    tearDownClass = classmethod(harness.Workflows.tearDownClass.__func__)
    setUp = harness.Workflows.setUp
    tearDown = harness.Workflows.tearDown
    go = harness.Workflows.go

    def prepare(self, script=FAKE_WEBRTC):
        self.page.add_init_script(script)
        self.page.unroute('**/api/status')
        self.page.route('**/api/status', lambda r:r.fulfill(json={'ready':True,'voice':{'speech':True,'transcribe':True,'realtime':True}}))
        self.session_requests=[]
        def session(route):
            self.session_requests.append(route.request.post_data_json)
            route.fulfill(json={'client_secret':'ek_ephemeral_test','expires_at':123,'model':'gpt-realtime-mini'})
        self.page.route('**/api/realtime/session',session)
        self.call_urls=[]
        def answer(route):
            self.call_urls.append(route.request.url)
            route.fulfill(body='mock-answer-sdp',content_type='application/sdp')
        self.page.route('https://api.openai.com/v1/realtime/calls*',answer)
        self.page.reload()

    def connect(self):
        self.page.click('#realtimeStart')
        self.page.wait_for_function("document.getElementById('realtimeBadge').textContent==='已连接'")

    def test_continuous_turns_transcripts_and_interrupt(self):
        self.prepare()
        self.page.evaluate("openCopilot('learning')")
        self.connect()
        self.assertEqual(self.session_requests,[{'module':'learning','voice':'cedar'}])
        self.assertIn('?model=gpt-realtime-mini',self.call_urls[0])
        self.assertTrue(self.page.locator('#chatText').is_disabled())
        self.assertTrue(self.page.locator('#voiceRecord').is_disabled())
        for i in range(2):
            self.page.evaluate('''i=>{
              rtEmit({type:'input_audio_buffer.speech_started',item_id:'u'+i});
              rtEmit({type:'conversation.item.input_audio_transcription.completed',item_id:'u'+i,transcript:'问题'+i});
              rtEmit({type:'response.created'});
              rtEmit({type:'response.output_audio_transcript.delta',item_id:'a'+i,delta:'回答'+i});
              rtEmit({type:'response.output_audio_transcript.done',item_id:'a'+i,transcript:'回答'+i});
              rtEmit({type:'output_audio_buffer.stopped'});
            }''',i)
        self.assertIn('问题0',self.page.locator('#realtimeCaptions').inner_text())
        self.assertIn('回答1',self.page.locator('#realtimeCaptions').inner_text())
        self.page.evaluate("rtEmit({type:'response.created'})")
        self.page.click('#realtimeInterrupt')
        events=self.page.evaluate('rtSent.map(e=>e.type)')
        self.assertIn('response.cancel',events)
        self.assertIn('output_audio_buffer.clear',events)
        self.page.click('#realtimeEnd')
        self.assertTrue(self.page.evaluate('rtTracks.every(t=>t.stopped)'))
        self.assertTrue(self.page.evaluate('rtPeers.every(p=>p.closed)'))
        self.assertTrue(self.page.locator('#chatText').is_enabled())

    def test_mute_and_leave_page_close_microphone(self):
        self.prepare();self.connect()
        self.page.click('#realtimeMute')
        self.assertFalse(self.page.evaluate('rtTracks[0].enabled'))
        self.assertEqual(self.page.locator('#realtimeMute').get_attribute('aria-pressed'),'true')
        self.page.click('#realtimeMute')
        self.assertTrue(self.page.evaluate('rtTracks[0].enabled'))
        self.go('growth')
        self.assertTrue(self.page.evaluate('rtTracks.every(t=>t.stopped)'))
        self.assertEqual(self.page.locator('#realtimeBadge').text_content(),'未连接')

    def test_failed_bootstrap_cleans_up(self):
        self.prepare()
        self.page.unroute('**/api/realtime/session')
        self.page.route('**/api/realtime/session',lambda r:r.fulfill(status=502,json={'error':'unavailable'}))
        self.page.click('#realtimeStart')
        self.page.wait_for_function("document.getElementById('realtimeStatus').textContent.includes('暂时失败')")
        self.assertTrue(self.page.evaluate('rtTracks.every(t=>t.stopped)'))
        self.assertTrue(self.page.locator('#chatText').is_enabled())
        self.assertTrue(self.page.locator('#realtimeStart').is_visible())

    def test_cancel_during_delayed_permission_does_not_leak_mic(self):
        script=FAKE_WEBRTC+'''
        Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:()=>new Promise(resolve=>window.resolveMic=resolve),configurable:true});
        '''
        # Redefinition is permitted by the configurable descriptor in this test stub.
        script=script.replace("value:async()=>{", "configurable:true,value:async()=>{",1)
        self.prepare(script)
        self.page.click('#realtimeStart')
        self.page.click('#realtimeEnd')
        self.page.evaluate("()=>{window.lateTrack={stopped:false,stop(){this.stopped=true}};resolveMic({getTracks:()=>[lateTrack],getAudioTracks:()=>[lateTrack]})}")
        self.page.wait_for_function('lateTrack.stopped')
        self.assertEqual(self.session_requests,[])
        self.assertEqual(self.page.locator('#realtimeBadge').text_content(),'未连接')

    def test_network_failure_and_background_end_session(self):
        self.prepare();self.connect()
        self.page.evaluate("()=>{const p=rtPeers.at(-1);p.connectionState='failed';p.onconnectionstatechange()}")
        self.assertTrue(self.page.evaluate('rtTracks.every(t=>t.stopped)'))
        self.connect()
        self.page.evaluate("()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))}")
        self.assertTrue(self.page.evaluate('rtTracks.every(t=>t.stopped)'))
        self.assertEqual(self.page.locator('#realtimeBadge').text_content(),'未连接')
