#!/usr/bin/env python3
"""Optional integration check: real Hermes, mock local model, isolated temp data.
Run after scripts/install_hermes.py. Does not use any real model API credentials.
"""
import json, sys, tempfile, threading, time, shlex
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import core, agent_bridge
calls=[]
class Model(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  data=json.dumps({'object':'list','data':[{'id':'tide-test','object':'model','owned_by':'local'}]}).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  messages=body.get('messages',[])
  tools=[t.get('function',{}).get('name') for t in body.get('tools',[])]
  has_tool=any(m.get('role')=='tool' for m in messages)
  calls.append({'path':self.path,'tools':tools,'has_tool_result':has_tool})
  if not has_tool and 'terminal' in tools:
   tool={'id':'call_tide_test','type':'function','function':{'name':'terminal','arguments':json.dumps({'command':shlex.quote(sys.executable)+' '+shlex.quote(str(core.ROOT/'tide.py'))+' add-symbol AAPL'})}}
   message={'role':'assistant','content':None,'tool_calls':[tool]};finish='tool_calls'
  else:
   message={'role':'assistant','content':'已通过 Tide CLI 添加 AAPL。请查看关注名单核对。'};finish='stop'
  base={'id':'chatcmpl-tide-test','object':'chat.completion','created':int(time.time()),'model':'tide-test'}
  if body.get('stream'):
   delta=dict(message)
   if 'tool_calls' in delta:delta['tool_calls'][0]['index']=0
   content='data: '+json.dumps({**base,'object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':None}]})+'\n\n'
   content+='data: '+json.dumps({**base,'object':'chat.completion.chunk','choices':[{'index':0,'delta':{},'finish_reason':finish}]})+'\n\ndata: [DONE]\n\n'
   data=content.encode();mime='text/event-stream'
  else:
   data=json.dumps({**base,'choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}).encode();mime='application/json'
  self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=ThreadingHTTPServer(('127.0.0.1',0),Model);threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory(prefix='tide-hermes-test-') as tmp:
 core.HOME=Path(tmp);core.initialize();settings=core.config('settings');settings['model']={'base_url':f'http://127.0.0.1:{server.server_port}/v1','name':'tide-test'};settings['agent_enabled']=True;core.save_config('settings',settings);core.save_secrets({'api_key':'local-test-only'})
 try:
  result=agent_bridge.run('请通过工具添加 AAPL 到关注名单。',print)
  added=any(x['symbol']=='AAPL' for x in core.config('watchlist'))
  result={'result':result,'added':added,'requests':calls,'upstream_commit':agent_bridge.PIN,'scope':'真实 Hermes 进程 + 本地模拟模型 + 实际 CLI 配置写入；未测试付费模型'}
  print(json.dumps(result,ensure_ascii=False,indent=2))
  if not added:raise RuntimeError('Hermes did not apply actual tool change')
 finally:server.shutdown()
