import unittest
from region_gate import validate,selected_boxes,candidates
class GateTests(unittest.TestCase):
 def test_origin_enum_and_complete_ids(self):
  good={'candidates':[{'id':3,'origin':'physical_surface','reason':'printed on shirt'}]}
  self.assertEqual(validate(good,[{'id':3}]),good)
  for bad in [{'candidates':[]},{'candidates':[{'id':3,'origin':'logo','reason':'corner'}]},[]]:
   with self.assertRaises(ValueError):validate(bad,[{'id':3}])
 def test_budget_and_no_automatic_semantics(self):
  boxes=[{'id':i,'bbox':[.1,.1,.2,.2],'score':.9} for i in range(40)]
  out=selected_boxes('x',boxes,{'tracks':[]},{'candidates':[]})
  self.assertEqual(len(out),16);self.assertTrue(all(b['candidate_origin']=='unconfirmed' for b in out))
 def test_physical_track_downranked_only(self):
  boxes=[{'id':0,'bbox':[.1,.1,.2,.2],'score':.9},{'id':1,'bbox':[.3,.3,.4,.4],'score':.8}]
  t={'track_id':5,'labels':['stable_corner_side_text'],'representative':{'zones':['top_left']},'observations':[{'frame':'x','ocr_id':0}]}
  out=selected_boxes('x',boxes,{'tracks':[t]},{'candidates':[{'id':5,'origin':'physical_surface','track':True}]})
  self.assertEqual([b['id'] for b in out],[1])
 def test_uncertain_remains(self):
  boxes=[{'id':0,'bbox':[.1,.1,.2,.2],'score':.9}]
  t={'track_id':5,'labels':['stable_corner_side_text'],'representative':{'zones':['top_left']},'observations':[{'frame':'x','ocr_id':0}]}
  self.assertEqual(len(selected_boxes('x',boxes,{'tracks':[t]},{'candidates':[{'id':5,'origin':'uncertain','track':True}]})),1)
if __name__=='__main__':unittest.main()
