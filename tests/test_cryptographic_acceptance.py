"""Unit checks of the future human signoff gate, never real signoffs."""
import base64
from datetime import datetime,timezone
from hashlib import sha256
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from marianos_scraper.qualification import observed_acceptance_evidence,OBSERVED_ACCEPTANCE_CLAIMS
from marianos_scraper.config import Store

STORE=Store('test-store','60640',"Mariano's",'Offline Fake Address','Offline Fake')

def fixture(tmp_path):
    export=tmp_path/'offline-data.json'
    export.write_text('[{"NOTICE":"synthetic fixture not real retailer data"}]')
    private=Ed25519PrivateKey.generate()
    pem=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    public=tmp_path/'fake-unit-public.pem'; public.write_bytes(pem)
    body={'reviewer':'UNIT TEST SYNTHETIC REVIEWER','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
          'sampled_records':30,'store_ids':[STORE.id], 'export_sha256':sha256(export.read_bytes()).hexdigest(),
          'azure_execution_id':'OFFLINE_UNIT_EXECUTION',
          'claims':{c:True for c in OBSERVED_ACCEPTANCE_CLAIMS}}
    canonical=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    body['signature_base64']=base64.b64encode(private.sign(canonical)).decode()
    path=tmp_path/'fake-unit-acceptance.json';path.write_text(json.dumps(body))
    return export,public,path

def test_observed_acceptance_requires_signed_review(tmp_path):
    export,public,path=fixture(tmp_path)
    assert not observed_acceptance_evidence('',str(public),str(export),[STORE],{'passed':True})['passed']
    result=observed_acceptance_evidence(str(path),str(public),str(export),[STORE],{'passed':True,'execution_id':'OFFLINE_UNIT_EXECUTION'})
    assert result['passed'] and result['observed_samples']==30

def test_observed_acceptance_rejects_tampered_export(tmp_path):
    export,public,path=fixture(tmp_path)
    export.write_text('tampered fixture bytes')
    result=observed_acceptance_evidence(str(path),str(public),str(export),[STORE],{'passed':True,'execution_id':'OFFLINE_UNIT_EXECUTION'})
    assert not result['passed'] and 'hash' in result['reason']

def test_observed_acceptance_rejects_missing_claim_after_signature(tmp_path):
    export,public,path=fixture(tmp_path)
    obj=json.loads(path.read_text());obj['claims']['coupon_to_product_mapping_and_limits_reviewed']=False
    path.write_text(json.dumps(obj))
    result=observed_acceptance_evidence(str(path),str(public),str(export),[STORE],{'passed':True,'execution_id':'OFFLINE_UNIT_EXECUTION'})
    assert not result['passed']