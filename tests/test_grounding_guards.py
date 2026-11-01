import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/comics_qa/annotations/magi3_grounding'))
from guards import install_decoder_guard, check_budget, GroundingLimitError, validate_prediction, reusable

class Guards(unittest.TestCase):
    def test_wrapper_stops_before_model_call(self):
        from types import SimpleNamespace
        calls=[]
        lm=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=16),generate=lambda **kw:calls.append(kw))
        model=SimpleNamespace(language_model=lm)
        processor=SimpleNamespace(tokenizer=SimpleNamespace(convert_ids_to_tokens=lambda row:row))
        class Prefix:
            def detach(self):return self
            def cpu(self):return self
            def tolist(self):return [['word']*8]
        install_decoder_guard(model,processor)
        with self.assertRaises(GroundingLimitError):lm.generate(decoder_input_ids=Prefix(),max_new_tokens=9)
        self.assertEqual(calls,[])
        lm.generate(decoder_input_ids=Prefix(),max_new_tokens=8)
        self.assertEqual(len(calls),1)

    def test_actual_length_reserves_chunk_space(self):
        check_budget(1015,9,1024,0)
        with self.assertRaises(GroundingLimitError):check_budget(1016,9,1024,0)
    def test_no_progress(self):
        with self.assertRaises(GroundingLimitError):check_budget(200,9,1024,64)
    def test_punctuation_is_explicit_not_exact(self):
        p={'grounded_caption':'A boy runs.', 'bboxes':[], 'indices_of_bboxes_in_caption':[]}
        self.assertEqual(validate_prediction(p,'A boy, runs.',True),'punctuation_or_whitespace_only')
        with self.assertRaises(ValueError):validate_prediction(p,'A girl runs.',True)
    def test_malformed_and_runaway(self):
        p={'grounded_caption':'boy','bboxes':[[[0,0,2,2]]]*129,'indices_of_bboxes_in_caption':[[0,3]]*129}
        with self.assertRaises(ValueError):validate_prediction(p,'boy',True)
        p['bboxes']=[]
        with self.assertRaises(ValueError):validate_prediction(p,'boy',True)
    def test_legacy_revalidation(self):
        d={'grounding':{'_meta':{'status':'complete','signature':'s'},'panels':[{'status':'complete','caption':'boy','grounded_caption':'girl','entities':[],'phrases':[]}]}}
        self.assertFalse(reusable(d,'s',True))
        d['grounding']['panels'][0]['grounded_caption']='boy'
        self.assertTrue(reusable(d,'s',True))
        self.assertFalse(reusable(d,'changed',True))
if __name__=='__main__':unittest.main()
