"""小白 2080：Python 标准库服务端，支持文字、录音转写和语音回答。"""
import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = Path(__file__).resolve().parent
KEY = os.environ.get('OPENAI_API_KEY', '').strip()
MODEL = os.environ.get('OPENAI_MODEL', 'gpt-6').strip()
TRANSCRIBE_MODEL = os.environ.get('OPENAI_TRANSCRIBE_MODEL', 'gpt-4o-mini-transcribe')
SPEECH_MODEL = os.environ.get('OPENAI_SPEECH_MODEL', 'gpt-4o-mini-tts')
MAX_AUDIO_BYTES = 8 * 1024 * 1024
AUDIO_SLOTS = threading.BoundedSemaphore(2)
SYSTEM="""你是2080年华中师范大学原型未来校园的智能教育伙伴“小白”，陪伴19岁的华诗诗。用自然、有温度、清醒、不过度煽情的简体中文交谈。你不是客服，也不是套话机器人。优先理解用户当下真实问题，回答要有内容、准确、具体；如果是学术问题，认真解释和举例；如果是情绪问题，先尊重感受，避免未经许可的心理诊断，再提供可选的微小行动；如果是人生探索，不替学生下结论，鼓励低风险真实探索。允许不同意、追问、纠错和拒绝。不要每次都强行问问题，也不要每次都提到2080或诗诗。对于不确定的事实说明不确定。不得声称已读取设备传感器、隐私或校园数据。默认回复简洁但有深度，必要时分步骤。"""
MODULES = {
    'general': '当前是综合对话，先澄清需求，再由学生选择下一步。',
    'learning': '当前是学业领航：定位卡点、讲解概念、提供核验方法和小练习；不代写完整作业，不编造资料来源。',
    'growth': '当前是成长发展：比较兴趣方向、设计低风险实践、整理真实证据；任务建议不等于已完成成果，不擅自公开档案。',
    'experience': '当前是情感陪伴：先倾听，询问是否需要建议；允许沉默和暂停，不强迫转成任务，不作医学诊断。',
    'status': '当前是生活助手：澄清时间与优先级，给出备选安排；未经本人确认不能声称修改、预约或发送。',
}
AUDIO_TYPES = {'audio/webm': 'webm', 'video/webm': 'webm', 'audio/mp4': 'mp4',
               'audio/x-m4a': 'm4a', 'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/ogg': 'ogg'}


def request_upstream(path, body, content_type='application/json', timeout=75):
    request = urllib.request.Request('https://api.openai.com/v1/' + path, data=body,
        headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': content_type}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class BadRequest(ValueError):
    pass


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, obj):
        self.send_bytes(status, json.dumps(obj, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def read_body(self, limit):
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise BadRequest('请求长度不正确')
        if not 0 < size <= limit:
            raise BadRequest('请求为空或超过大小限制')
        body = self.rfile.read(size)
        if len(body) != size:
            raise BadRequest('请求未完整上传')
        return body

    def read_json(self):
        try:
            data = json.loads(self.read_body(100000))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise BadRequest('请发送有效的 JSON')
        if not isinstance(data, dict):
            raise BadRequest('请求需要是对象')
        return data

    def do_GET(self):
        if self.path == '/api/status':
            return self.send_json(200, {'ready': bool(KEY), 'model': MODEL if KEY else None,
                'voice': {'transcribe': bool(KEY), 'speech': bool(KEY)}})
        return super().do_GET()

    def do_POST(self):
        if self.path not in ('/api/chat', '/api/transcribe', '/api/speech'):
            return self.send_json(404, {'error': 'Not found'})
        if not KEY:
            return self.send_json(503, {'error': '模型服务尚未配置；可以继续使用文字演示与设备朗读。'})
        audio = self.path != '/api/chat'
        acquired = not audio or AUDIO_SLOTS.acquire(blocking=False)
        if not acquired:
            return self.send_json(429, {'error': '语音正在处理其他请求，请稍后重试。'})
        try:
            if self.path == '/api/chat':
                return self.chat()
            if self.path == '/api/transcribe':
                return self.transcribe()
            return self.speech()
        except BadRequest as exc:
            return self.send_json(400, {'error': str(exc)})
        except urllib.error.HTTPError as exc:
            # Never print upstream bodies: authentication errors may echo credential material.
            print('Upstream request failed:', self.path, exc.code, flush=True)
            return self.send_json(502, {'error': '模型服务暂时不可用（HTTP %s），请稍后重试。' % exc.code})
        except (TimeoutError, urllib.error.URLError):
            return self.send_json(504, {'error': '连接超时，请检查网络后重试；已输入文字不会丢失。'})
        except Exception as exc:
            print('Request failed:', self.path, type(exc).__name__, flush=True)
            return self.send_json(500, {'error': '服务暂时无法响应，请稍后重试。'})
        finally:
            if audio and acquired:
                AUDIO_SLOTS.release()

    def chat(self):
        data = self.read_json()
        messages = data.get('messages', [])
        if not isinstance(messages, list):
            raise BadRequest('messages 格式不正确')
        cleaned = [{'role': m['role'], 'content': m['content'][:4000]} for m in messages[-24:]
                   if isinstance(m, dict) and m.get('role') in ('user', 'assistant')
                   and isinstance(m.get('content'), str) and m['content'].strip()]
        if not cleaned or cleaned[-1]['role'] != 'user':
            raise BadRequest('请发送问题')
        module = data.get('module', 'general')
        if not isinstance(module, str) or module not in MODULES:
            raise BadRequest('未知对话情境')
        payload = {'model': MODEL, 'instructions': SYSTEM + '\n' + MODULES[module],
                   'input': cleaned, 'max_output_tokens': 900}
        result = json.loads(request_upstream('responses', json.dumps(payload).encode()))
        parts = [c.get('text', '') for item in result.get('output', []) if item.get('type') == 'message'
                 for c in item.get('content', []) if c.get('type') == 'output_text']
        answer = '\n'.join(parts).strip() or result.get('output_text', '')
        if not answer:
            raise ValueError('Empty model response')
        return self.send_json(200, {'reply': answer})

    def transcribe(self):
        mime = self.headers.get('Content-Type', '').split(';')[0].strip().lower()
        if mime not in AUDIO_TYPES:
            raise BadRequest('不支持的录音格式，请使用 MP4、WebM、MP3、WAV 或 Ogg')
        audio = self.read_body(MAX_AUDIO_BYTES)
        boundary = 'xiaobai-' + uuid.uuid4().hex
        parts = []
        for name, value in [('model', TRANSCRIBE_MODEL), ('language', 'zh')]:
            parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n' + value + '\r\n').encode())
        parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="recording.' + AUDIO_TYPES[mime] + '"\r\nContent-Type: ' + mime + '\r\n\r\n').encode())
        parts.extend([audio, ('\r\n--' + boundary + '--\r\n').encode()])
        result = json.loads(request_upstream('audio/transcriptions', b''.join(parts),
                            'multipart/form-data; boundary=' + boundary, timeout=60))
        text = result.get('text', '').strip()
        if not text:
            raise BadRequest('没有识别到清晰语音，请重新录制或直接打字')
        return self.send_json(200, {'text': text[:4000]})

    def speech(self):
        data = self.read_json()
        text = data.get('text', '')
        voice = data.get('voice', 'cedar')
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 1000:
            raise BadRequest('语音文字需要在 1—1000 字之间')
        if voice not in ('cedar', 'marin'):
            raise BadRequest('请选择支持的声音')
        payload = {'model': SPEECH_MODEL, 'input': text.strip(), 'voice': voice, 'response_format': 'mp3',
            'instructions': '用自然、清晰的简体中文朗读，像温和、平等的校园伙伴。语速适中，克制、不夸张，不要增加原文没有的内容。'}
        audio = request_upstream('audio/speech', json.dumps(payload).encode(), timeout=60)
        return self.send_bytes(200, audio, 'audio/mpeg')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    print('小白服务已启动，端口 %s' % port, flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
