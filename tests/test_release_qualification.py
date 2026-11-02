from datetime import date,timedelta
import hashlib,json
from dataclasses import replace
from marianos_scraper.config import Category, Store
from marianos_scraper.qualification import authorization_evidence, release_report, audit_export
from marianos_scraper.schema import record

CATS=[Category('Produce','https://www.marianos.com/d/produce'),Category('Coupons','https://www.marianos.com/savings/cl/coupons/')]
STORES=[Store('531_00515','60640',"Mariano's",'1800 W Lawrence Ave, Chicago IL 60640','1800 W Lawrence Ave')]

def auth(tmp_path):
    agreement=tmp_path/'signed.pdf';agreement.write_bytes(b'signed external agreement placeholder fixture' * 8)
    data={'retailer':"Mariano's",'grantor':'test licensor','agreement_id':'test-contract','effective_date':str(date.today()-timedelta(days=1)),
    'expiry_date':str(date.today()+timedelta(days=1)),'authorized_access_method':'written permission for browser collection',
    'store_ids':['531_00515'],'authorized_categories':['Produce','Coupons'],'collection_frequency_per_week':2,
    'commercial_storage_permitted':True,'historical_retention_permitted':True,
    'promotion_and_coupon_collection_permitted':True,'signed_agreement_file':str(agreement),
    'signed_agreement_sha256':hashlib.sha256(agreement.read_bytes()).hexdigest()}
    path=tmp_path/'permission.json';path.write_text(json.dumps(data))
    return path,data

def test_no_document_no_permission():
    assert authorization_evidence('',STORES,CATS)['passed'] is False

def test_authorization_scope_and_checksum(tmp_path):
    path,data=auth(tmp_path)
    assert authorization_evidence(str(path),STORES,CATS)['passed']
    data['authorized_categories']=['Produce'];path.write_text(json.dumps(data))
    assert not authorization_evidence(str(path),STORES,CATS)['passed']
    data['authorized_categories']=['Produce','Coupons'];data['signed_agreement_sha256']='bad';path.write_text(json.dumps(data))
    assert not authorization_evidence(str(path),STORES,CATS)['passed']

def test_coupon_flag_required_for_permission(tmp_path):
    path,data=auth(tmp_path);data['promotion_and_coupon_collection_permitted']=False;path.write_text(json.dumps(data))
    assert not authorization_evidence(str(path),STORES,CATS)['passed']

def test_audit_no_fake_pass_when_missing_coupon(tmp_path):
    path=tmp_path/'out.json'
    items=[record({'zipcode':'60640','store_location':'1800 W Lawrence Ave','product_title':str(i),
                    'url':f'https://www.marianos.com/p/item-{i}','category':'Produce','weight':'12 oz','regular_price':'2.00'},'2026-10-18') for i in range(500)]
    path.write_text(json.dumps(items))
    output=audit_export(str(path),CATS)
    assert output['status']=='failed' and output['missing_categories']==['Coupons']

def test_default_release_check_is_no_go(tmp_path):
    output=release_report('config/Marianos_Category_URLs.csv','config/stores.yaml','', '', '')
    assert output['status']=='NO_GO' and output['checks']['authorization']['passed'] is False