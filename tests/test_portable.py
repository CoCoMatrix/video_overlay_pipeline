import importlib.util,json,threading,unittest,tempfile,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from functools import partial
from region_gate import candidates
from contract_v4 import aggregate
from rules import analyze
REPO=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('serve',REPO/'scripts/serve.py')
serve=importlib.util.module_from_spec(spec);spec.loader.exec_module(serve)
class PortableTests(unittest.TestCase):
    def test_corner_inspection_even_without_ocr(self):
        cs=candidates({'tracks':[]},{'frames':{'a.jpg':{'timestamp_s':1,'boxes':[]}}})
        self.assertEqual(len(cs),4)
        self.assertEqual(len(set(c['id'] for c in cs)),4)
        self.assertTrue(all(c['rule_labels']==['corner_inspection_only'] for c in cs))
    def test_empty_rules_never_imply_no_overlay(self):
        cfg=json.loads((REPO/'configs/region_rules.json').read_text())
        result=analyze({'clip_id':'test','frames':{'a':{'timestamp_s':0,'boxes':[],'width':640,'height':360}}},5,cfg)
        self.assertIsNone(result['semantic_overlay_present'])
        self.assertEqual(result['labels'],[])
    def test_blockage_requires_extra_verification(self):
        r={'overlay_present':True,'overlay_types':['logo'],'action_present':True,'overlay_impact':'blocks_key_action',
           'evidence':[{'frame_id':0,'overlay_type':'logo','overlay_region':[.2,.2,.7,.7],'critical_region':[.3,.3,.6,.6]}]}
        passes=[{'result':r,'frames':[{'timestamp_s':.5}]}]*2
        self.assertEqual(aggregate(passes)['overlay_route'],'review')
        v={'result':{'overlay_covers_critical_region':True,'necessary_phase_unobservable':True,'cause_is_overlay':True}}
        self.assertEqual(aggregate(passes,v)['overlay_route'],'reject')
    def test_http_ranges_and_outside_symlink(self):
        with tempfile.TemporaryDirectory() as tmp,tempfile.TemporaryDirectory() as outside:
            root=Path(tmp);(root/'video.mp4').write_bytes(b'0123456789')
            (Path(outside)/'private').write_text('not served');(root/'outside').symlink_to(outside,target_is_directory=True)
            class Quiet(serve.Handler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=tmp))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                for value,expected in [('bytes=2-5',b'2345'),('bytes=-3',b'789'),('bytes=8-',b'89')]:
                    with opener.open(urllib.request.Request(base+'/video.mp4',headers={'Range':value})) as response:
                        self.assertEqual(response.status,206);self.assertEqual(response.read(),expected)
                for path,headers,code in [('/video.mp4',{'Range':'bytes=20-25'},416),('/outside/private',{},403)]:
                    with self.assertRaises(urllib.error.HTTPError) as err:opener.open(urllib.request.Request(base+path,headers=headers))
                    self.assertEqual(err.exception.code,code)
            finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
