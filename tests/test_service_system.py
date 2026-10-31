"""Shared tasks, service states and dated handoffs; no external APIs invoked."""
import unittest
import test_browser_workflows as browser


class ServiceSystem(browser.Workflows):
    def create_task(self):
        self.go('learning')
        self.page.fill('#ss-title', '校园空间体验研究')
        self.page.fill('#ss-deliverable', '三次观察与一份修订方案')
        self.page.fill('#ss-criterion', '使用两个现场证据解释方案取舍')
        self.page.fill('#ss-budget', '25')
        self.page.locator('#ss-create button').click()

    def record_outcome(self):
        self.page.locator('#ss-log').evaluate('(e)=>e.closest("details").open=true')
        self.page.fill('#ss-attempt', '比较了三个校园空间的停留情况')
        self.page.fill('#ss-result', '两处有树荫的空间停留更久，需要控制时段差异')
        self.page.fill('#ss-next', '再观察下午时段并核验原因')
        self.page.locator('#ss-log button').click()
        self.go('growth')
        self.page.fill('#ss-outcome-text', '我观察了三个校园空间并记录不同时间的停留情况，形成问题地图。')
        self.page.fill('#ss-outcome-check', '已有两处现场证据，仍缺下午时段的验证')
        self.page.locator('#ss-outcome button').click()

    def saved(self):
        return self.page.evaluate("JSON.parse(localStorage.getItem('xb2080_service_system_v1'))")

    def test_shared_task_evidence_feedback_revision_and_persistence(self):
        self.create_task()
        self.record_outcome()
        self.page.locator('[data-ss="teacher-request"]').click()
        self.page.locator('#ss-feedback-view [data-ss="simulate-next"]').click()
        self.page.locator('#ss-feedback-view [data-ss="simulate-next"]').click()
        self.assertIn('非真实教师', self.page.locator('#ss-feedback-view').inner_text())
        self.go('learning')
        self.page.locator('#ss-revise').evaluate('(e)=>e.closest("details").open=true')
        self.page.fill('#ss-revised-steps', '补充下午观察\n对比已有结论\n修订方案')
        self.page.fill('#ss-revise-reason', '导师模拟反馈提示证据仍有局限')
        self.page.locator('#ss-revise button').click()
        self.page.reload()
        self.go('learning')
        self.page.locator('#ss-revise').evaluate('(e)=>e.closest("details").open=true')
        self.assertIn('补充下午观察', self.page.locator('#ss-revisions').inner_text())
        self.assertEqual(len(self.saved()['tasks']), 1)
        self.assertEqual(len(self.saved()['tasks'][0]['feedback']), 1)
        self.assertFalse(any(x['done'] for x in self.saved()['tasks'][0]['steps']))

    def test_dates_conflicts_adjustment_and_cancellation(self):
        self.create_task()
        self.go('status')
        self.page.fill('#ss-event-start', '10:00')
        self.page.fill('#ss-event-end', '11:00')
        self.page.locator('#ss-event button').click()
        self.page.fill('#ss-event-start', '10:30')
        self.page.fill('#ss-event-end', '11:30')
        self.page.locator('#ss-event button').click()
        self.assertEqual(len(self.saved()['events']), 1)
        self.assertIn('已有安排', self.page.locator('#ss-status .ss-notice').inner_text())
        self.page.locator('#ss-adjust-event').evaluate('(e)=>e.closest("details").open=true')
        self.page.select_option('#ss-adjust-event', self.saved()['events'][0]['id'])
        self.page.fill('#ss-adjust-start', '13:00')
        self.page.fill('#ss-adjust-end', '14:00')
        self.page.locator('[data-ss="preview-adjust"]').click()
        self.assertEqual(self.saved()['events'][0]['start'], '10:00')
        self.page.locator('[data-ss="confirm-adjust"]').click()
        self.assertEqual(self.saved()['events'][0]['start'], '13:00')
        self.page.locator('#ss-calendar [data-ss="event-delete"]').click()
        self.assertEqual(self.saved()['events'], [])
        self.page.locator('[data-ss="undo-event"]').click()
        self.assertEqual(self.saved()['events'][0]['start'], '13:00')

    def test_booking_accept_fail_retry_cancel_tracks_calendar(self):
        self.create_task()
        self.go('status')
        self.page.locator('#ss-booking').evaluate('(e)=>e.closest("details").open=true')
        self.page.fill('#ss-book-start', '09:00')
        self.page.fill('#ss-book-end', '10:00')
        self.page.check('#ss-book-consent')
        self.page.locator('#ss-booking button').click()
        self.assertEqual(self.saved()['events'], [])
        self.page.locator('#ss-bookings [data-ss="simulate-next"]').click()
        self.assertEqual(len(self.saved()['events']), 1)
        self.page.locator('#ss-bookings [data-ss="simulate-fail"]').click()
        self.assertEqual(self.saved()['events'], [])
        self.page.locator('#ss-bookings [data-ss="retry-request"]').click()
        self.page.locator('#ss-bookings [data-ss="simulate-next"]').click()
        self.page.locator('#ss-bookings [data-ss="cancel-request"]').click()
        self.assertEqual(self.saved()['events'], [])
        self.assertEqual(self.saved()['requests'][0]['status'], 'cancelled')

    def test_application_requires_evidence_and_explicit_consent(self):
        self.create_task()
        self.go('growth')
        self.page.locator('#ss-apply').evaluate('(e)=>e.closest("details").open=true')
        self.page.fill('#ss-application', '我想参与校园空间共创，已进行观察，希望进一步学习。')
        self.page.locator('#ss-apply button').click()
        self.assertEqual(self.saved()['requests'], [])
        self.go('learning')
        self.record_outcome()
        self.page.check('#ss-application-consent')
        self.page.locator('#ss-apply button').click()
        self.assertEqual(self.saved()['requests'][0]['status'], 'pending')
        self.page.locator('#ss-application-list [data-ss="simulate-next"]').click()
        self.page.locator('#ss-application-list [data-ss="simulate-next"]').click()
        self.assertIn('不是录用通知', self.page.locator('#ss-application-list').inner_text())

    def test_context_is_only_draft_and_does_not_read_private_journal(self):
        self.create_task()
        self.page.evaluate("localStorage.setItem('xiaobai_emotion_support_log', JSON.stringify([{text:'PRIVATE_JOURNAL_SENTINEL'}]))")
        self.page.locator('[data-ss="chat"]').evaluate('(e)=>e.closest("details").open=true')
        self.page.locator('[data-ss="chat"]').click()
        self.assertIn('校园空间体验研究', self.page.input_value('#chatText'))
        self.assertNotIn('PRIVATE_JOURNAL', self.page.input_value('#chatText'))
        self.assertEqual(self.page.locator('#chatMessages .msg.user').count(), 0)

    def test_xss_import_rejected_and_storage_failure_does_not_erase_input(self):
        self.create_task()
        self.go('status')
        self.page.locator('#ss-import').evaluate('(e)=>e.closest("details").open=true')
        self.page.set_input_files('#ss-import', {'name':'bad.json','mimeType':'application/json','buffer':b'{"version":1,"tasks":[{}]}'})
        self.assertEqual(len(self.saved()['tasks']), 1)
        self.assertIn('格式无效', self.page.locator('#ss-status .ss-notice').inner_text())
        self.go('learning')
        self.page.evaluate("() => { Storage.prototype.setItem = () => {throw new Error('quota')}; }")
        self.page.fill('#ss-title', '尚未保存的目标')
        self.page.fill('#ss-deliverable', '证据')
        self.page.fill('#ss-criterion', '检查')
        self.page.locator('#ss-create button').click()
        self.assertEqual(self.page.input_value('#ss-title'), '尚未保存的目标')
        self.assertEqual(len(self.saved()['tasks']), 1)

    def test_shared_workspace_tablet_and_phone_widths(self):
        self.create_task()
        for width, height in [(820,1180),(1180,820),(390,844)]:
            self.page.set_viewport_size({'width':width,'height':height})
            for section in ['learning','growth','experience','status']:
                self.go(section)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width+2)

    def test_backup_roundtrip_requires_preview_and_rejects_unsafe_links(self):
        import json
        self.create_task()
        original = self.saved()
        self.go('status')
        self.page.locator('#ss-import').evaluate('(e)=>e.closest("details").open=true')
        original['tasks'][0]['title'] = '<img src=x onerror=alert(1)>'
        self.page.set_input_files('#ss-import', {'name':'valid.json','mimeType':'application/json','buffer':json.dumps(original).encode()})
        self.assertEqual(self.saved()['tasks'][0]['title'], '校园空间体验研究')
        self.page.locator('[data-ss="confirm-import"]').click()
        self.assertEqual(self.saved()['tasks'][0]['title'], '<img src=x onerror=alert(1)>')
        self.assertEqual(self.page.locator('.ss-workspace img').count(), 0)
        original['tasks'][0]['resources'] = [{'title':'bad','use':'test','url':'javascript:alert(1)'}]
        self.page.set_input_files('#ss-import', {'name':'unsafe.json','mimeType':'application/json','buffer':json.dumps(original).encode()})
        self.assertEqual(self.page.locator('[data-ss="confirm-import"]').count(), 0)
        self.assertEqual(self.saved()['tasks'][0]['resources'], [])

    def test_support_simulation_and_voluntary_followup(self):
        self.go('experience')
        self.page.locator('#ss-support').evaluate('(e)=>e.closest("details").open=true')
        self.page.fill('#ss-support-message', '我希望找一个时间聊聊学习安排。')
        self.page.locator('#ss-support button').click()
        self.assertIsNone(self.saved())
        self.page.check('#ss-support-consent')
        self.page.locator('#ss-support button').click()
        self.page.locator('#ss-support-list [data-ss="simulate-next"]').click()
        self.page.locator('#ss-support-list [data-ss="simulate-next"]').click()
        self.page.locator('#ss-followup').evaluate('(e)=>e.closest("details").open=true')
        self.page.select_option('#ss-helpful', '暂时不需要继续')
        self.page.locator('#ss-followup button').click()
        self.assertEqual(self.saved()['support'][0]['helpful'], '暂时不需要继续')
        self.assertEqual(self.saved()['tasks'], [])

    def test_text_chat_persistence_is_opt_in_and_revocable(self):
        self.page.check('#rememberCopilotChats')
        self.page.fill('#chatText', '我想梳理学习任务')
        self.page.locator('#chatForm button[type=submit]').click()
        self.page.wait_for_function('!document.getElementById("chatText").disabled')
        self.page.reload()
        self.assertTrue(self.page.locator('#rememberCopilotChats').is_checked())
        self.assertIn('我想梳理学习任务', self.page.locator('#chatMessages').inner_text())
        self.page.uncheck('#rememberCopilotChats')
        self.assertIsNone(self.page.evaluate("localStorage.getItem('xb2080_chat_history_optin_v1')"))
        self.page.reload()
        self.assertEqual(self.page.locator('#chatMessages .msg.user').count(), 0)

    def test_learning_route_uses_level_and_available_time(self):
        self.create_task()
        first = self.saved()['tasks'][0]['steps']
        self.page.fill('#ss-title', '验证进阶研究方案')
        self.page.fill('#ss-deliverable', '两个方案与证据对照')
        self.page.fill('#ss-criterion', '能解释不同方案的局限')
        self.page.select_option('#ss-level', '进阶')
        self.page.fill('#ss-budget', '45')
        self.page.locator('#ss-create button').click()
        second = self.saved()['tasks'][1]['steps']
        self.assertNotEqual(first, second)
        self.assertIn('45分钟', second[1]['text'])
        self.assertIn('假设', second[0]['text'])


def load_tests(loader, tests, pattern):
    # Existing workflow coverage runs in its original module, not once per subclass.
    return unittest.TestSuite(ServiceSystem(name) for name in ServiceSystem.__dict__ if name.startswith('test_'))
