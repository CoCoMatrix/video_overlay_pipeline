import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from contract_v3 import validate,aggregate
from run_v3 import common_intervals,retryable_record
from media_v3 import identity,subsample

class V3(unittest.TestCase):
 def sample(self):
  return dict(overlay_present=True,overlay_types=['logo'],action_present=True,task_relevance='relevant',action_intervals=[dict(start_s=0,end_s=2)],key_action_visibility='blocked',temporal_adequacy='adequate',decision='reject',observed_action='hand inserts plug',other_limitations=[],review_reason='none',evidence=[dict(frame_id=0,timestamp_s=.5,overlay_type='logo',critical_region=[.4,.4,.6,.6],overlay_region=[.45,.45,.7,.7],blocked_phase='contact',reason='opaque overlay over contact')])
 def test_reject_without_overlap_fails(self):
  r=self.sample();r['evidence'][0]['overlay_region']=[0,0,.1,.1]
  with self.assertRaises(ValueError):validate(r,2,[{'timestamp_s':.5}])
 def test_unseen_and_wrong_timestamp(self):
  for field,value in [('frame_id',10),('timestamp_s',1.5)]:
   r=self.sample();r['evidence'][0][field]=value
   with self.assertRaises(ValueError):validate(r,2,[{'timestamp_s':.5}])
 def test_two_rejects_need_verification(self):
  p=[{'result':self.sample()}]*2
  self.assertEqual(aggregate(p)[0],'review')
  self.assertEqual(aggregate(p,{'result':dict(overlay_covers_critical_region=True,necessary_phase_unobservable=False,cause_is_overlay=True)})[0],'review')
 def test_distinct_overlay_locations_disagree(self):
  a=self.sample();b=self.sample();b['evidence'][0]['overlay_region']=[.1,.1,.2,.2]
  # Same broad contact box must not make different overlays agree.
  b['evidence'][0]['critical_region']=[.1,.1,.6,.6]
  verifier={'result':dict(overlay_covers_critical_region=True,necessary_phase_unobservable=True,cause_is_overlay=True)}
  self.assertEqual(aggregate([{'result':a},{'result':b}],verifier)[0],'review')
 def test_action_interval_intersection(self):
  self.assertEqual(common_intervals([{'action_intervals':[{'start_s':0,'end_s':3}]},{'action_intervals':[{'start_s':2,'end_s':4}]}]),[{'start_s':2,'end_s':3}])
 def test_retry_failure_only(self):
  self.assertTrue(retryable_record({'passes':[{'error':'bad JSON'}]}))
  self.assertFalse(retryable_record({'passes':[{'result':{'decision':'review'}}]}))
 def test_cache_inputs_and_real_times(self):
  self.assertNotEqual(identity({'sha':'x','start':0}),identity({'sha':'x','start':1}))
  frames=[{'timestamp_s':x/30} for x in range(30)]
  sampled=subsample(frames,8)
  self.assertTrue(all(f in frames for f in sampled));self.assertEqual(len(sampled)%4,0)

if __name__=='__main__':unittest.main()
