"""Run with: python3 -m unittest discover -s tests -v (requires Playwright Chromium)."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from playwright.sync_api import sync_playwright


class Workflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1180, 'height': 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('dialog', lambda d: d.accept())
        self.page.route('**/api/status', lambda r: r.fulfill(json={'ready': False, 'model': None}))
        self.page.goto(self.url)

    def tearDown(self):
        errors = self.errors[:]
        self.context.close()
        self.assertEqual(errors, [])

    def go(self, ident):
        self.page.evaluate('(id) => go(id)', ident)

    def test_names_and_order_everywhere(self):
        expected = ['学业领航', '成长发展', '情感陪伴', '生活助手']
        self.assertEqual(self.page.locator('.nav button').all_text_contents()[1:5], expected)
        self.assertEqual(self.page.locator('.hub-module strong').all_text_contents(), expected)
        self.assertEqual(self.page.locator('main > section').evaluate_all('(els)=>els.map(e=>e.id)'), ['chat', 'learning', 'growth', 'experience', 'status', 'settings'])
        self.assertNotRegex(self.page.content(), '辅助学习|引导探索')
        for ident in ['learning', 'growth', 'experience', 'status']:
            self.page.locator(f'.nav [data-page="{ident}"]').click()
            self.assertTrue(self.page.locator('#'+ident).is_visible())
        self.assertEqual(self.page.locator('#hubProgressLabel').text_content(), '4 / 4 个模块已浏览')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '0')
        self.assertEqual(self.page.locator('#count').text_content(), '0 / 4')

    def test_academic_panels_and_cross_module_link(self):
        self.go('learning')
        self.assertTrue(self.page.locator('#studyPlanPanel').is_visible())
        self.assertFalse(self.page.locator('#libraryPanel').is_visible())
        self.page.locator('[data-learning-feature="library"]').click()
        self.assertTrue(self.page.locator('#libraryPanel').is_visible())
        self.assertFalse(self.page.locator('#studyPlanPanel').is_visible())
        self.page.locator('[data-learning-feature="trace"]').click()
        self.page.locator('[data-learning-jump="growth"]').click()
        self.assertTrue(self.page.locator('#growth').is_visible())
        self.assertFalse(self.page.locator('#learning').is_visible())

    def test_plan_checkmarks_restore_without_duplicate_review(self):
        self.go('learning')
        self.page.fill('#learnGoal', '理解校园空间研究中的日照分析')
        self.page.click('#makeStudyPlan')
        self.page.locator('[data-plan-step]').nth(0).check()
        self.page.click('#saveStudyPlan')
        self.page.reload()
        self.go('learning')
        self.assertEqual(self.page.input_value('#learnGoal'), '理解校园空间研究中的日照分析')
        self.assertTrue(self.page.locator('[data-plan-step]').nth(0).is_checked())
        for checkbox in self.page.locator('[data-plan-step]').all():
            checkbox.check()
        self.page.locator('[data-plan-step]').nth(1).uncheck()
        self.assertFalse(self.page.locator('#studyPlanReview').is_visible())
        self.page.locator('[data-plan-step]').nth(1).check()
        self.assertEqual(self.page.locator('#studyPlanReview').count(), 1)

    def test_confirmed_learning_evidence_reaches_growth_once(self):
        self.go('learning')
        self.page.fill('#learnGoal', '完成校园日照观察')
        self.page.click('#makeStudyPlan')
        for checkbox in self.page.locator('[data-plan-step]').all():
            checkbox.check()
        self.page.click('#archiveStudyOutcome')
        self.assertIn('至少10个字', self.page.locator('#studyArchiveStatus').inner_text())
        self.assertIsNone(self.page.evaluate("localStorage.getItem('xb2080_confirmed_learning_v1')"))
        self.page.fill('#studyOutcome', '我观察了三个地点的日照差异，下一步会增加下午时段的对照记录。')
        self.page.click('#archiveStudyOutcome')
        self.page.click('#archiveStudyOutcome')
        self.assertIn('无需重复', self.page.locator('#studyArchiveStatus').inner_text())
        self.page.reload()
        self.go('growth')
        self.assertEqual(self.page.locator('#learningEvidenceList article').count(), 1)
        self.assertIn('三个地点', self.page.locator('#learningEvidenceList').inner_text())
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '0')
        self.page.locator('#learningEvidenceList button').click()
        self.page.reload()
        self.go('growth')
        self.assertEqual(self.page.locator('#learningEvidenceList article').count(), 0)

    def test_learning_trace_captured_once(self):
        self.go('learning')
        self.page.locator('[data-learning-feature="think"]').click()
        self.page.click('#copilotLearningEntry')
        self.page.fill('#chatText', '我知道日照原理，但不会验证模型')
        self.page.locator('#chatForm button').click()
        rows = self.page.evaluate("JSON.parse(localStorage.getItem('xb2080_learning_trace_v1'))")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['text'], '我知道日照原理，但不会验证模型')
        self.go('learning')
        self.page.locator('[data-learning-feature="trace"]').click()
        self.page.wait_for_selector('#learningTraceItems')
        self.assertIn('日照原理', self.page.locator('#learningTraceItems').inner_text())

    def test_exploration_requires_actual_result_and_deduplicates(self):
        self.go('growth')
        self.page.evaluate('gxChoosePath(0)')
        before = self.page.input_value('#talentPortfolio')
        self.page.click('#gxToTalent')
        self.assertEqual(self.page.input_value('#talentPortfolio'), before)
        self.assertIn('请先完成实践', self.page.locator('#gxRecordStatus').inner_text())
        self.page.fill('#gxOutcome', '我在图书馆外观察了三个停留点，并记录树荫与座位对交流的影响。')
        self.page.click('#gxSaveTrace')
        self.page.click('#gxSaveTrace')
        rows = self.page.evaluate("JSON.parse(localStorage.getItem('xb2080_exploration_trace_v1'))")
        self.assertEqual(len(rows), 1)
        self.page.click('#gxToTalent')
        self.assertIn('观察了三个停留点', self.page.input_value('#talentPortfolio'))
        self.assertFalse(self.page.locator('#talentEmployerConsent').is_checked())
        self.page.reload()
        self.go('growth')
        self.assertIn('观察了三个停留点', self.page.locator('#explorationRecordList').inner_text())

    def test_growth_requires_evidence_and_persists_points(self):
        self.go('growth')
        self.page.locator('#growthIncentives').evaluate('(e)=>e.closest("details").open=true')
        button = self.page.locator('#growthExplores button').first
        button.click()
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '0')
        self.page.locator('#growthExplores textarea').first.fill('我观察了三个校园座位，记录使用时间与人群，并写下一个需要继续验证的问题。')
        button.click()
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '60')
        self.page.reload()
        self.go('growth')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '60')
        self.assertTrue(self.page.locator('#growthExplores button').first.is_disabled())
        self.assertIn('观察了三个', self.page.locator('#growthExplores textarea').first.input_value())

    def test_all_four_scenarios_reachable_without_duplicate_awards(self):
        self.page.evaluate('for(let i=0;i<4;i++)completeModuleExperience(i)')
        self.assertEqual(self.page.locator('#count').text_content(), '4 / 4')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '240')
        self.page.evaluate('for(let i=0;i<4;i++)completeModuleExperience(i)')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '240')
        self.page.reload()
        self.assertEqual(self.page.locator('#count').text_content(), '4 / 4')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '240')
        self.page.evaluate('resetRecords()')
        self.assertEqual(self.page.locator('#count').text_content(), '0 / 4')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '0')

    def test_consent_does_not_auto_grant_and_withdrawal_survives_reload(self):
        self.go('growth')
        self.page.locator('#talentEmployerConsent').click()
        self.assertFalse(self.page.locator('#talentSchoolConsent').is_checked())
        self.assertFalse(self.page.locator('#talentEmployerConsent').is_checked())
        self.page.fill('#talentSkills', '校园日照测试')
        self.page.fill('#talentPortfolio', '独立整理校园日照观察成果')
        self.page.locator('#talentSchoolConsent').check()
        self.page.locator('#talentEmployerConsent').check()
        self.page.evaluate('saveTalentProfile()')
        self.page.locator('#enterpriseSimulation').evaluate('(e)=>e.open=true')
        self.page.fill('#talentJobQuery', '校园日照测试')
        self.page.evaluate('searchTalentMatches()')
        self.assertIn('当前用户', self.page.locator('#talentMatchResults').inner_text())
        self.page.locator('#talentEmployerConsent').uncheck()
        self.page.reload()
        self.go('growth')
        self.assertFalse(self.page.locator('#talentEmployerConsent').is_checked())
        self.page.locator('#enterpriseSimulation').evaluate('(e)=>e.open=true')
        self.page.fill('#talentJobQuery', '校园日照测试')
        self.page.evaluate('searchTalentMatches()')
        self.assertNotIn('当前用户', self.page.locator('#talentMatchResults').inner_text())

    def test_schedule_draft_requires_confirmation_and_valid_times(self):
        self.go('status')
        before = self.page.evaluate("localStorage.getItem('xb2080_schedule_tasks')")
        self.page.click('#lifeOrchestrateSchedule')
        self.assertIn('草稿', self.page.locator('#dayPlanAdvice').inner_text())
        self.assertEqual(self.page.evaluate("localStorage.getItem('xb2080_schedule_tasks')"), before)
        self.page.fill('#taskStart', '15:00')
        self.page.fill('#taskEnd', '14:00')
        self.page.click('#addTask')
        self.assertEqual(self.page.evaluate("localStorage.getItem('xb2080_schedule_tasks')"), before)
        self.page.fill('#taskEnd', '16:00')
        self.page.click('#addTask')
        self.assertIsNotNone(self.page.evaluate("localStorage.getItem('xb2080_schedule_tasks')"))

    def test_evidence_can_reach_aid_threshold_without_repeated_clicks(self):
        self.go('growth')
        for group in ['growthArchives', 'growthExplores', 'growthPractices']:
            if group=='growthExplores':
                self.page.locator('#growthIncentives').evaluate('(e)=>e.closest("details").open=true')
            cards = self.page.locator('#'+group+' .growth-item')
            for card in cards.all():
                card.locator('textarea').fill('我完成了校园观察与资料核对，留下问题、行动过程、反馈以及下一次要验证的方向。')
                card.locator('button').click()
        self.page.evaluate('for(let i=0;i<4;i++)completeModuleExperience(i)')
        self.assertEqual(self.page.locator('#growthPoints').text_content(), '1200')
        self.assertIn('达到', self.page.locator('#aidStatus').text_content())

    def test_emotional_chat_accepts_multiple_turns(self):
        self.page.evaluate("openCopilot('experience')")
        for message in ['我今天有点累', '我想先休息一下']:
            self.page.fill('#chatText', message)
            self.page.locator('#chatForm button[type=submit]').click()
            self.page.wait_for_function('!document.getElementById("chatText").disabled')
        self.assertEqual(self.page.locator('#chatMessages .msg.user').count(), 2)
        self.assertEqual(self.page.locator('#chatMessages .msg.bot').count(), 3)

    def test_step_targets_and_mobile_width(self):
        for ident in ['learning', 'growth', 'experience', 'status']:
            self.go(ident)
            buttons = self.page.locator('#'+ident+' .module-path button')
            for button in buttons.all():
                target = button.get_attribute('data-module-target')
                self.assertEqual(self.page.locator('#'+target).count(), 1, target)
                button.click()
                self.assertTrue(self.page.locator('#'+target).is_visible(), target)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        for ident in ['chat', 'learning', 'growth', 'experience', 'status']:
            self.go(ident)
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 392, ident)


if __name__ == '__main__':
    unittest.main()
