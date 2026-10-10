"""Real HTTP tests of the offline asset handler, using a temporary fixture tree."""
import importlib.util,json,pathlib,tempfile,threading,unittest,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace
import sys

ROOT=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[4]
sys.argv=sys.argv[:1]
spec=importlib.util.spec_from_file_location('offline_serve',ROOT/'web/civic/offline/serve.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send_bytes(self,status,data,kind):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers()
  if self.command!='HEAD':self.wfile.write(data)
 def error_reply(self,status,message):self.send_bytes(status,json.dumps({'error':message}).encode(),'application/json')
 def do_GET(self):
  if not mod.serve(self,self.path.split('?')[0]):self.error_reply(404,'not found')
 do_HEAD=do_GET

class Transport(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=pathlib.Path(cls.temp.name)
  p=cls.root/'data/civic/astana/tiles/astana.pmtiles';p.parent.mkdir(parents=True);cls.data=b'PMTiles\x03'+bytes(range(256))*257;p.write_bytes(cls.data)
  p=cls.root/'web/civic/offline/fonts/Noto Sans Regular/1024-1279.pbf';p.parent.mkdir(parents=True);p.write_bytes(b'font')
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.backend=SimpleNamespace(project=cls.root)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.base='http://127.0.0.1:'+str(cls.server.server_port)+'/civic/offline/'
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
 def call(self,name='astana.pmtiles',headers=None,method='GET'):
  try:r=urllib.request.urlopen(urllib.request.Request(self.base+name,headers=headers or {},method=method),timeout=5)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,r.headers,r.read()
 def test_full_archive(self):
  s,h,b=self.call();self.assertEqual(s,200);self.assertEqual(b,self.data);self.assertEqual(h['Accept-Ranges'],'bytes')
 def test_head_no_body(self):
  s,h,b=self.call(method='HEAD');self.assertEqual(s,200);self.assertEqual(b,b'');self.assertEqual(int(h['Content-Length']),len(self.data))
 def test_header_range(self):
  s,h,b=self.call(headers={'Range':'bytes=0-16383'});self.assertEqual(s,206);self.assertEqual(b,self.data[:16384]);self.assertEqual(h['Content-Range'],f'bytes 0-16383/{len(self.data)}')
 def test_range_head(self):
  s,h,b=self.call(headers={'Range':'bytes=8-31'},method='HEAD');self.assertEqual(s,206);self.assertEqual(b,b'');self.assertEqual(h['Content-Length'],'24')
 def test_suffix(self):self.assertEqual(self.call(headers={'Range':'bytes=-10'})[2],self.data[-10:])
 def test_open_end(self):self.assertEqual(self.call(headers={'Range':f'bytes={len(self.data)-10}-'})[2],self.data[-10:])
 def test_clamped_end(self):self.assertEqual(self.call(headers={'Range':'bytes=1-999999'})[2],self.data[1:])
 def test_unsatisfiable(self):
  s,h,b=self.call(headers={'Range':'bytes=999999-'});self.assertEqual(s,416);self.assertEqual(h['Content-Range'],f'bytes */{len(self.data)}');self.assertEqual(b,b'')
 def test_invalid_ranges(self):
  for value in ['bytes=3-2','bytes=-0','bytes=-','items=0-4','bytes=0-1,4-5','bytes=x-y']:
   with self.subTest(value=value):self.assertEqual(self.call(headers={'Range':value})[0],416)
 def test_etag_if_range(self):
  _,h,_=self.call();self.assertEqual(self.call(headers={'Range':'bytes=0-7','If-Range':h['ETag']})[0],206)
  self.assertEqual(self.call(headers={'Range':'bytes=0-7','If-Range':'"stale"'})[0],200)
 def test_status(self):self.assertEqual(json.loads(self.call('status.json')[2]),{'available':True})
 def test_404_no_paths_leaked(self):
  for name in ['serve.py','../boot.js','%2e%2e/%2e%2e/run.bat','fonts/Noto%20Sans%20Regular/1025-1280.pbf','fonts/unknown/0-255.pbf']:
   with self.subTest(name=name):
    s,_,b=self.call(name);self.assertEqual(s,404);self.assertNotIn(str(self.root).encode(),b)
 def test_glyph_allowlist(self):self.assertEqual(self.call('fonts/Noto%20Sans%20Regular/1024-1279.pbf')[2],b'font')

if __name__=='__main__':unittest.main(verbosity=2)
