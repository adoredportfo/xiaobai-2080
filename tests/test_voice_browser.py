import unittest
import test_browser_workflows as harness


class VoiceWorkflows(unittest.TestCase):
    setUpClass = classmethod(harness.Workflows.setUpClass.__func__)
    tearDownClass = classmethod(harness.Workflows.tearDownClass.__func__)
    setUp = harness.Workflows.setUp
    tearDown = harness.Workflows.tearDown
    go = harness.Workflows.go

    # Own cases use the same real-browser harness, with microphone/audio devices mocked.
    def ready_voice(self):
        self.page.unroute('**/api/status')
        self.page.route('**/api/status', lambda r: r.fulfill(json={'ready': True, 'voice': {'transcribe': True, 'speech': True}}))
        self.page.reload()
        self.page.wait_for_function("document.querySelector('.ai-banner').textContent.includes('已配置')")
        self.page.locator('.voice-fallback').evaluate('(e)=>e.open=true')

    def test_shared_context_preserves_separate_conversations(self):
        self.page.evaluate("openCopilot('learning','我需要理解日照分析')")
        self.page.click('#chatForm button')
        before = self.page.locator('#chatMessages').inner_text()
        self.page.evaluate("openCopilot('experience')")
        self.assertNotIn('理解日照分析', self.page.locator('#chatMessages').inner_text())
        self.page.evaluate("openCopilot('learning')")
        self.assertEqual(before, self.page.locator('#chatMessages').inner_text())
        self.page.click('[data-copilot-action="learning"]')
        self.assertEqual(self.page.input_value('#learnGoal'), '我需要理解日照分析')

    def test_optional_tools_start_collapsed(self):
        self.go('growth')
        self.assertFalse(self.page.locator('#growthExplores').is_visible())
        self.assertTrue(self.page.locator('#growthArchives').is_visible())
        self.assertFalse(self.page.locator('#talentJobQuery').is_visible())
        self.go('status')
        self.assertFalse(self.page.locator('#lifeNutritionPanel').is_visible())
        self.page.locator('[data-module-target="lifeNutritionPanel"]').click()
        self.assertTrue(self.page.locator('#lifeNutritionPanel').is_visible())

    def test_recording_requires_confirmation_and_never_auto_sends(self):
        self.page.add_init_script('''
        window.testMicClosed = 0;
        Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>({getTracks:()=>[{stop:()=>window.testMicClosed++}]})});
        window.MediaRecorder=class {
          static isTypeSupported(){return true}
          constructor(){this.state='inactive';this.mimeType='audio/mp4'}
          start(){this.state='recording'}
          stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['test'],{type:'audio/mp4'})});this.onstop?.()}
        };
        ''')
        self.ready_voice()
        transcriptions = []
        chats = []
        self.page.route('**/api/transcribe', lambda r: (transcriptions.append(r.request.post_data_buffer), r.fulfill(json={'text':'我想研究校园光照'})))
        self.page.route('**/api/chat', lambda r: (chats.append(r.request.post_data), r.fulfill(json={'reply':'先从一个观察点开始。'})))
        self.page.click('#voiceRecord')
        self.assertIn('正在录音', self.page.locator('#voiceStatus').inner_text())
        self.page.click('#voiceRecord')
        self.assertEqual(transcriptions, [])
        self.assertEqual(chats, [])
        self.assertGreater(self.page.evaluate('window.testMicClosed'), 0)
        self.page.click('#voiceTranscribe')
        self.page.wait_for_function("document.getElementById('chatText').value.includes('校园光照')")
        self.assertEqual(len(transcriptions), 1)
        self.assertEqual(chats, [])
        self.page.click('#chatForm button')
        self.page.wait_for_function("document.getElementById('chatMessages').textContent.includes('观察点')")
        self.assertEqual(len(chats), 1)

    def test_microphone_denied_keeps_text_chat_available(self):
        self.page.add_init_script("Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{throw new DOMException('denied','NotAllowedError')}})")
        self.ready_voice()
        self.page.click('#voiceRecord')
        self.page.wait_for_function("document.getElementById('voiceStatus').textContent.includes('权限未开启')")
        self.assertTrue(self.page.locator('#chatText').is_enabled())
        self.assertTrue(self.page.locator('#voiceRecord').is_enabled())

    def test_speech_is_opt_in_and_stop_aborts_generation(self):
        self.ready_voice()
        self.page.route('**/api/chat', lambda r:r.fulfill(json={'reply':'我们先确定你想完成的一个小目标。'}))
        self.page.evaluate('''()=>{window.voiceSpeechCalls=0;const original=window.fetch;window.fetch=(url,opts)=>url==='/api/speech'?new Promise((resolve,reject)=>{window.voiceSpeechCalls++;opts.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')))}):original(url,opts)}''')
        self.page.fill('#chatText','你好')
        self.page.click('#chatForm button')
        self.page.wait_for_function("!document.getElementById('chatText').disabled")
        self.assertEqual(self.page.evaluate('window.voiceSpeechCalls'), 0)
        self.page.click('#voicePlay')
        self.page.wait_for_function("document.getElementById('voiceStatus').textContent.includes('正在生成')")
        self.page.click('#voiceStop')
        self.assertEqual(self.page.locator('#voiceStatus').inner_text(), '语音已停止。')
        self.page.wait_for_timeout(50)
