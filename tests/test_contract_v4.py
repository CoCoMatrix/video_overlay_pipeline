import unittest,copy
from contract_v4 import validate,aggregate,match_ocr
F=[{'timestamp_s':0.0},{'timestamp_s':1.0}]
O={0:{3:{'bbox':[0,.8,1,1]}},1:{}}
def sample():
 return dict(overlay_present=True,overlay_types=['subtitle'],action_present=False,overlay_impact='not_applicable',observed_action='',action_intervals=[],reason='字幕存在，无操作',evidence=[dict(frame_id=0,overlay_type='subtitle',overlay_region=[0,.8,1,1],critical_region=None,blocked_phase='',reason='底部字幕')])
class ContractTests(unittest.TestCase):
 def test_no_action_still_inventory(self):
  v=validate(sample(),2,F,O);r=aggregate([{'result':v},{'result':v}]);self.assertEqual(r['overlay_route'],'not_applicable');self.assertTrue(r['overlay_present'])
 def test_no_action_wrong_impact(self):
  v=sample();v['overlay_impact']='none'
  with self.assertRaises(ValueError):validate(v,2,F,O)
 def test_programmatic_ocr_match(self):
  v=sample();m=match_ocr(v['evidence'],O);self.assertEqual(m[0]['ocr_ids'],[3]);self.assertFalse(m[0]['semantic_confirmation'])
  v['evidence'][0]['overlay_region']=[0,0,.1,.1];self.assertEqual(match_ocr(v['evidence'],O)[0]['ocr_ids'],[])
 def test_no_action_type_disagreement(self):
  a=sample();b=sample();b['overlay_types']=['title_text'];b['evidence'][0]['overlay_type']='title_text'
  r=aggregate([{'result':a},{'result':b}]);self.assertEqual(r['overlay_impact'],'not_applicable');self.assertEqual(r['routing_reason'],'overlay_type_disagreement')
 def test_technical_failure(self):
  self.assertEqual(aggregate([{'error':'timeout'},{'result':sample()}])['routing_reason'],'technical_failure')
 def test_inventory_without_action_and_without_overlay(self):
  v=sample();v.update(overlay_present=False,overlay_types=[]);v['evidence'][0].update(overlay_type='none',overlay_region=None)
  validate(v,2,F,O);r=aggregate([{'result':v},{'result':v}]);self.assertEqual(r['overlay_route'],'not_applicable');self.assertFalse(r['overlay_present'])
 def test_absent_overlay_visible_action(self):
  v=sample();v.update(overlay_present=False,overlay_types=[],action_present=True,overlay_impact='none',observed_action='手部移动杯子',action_intervals=[{'start_s':0,'end_s':1}]);v['evidence'][0].update(overlay_type='none',overlay_region=None)
  validate(v,2,F,O);self.assertEqual(aggregate([{'result':v},{'result':v}])['overlay_route'],'accept')
if __name__=='__main__':unittest.main()
