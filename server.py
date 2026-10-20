"""小白 2080：仅使用 Python 标准库的最小 AI 服务端。"""
import json, os, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).resolve().parent
KEY=os.environ.get('OPENAI_API_KEY','').strip()
MODEL=os.environ.get('OPENAI_MODEL','gpt-6').strip()
SYSTEM="""你是2080年华中师范大学原型未来校园的智能教育伙伴“小白”，陪伴19岁的华诗诗。用自然、有温度、清醒、不过度煽情的简体中文交谈。你不是客服，也不是套话机器人。优先理解用户当下真实问题，回答要有内容、准确、具体；如果是学术问题，认真解释和举例；如果是情绪问题，先尊重感受，避免未经许可的心理诊断，再提供可选的微小行动；如果是人生探索，不替学生下结论，鼓励低风险真实探索。允许不同意、追问、纠错和拒绝。不要每次都强行问问题，也不要每次都提到2080或诗诗。对于不确定的事实说明不确定。不得声称已读取设备传感器、隐私或校园数据。默认回复简洁但有深度，必要时分步骤。"""
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(BASE),**kw)
 def send_json(self,status,obj):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=='/api/status':return self.send_json(200,{'ready':bool(KEY),'model':MODEL if KEY else None})
  return super().do_GET()
 def do_POST(self):
  if self.path!='/api/chat':return self.send_json(404,{'error':'Not found'})
  if not KEY:return self.send_json(503,{'error':'服务端尚未配置 OPENAI_API_KEY'})
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size<1 or size>100000:return self.send_json(413,{'error':'请求太长'})
   data=json.loads(self.rfile.read(size));msgs=data.get('messages',[])
   if not isinstance(msgs,list):raise ValueError('messages 格式不正确')
   cleaned=[]
   for m in msgs[-24:]:
    if isinstance(m,dict) and m.get('role') in ('user','assistant') and isinstance(m.get('content'),str):cleaned.append({'role':m['role'],'content':m['content'][:4000]})
   if not cleaned or cleaned[-1]['role']!='user':raise ValueError('请发送问题')
   payload={'model':MODEL,'instructions':SYSTEM,'input':cleaned,'max_output_tokens':900}
   req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=75) as resp:result=json.load(resp)
   parts=[]
   for item in result.get('output',[]):
    if item.get('type')=='message':
     for c in item.get('content',[]):
      if c.get('type')=='output_text':parts.append(c.get('text',''))
   answer='\n'.join(parts).strip() or result.get('output_text','')
   if not answer:raise ValueError('模型没有返回可显示的文本')
   return self.send_json(200,{'reply':answer})
  except urllib.error.HTTPError as e:
   detail=e.read(2000).decode('utf-8','replace');print('OpenAI API error:',e.code,detail)
   return self.send_json(502,{'error':'模型接口错误（HTTP %s），请检查密钥、模型权限和额度。'%e.code})
  except Exception as e:
   print('Error:',repr(e));return self.send_json(500,{'error':'服务暂时无法响应，请检查服务器日志。'})
if __name__=='__main__':
 port=int(os.environ.get('PORT','8000'));print('打开 http://localhost:%s'%port,flush=True)
 ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
