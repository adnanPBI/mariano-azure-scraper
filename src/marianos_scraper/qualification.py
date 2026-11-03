"""Release qualification: machine-readable gates; never manufacture retailer evidence."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from .config import load_categories,load_settings
from .schema import FIELDS,validate
from .coverage_audit import audit_source_coverage

REQUIRED_AUTH_SCOPE = ('retailer', 'grantor', 'agreement_id', 'effective_date', 'expiry_date',
                       'authorized_access_method', 'store_ids', 'authorized_categories',
                       'collection_frequency_per_week', 'commercial_storage_permitted',
                       'historical_retention_permitted', 'promotion_and_coupon_collection_permitted')


def _private_evidence_bytes(path: str) -> bytes:
    """Read private authorizations locally or through Azure managed identity.

    Blob keys are private and never printed. The managed identity's scoped data
    role, rather than a storage key in source code, controls access.
    """
    if path.startswith('blob:'):
        import os
        from azure.storage.blob import BlobServiceClient
        from azure.identity import DefaultAzureCredential
        account=os.environ.get('AZURE_STORAGE_ACCOUNT')
        if not account:
            raise ValueError('AZURE_STORAGE_ACCOUNT required for private authorization blob')
        connection=os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        client=(BlobServiceClient.from_connection_string(connection) if connection
                else BlobServiceClient(f'https://{account}.blob.core.windows.net',
                                       credential=DefaultAzureCredential()))
        container=os.environ.get('AZURE_STORAGE_CONTAINER','marianos-crawls')
        blob_path=path[5:]
        if not blob_path.startswith('authorization/') or '..' in blob_path.split('/'):
            raise ValueError('authorization blobs must be in the authorization/ prefix')
        return client.get_container_client(container).download_blob(blob_path).readall()
    return Path(path).read_bytes()


def authorization_evidence(path: str, stores: list, categories: list) -> dict:
    """Metadata is a prerequisite, not verification of a signature or legal validity."""
    if not path or (not path.startswith('blob:') and not Path(path).is_file()):
        return {'passed': False, 'reason': 'Authorization metadata not supplied'}
    try:
        doc=json.loads(_private_evidence_bytes(path).decode('utf-8'))
        missing=[k for k in REQUIRED_AUTH_SCOPE if k not in doc or doc[k] in ('',None,[])]
        if missing:return {'passed':False,'reason':'Missing authorization fields','missing':missing}
        if not isinstance(doc['store_ids'],list) or not isinstance(doc['authorized_categories'],list):
            raise ValueError('store_ids and authorized_categories must be arrays')
        if not set(s.id for s in stores).issubset(set(doc['store_ids'])):
            raise ValueError('not all store IDs covered')
        if not set(c.name for c in categories).issubset(set(doc['authorized_categories'])):
            raise ValueError('not all category names covered')
        if doc['collection_frequency_per_week'] < 2:
            raise ValueError('authorization does not cover twice-weekly runs')
        for key in ('commercial_storage_permitted','historical_retention_permitted','promotion_and_coupon_collection_permitted'):
            if doc[key] is not True:raise ValueError(key+' must explicitly be true')
        if not (date.fromisoformat(doc['effective_date']) <= date.today() <= date.fromisoformat(doc['expiry_date'])):
            raise ValueError('authorization not in current effective dates')
        agreement_file=doc.get('signed_agreement_file','')
        if not agreement_file or not isinstance(agreement_file,str):
            raise ValueError('signed_agreement_file not accessible')
        contents=_private_evidence_bytes(agreement_file)
        if len(contents)<100:raise ValueError('signed agreement file missing/empty')
        actual=hashlib.sha256(contents).hexdigest()
        if actual != doc.get('signed_agreement_sha256'):
            raise ValueError('signed agreement SHA-256 mismatch')
        return {'passed':True,'agreement_id':doc['agreement_id'],'sha256':actual,
                'limitation':'Metadata + file-hash check only; human must verify signer, contractual scope and authenticity'}
    except Exception as exc:
        return {'passed':False,'reason':str(exc)}


def audit_export(path:str, categories:list, source_coverage_path:str="") -> dict:
    """Schema and physical coverage audit; claims are restricted to genuine output evidence."""
    from collections import Counter
    try:
        items=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(items,list) or not items:raise ValueError('missing or empty JSON array')
        for p in items:validate(p)
        raw=Counter(x['category'] for x in items)
        missing=sorted({c.name for c in categories}-set(raw))
        if missing and source_coverage_path:
            review=audit_source_coverage(path,source_coverage_path,categories)
            if review.get("passed"):
                report=json.loads(Path(source_coverage_path).read_text(encoding="utf-8"))
                evidence=report.get("category_coverage_evidence",{})
                missing=[cat for cat in missing if not (
                    evidence.get(cat,{}).get("overlap_only") is True
                    and evidence.get(cat,{}).get("fresh_source_count",0)>0
                )]
        duplicates=len(items)-len({(r['zipcode'],r['store_location'],r['upc'] or r['url'].split('?',1)[0]) for r in items})
        coupons=[x for x in items if x['digital_deals_description']]
        volumes=[x for x in items if x['volume_deals_description']]
        ppm=[x for x in items if x['ppm']]
        bad_urls=[x['url'] for x in items if urlparse(x['url']).hostname not in ('www.marianos.com','marianos.com')]
        store_contexts=sorted({(x['zipcode'],x['store_location']) for x in items})
        ok=(len(items)>=500 and not missing and not duplicates and not bad_urls and len(store_contexts)==1)
        return {'status':'preliminary_pass' if ok else 'failed', 'records':len(items),
                'category_counts':dict(raw),'missing_categories':missing,'duplicate_count':duplicates,
                'field_completeness':{f:round(sum(bool(x[f]) for x in items)/len(items),4) for f in FIELDS},
                'ppm_count':len(ppm),'ppm_examples':[x['ppm'] for x in ppm[:5]],
                'digital_deal_count':len(coupons),'volume_deal_count':len(volumes),
                'bad_url_count':len(bad_urls),'store_contexts':[list(x) for x in store_contexts],
                'remaining_evidence':'Browser screenshots, retailer manual comparison, full subcategory/coupon coverage, Azure jobs, signed authorization and repeat run are separately required.'}
    except Exception as exc:return {'status':'failed','error':str(exc)}


# Each assertion requires a real witnessed observation, not a generated fixture.
OBSERVED_ACCEPTANCE_CLAIMS = (
    'retailer_collection_rights_human_verified',
    'actual_store_selection_and_price_location_verified',
    'all_28_categories_and_applicable_subcategories_reviewed',
    'coupon_to_product_mapping_and_limits_reviewed',
    'ppm_source_text_and_units_reviewed',
    'volume_and_digital_deals_separately_reviewed',
    'random_records_compared_with_retailer',
    'interruption_and_same_slot_resume_witnessed',
    'repeat_observed_run_witnessed',
    'last_successful_dataset_survived_failed_run',
)


def observed_acceptance_evidence(path: str,public_key_path: str,export_path: str,
                                 stores: list,azure_proof: dict) -> dict:
    """Verify an independent Ed25519 acceptance signature over actual evidence IDs.

    Valid cryptography authenticates an attestant, not the truth of their claims.
    The trusted public key must be provisioned independently by the customer.
    """
    if not path or not public_key_path or not Path(path).is_file() or not Path(public_key_path).is_file():
        return {'passed':False,'reason':'Independent signed observed-acceptance and trusted public key missing'}
    if not export_path or not Path(export_path).is_file() or not azure_proof.get('passed'):
        return {'passed':False,'reason':'A live export and real Azure execution must be supplied first'}
    try:
        import base64
        from datetime import datetime, timezone, timedelta
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        body=json.loads(Path(path).read_text(encoding='utf-8'))
        signature=base64.b64decode(body.pop('signature_base64'),validate=True)
        key=load_pem_public_key(Path(public_key_path).read_bytes())
        if not isinstance(key,Ed25519PublicKey):
            raise ValueError('acceptance public key must be Ed25519')
        canonical=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
        key.verify(signature,canonical)
        if not isinstance(body.get('reviewer'),str) or len(body['reviewer'].strip())<3:
            raise ValueError('reviewer identity missing')
        when=datetime.fromisoformat(body['reviewed_at_utc'].replace('Z','+00:00'))
        if when.utcoffset() is None:
            raise ValueError('reviewed_at_utc must have timezone')
        now=datetime.now(timezone.utc)
        if when>now+timedelta(minutes=10) or when<now-timedelta(days=30):
            raise ValueError('observed review is out of validity window')
        if body.get('sampled_records',0)<30:
            raise ValueError('at least 30 individually checked genuine source records required')
        if set(body.get('store_ids',[]))!=set(s.id for s in stores):
            raise ValueError('observed review does not cover configured store IDs')
        if body.get('export_sha256')!=hashlib.sha256(Path(export_path).read_bytes()).hexdigest():
            raise ValueError('observed review export hash does not match candidate dataset')
        if body.get('azure_execution_id')!=azure_proof.get('execution_id'):
            raise ValueError('review must identify same completed Azure execution')
        failed=[c for c in OBSERVED_ACCEPTANCE_CLAIMS if body.get('claims',{}).get(c) is not True]
        if failed:
            raise ValueError('missing independent observations: '+', '.join(failed))
        return {'passed':True,'reviewer':body['reviewer'],'reviewed_at_utc':body['reviewed_at_utc'],
                'observed_samples':body['sampled_records'],'signed_evidence_sha256':hashlib.sha256(canonical).hexdigest(),
                'limitation':'Cryptographic signature authenticates attestation, not data source truth'}
    except Exception as exc:
        return {'passed':False,'reason':type(exc).__name__+': '+str(exc)}


def release_report(categories_path:str, settings_path:str, authorization_path:str='', export_path:str='', azure_proof_path:str='', acceptance_path:str='', reviewer_public_key_path:str='', source_coverage_path:str='') -> dict:
    result={'status':'NO_GO','checks':{}}
    try:
        cats=load_categories(categories_path)
        result['checks']['manifest']={'passed':len(cats)==28, 'count':len(cats), 'names':[x.name for x in cats]}
    except Exception as exc:
        result['checks']['manifest']={'passed':False,'reason':str(exc)}
        return result
    try:
        stores,opts=load_settings(settings_path)
        result['checks']['stores']={'passed':True,'ids':[s.id for s in stores], 'addresses':[s.address for s in stores],
                                    'warning':'Store config is unverified without observed selected-store screenshots'}
    except Exception as exc:
        result['checks']['stores']={'passed':False,'reason':str(exc)}
        stores=[]
    result['checks']['authorization']=authorization_evidence(authorization_path,stores,cats)
    result['checks']['source_coverage']=audit_source_coverage(export_path,source_coverage_path,cats)
    result['checks']['live_export']=audit_export(export_path,cats,source_coverage_path) if export_path else {'status':'not_run','reason':'No actual retailer export supplied'}
    if azure_proof_path and Path(azure_proof_path).is_file():
        try:
            proof=json.loads(Path(azure_proof_path).read_text(encoding='utf-8'))
            valid=(proof.get('completed_real_job') is True
                   and proof.get('storage_publication_verified') is True
                   and proof.get('schedule_verified') is True
                   and proof.get('last_good_pointer_verified') is True
                   and bool(proof.get('execution_id'))
                   and bool(proof.get('subscription_id')))
            result['checks']['azure']={'passed':valid,
                'execution_id':proof.get('execution_id',''),
                'warning':'Azure evidence file values must be checked against real authenticated Azure control plane'}
        except Exception as exc:
            result['checks']['azure']={'passed':False,'reason':str(exc)}
    else:
        result['checks']['azure']={'passed':False,'reason':'No real Azure execution evidence'}
    result['checks']['observed_acceptance']=observed_acceptance_evidence(
        acceptance_path,reviewer_public_key_path,export_path,stores,result['checks']['azure'])
    if (result['checks']['manifest'].get('passed') and result['checks']['stores'].get('passed')
            and result['checks']['authorization'].get('passed')
            and result['checks']['live_export'].get('status')=='preliminary_pass'
            and result['checks']['source_coverage'].get('passed')
            and result['checks']['azure'].get('passed')
            and result['checks']['observed_acceptance'].get('passed')):
        result['status']='GO'
        result['caution']='GO is based on independent signed operator evidence; verify its claims with the retailer and Azure control plane.'
    return result