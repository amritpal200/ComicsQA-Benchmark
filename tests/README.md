# tests

CPU tests with tiny synthetic fixtures; no data or GPUs needed.

Relevant CKG/CRL/generation regression suite (includes verified OCR/lexical and GEN-2):

```bash
PYTHONPATH=tests:src python3 -m unittest test_ckg0 test_ckg0_review test_ckg1 test_ckg2 \
  test_ckg3 test_core test_crl test_crl2 test_crl_rich test_gen1 test_gen2 test_gen2_quality test_gen2_v3 test_verb1 test_verb1_gen2
```
