"""Adversarial offline verification; all source data is synthetic and non-retailer."""
from collections import Counter
from dataclasses import replace
import json
import pytest
from marianos_scraper.browser import BrowserSource,CoverageGap
from marianos_scraper.config import Category,Store,Options,load_categories
from marianos_scraper.runner import Pipeline
from marianos_scraper.storage import LocalStorage
from marianos_scraper.promotions import classify
from marianos_scraper.qualification import audit_export

STORE=Store('offline-store','60640',"Mariano's",'1800 Fake Avenue, Chicago, IL 60640','1800 Fake Avenue')
ALL_CATEGORIES=load_categories('config/Marianos_Category_URLs.csv')
OPT=Options(min_records_per_store=500,min_per_category=1,max_detail_pages=0,delay_seconds=0)

class SyntheticSource:
    """Generates distinct in-memory records; DOES NOT visit Mariano's."""
    count=20
    approx_only_category=None
    duplicate_only_category=None
    fail_category=None
    seen=[]
    def __init__(self,store,options): self.store=store
    def __enter__(self): return self
    def __exit__(self,*exc): return None
    def discover_units(self,cat):
        self.seen.append(('discover',cat.name))
        return [(cat.name+' / all',cat.url)]
    def crawl_listing(self,cat,sub,url,progress=None,resume_items=None):
        from marianos_scraper.browser import CrawlOutcome
        self.seen.append(('crawl',cat.name))
        if cat.name==self.fail_category: raise ConnectionError('offline-injected interruption')
        count=self.count
        if cat.name in (self.approx_only_category,self.duplicate_only_category): count=1
        items=[]
        for k in range(count):
            dupe=cat.name==self.duplicate_only_category
            name=ALL_CATEGORIES[0].name if dupe else cat.name
            items.append(dict(category=cat.name,sub_category=sub,product_title=f'OFFLINE TEST {name} {k}',
                weight='approx. 2 lb' if cat.name==self.approx_only_category else '12 oz',
                regular_price='2.49',sale_price='',volume_deals_description='',volume_deals_price='',
                digital_deals_description='',digital_deals_price='',image_url='',
                url=f'https://www.marianos.com/p/offline-{name.replace(" ", "-")}-{k}',upc='',ppm='',store_brand='no'))
        if progress:progress(items)
        return CrawlOutcome(items=items,proof=f'Pickup at {self.store.verification_text}',observed_count=len(items),screenshots=[])

@pytest.fixture(autouse=True)
def reset_synthetic_source():
    SyntheticSource.count=20
    SyntheticSource.approx_only_category=None
    SyntheticSource.duplicate_only_category=None
    SyntheticSource.fail_category=None
    SyntheticSource.seen=[]
    yield

def test_every_supplied_category_has_exported_synthetic_records(tmp_path):
    storage=LocalStorage(str(tmp_path))
    report=Pipeline(storage,SyntheticSource).run(STORE,ALL_CATEGORIES,OPT,slot='2026-10-19')
    assert len(ALL_CATEGORIES)==28
    assert report['records']==560
    assert set(report['category_counts'])=={c.name for c in ALL_CATEGORIES}
    assert all(report['category_counts'][c.name]==20 for c in ALL_CATEGORIES)
    data=storage.get_json(report['dataset_key'])
    assert len(data)==560
    assert {p['category'] for p in data}=={c.name for c in ALL_CATEGORIES}
    assert all(p['gupc']==p['unit_price']=='' for p in data)
    assert all('OFFLINE TEST ' in p['product_title'] for p in data)
    assert audit_export(str(storage._path(report['dataset_key'])),ALL_CATEGORIES)['status']=='preliminary_pass'

def test_approximate_weight_only_category_rejected_despite_500_other_products(tmp_path):
    storage=LocalStorage(str(tmp_path))
    SyntheticSource.count=21
    SyntheticSource.approx_only_category='Coupons'
    with pytest.raises(CoverageGap,match='Coupons'):
        Pipeline(storage,SyntheticSource).run(STORE,ALL_CATEGORIES,OPT,slot='2026-10-19')
    assert storage.get_json('published/offline-store/latest.json') is None

def test_duplicate_only_category_does_not_create_false_export_coverage(tmp_path):
    storage=LocalStorage(str(tmp_path))
    SyntheticSource.count=21
    SyntheticSource.duplicate_only_category='Hardware Home Improvement'
    with pytest.raises(CoverageGap,match='absent after global deduplication'):
        Pipeline(storage,SyntheticSource).run(STORE,ALL_CATEGORIES,OPT,slot='2026-10-19')
    assert storage.get_json('published/offline-store/latest.json') is None

def test_interruption_does_not_replace_successful_dataset_and_resume(tmp_path):
    storage=LocalStorage(str(tmp_path))
    pipeline=Pipeline(storage,SyntheticSource)
    previous=pipeline.run(STORE,ALL_CATEGORIES,OPT,slot='2026-10-12')
    SyntheticSource.fail_category='Beauty'
    with pytest.raises(ConnectionError):
        pipeline.run(STORE,ALL_CATEGORIES,OPT,slot='2026-10-15')
    assert storage.get_json('published/offline-store/latest.json')['sha256']==previous['sha256']
    SyntheticSource.fail_category=None
    SyntheticSource.seen=[]
    new=pipeline.run(STORE,ALL_CATEGORIES,OPT,slot='2026-10-15')
    assert new['status']=='passed'
    # Categories completed before Beauty did not recrawl on resume.
    pre_index=[c.name for c in ALL_CATEGORIES].index('Beauty')
    assert not any(event=='crawl' and category in {c.name for c in ALL_CATEGORIES[:pre_index]}
                   for event,category in SyntheticSource.seen)

def test_category_url_change_invalidates_discovery_checkpoint(tmp_path):
    db=LocalStorage(str(tmp_path))
    a=Category('Grocery','https://www.marianos.com/d/old')
    b=Category('Produce','https://www.marianos.com/d/produce')
    opt=replace(OPT,min_records_per_store=2)
    SyntheticSource.count=2
    SyntheticSource.fail_category='Produce'
    with pytest.raises(ConnectionError):Pipeline(db,SyntheticSource).run(STORE,[a,b],opt,slot='2026-10-19')
    SyntheticSource.fail_category=None
    SyntheticSource.seen=[]
    a_changed=Category('Grocery','https://www.marianos.com/d/new')
    Pipeline(db,SyntheticSource).run(STORE,[a_changed,b],opt,slot='2026-10-19')
    assert ('discover','Grocery') in SyntheticSource.seen
    assert ('crawl','Grocery') in SyntheticSource.seen

def test_nested_department_discovery_not_limited_to_first_level():
    from urllib.parse import urlparse
    cat=Category('Produce','https://www.marianos.com/d/produce')
    source=BrowserSource(STORE,replace(OPT,max_subcategory_depth=3))
    links={
      '/d/produce':[
        {'href':'https://www.marianos.com/pl/apples/1','text':'Apples'},
        {'href':'https://www.marianos.com/d/produce/vegetables','text':'Vegetables'},
        {'href':'https://example.org/pl/wrong','text':'Offsite'},
      ],
      '/d/produce/vegetables':[
        {'href':'https://www.marianos.com/pl/greens/2','text':'Greens'},
        {'href':'https://www.marianos.com/d/produce/vegetables/leafy','text':'Leafy'},
      ],
      '/d/produce/vegetables/leafy':[
        {'href':'https://www.marianos.com/pl/lettuce/3','text':'Lettuce'},
        {'href':'https://www.marianos.com/d/produce','text':'Back To Produce'},
      ],
    }
    class DummyPage:
        def __init__(self): self.path=''
        def eval_on_selector_all(self,selector,script): return links.get(self.path,[])
    page=DummyPage()
    source.page=page
    source._navigate=lambda url:setattr(page,'path',urlparse(url).path)
    source.verify_store=lambda:'verified in offline fixture'
    units=source.discover_units(cat)
    assert [sub for sub,url in units]==['Apples','Greens','Lettuce']
    assert all('example.org' not in u for _,u in units)

def test_coupon_landing_without_product_mapping_fails_closed():
    cat=next(c for c in ALL_CATEGORIES if c.name=='Coupons')
    src=BrowserSource(STORE,OPT)
    class DummyPage:
        def eval_on_selector_all(self,selector,script):
            return [{'href':'https://www.marianos.com/savings/cl/coupons/coupon123','text':'Digital offer'}]
    src.page=DummyPage()
    src._navigate=lambda u:None
    src.verify_store=lambda:'verified in offline fixture'
    with pytest.raises(CoverageGap,match='no product-listing subcategories'):
        src.discover_units(cat)

@pytest.mark.parametrize('text,kind,price',[
    ('Buy 1, Get 1 Free','volume',''),
    ('2 for $5','volume','5.00'),
    ('Clip Coupon: Save $2','digital',''),
    ('Save $5 when you buy 5 with Digital Coupon','digital',''),
    ('$3.99 each with Digital Coupon','digital','3.99'),
    ('20% off with clipped coupon','digital',''),
])
def test_deal_prices_only_when_explicit(text,kind,price):
    offer=classify(text)
    assert offer.kind==kind
    assert offer.displayed_price==price

def test_live_runtime_gate_rejects_attestation_without_signed_file(monkeypatch):
    from marianos_scraper.cli import require_authorization
    monkeypatch.setenv('MARIANOS_AUTHORIZED','true')
    monkeypatch.setenv('MARIANOS_APPROVAL_REFERENCE','not-a-real-license')
    monkeypatch.delenv('MARIANOS_AUTHORIZATION_FILE',raising=False)
    with pytest.raises(PermissionError,match='Signed authorization evidence unavailable'):
        require_authorization('',[STORE],ALL_CATEGORIES)


def test_live_runtime_gate_rejects_api_only_license_for_browser(monkeypatch,tmp_path):
    from datetime import date,timedelta
    from hashlib import sha256
    from marianos_scraper.cli import require_authorization
    monkeypatch.setenv('MARIANOS_AUTHORIZED','true')
    monkeypatch.setenv('MARIANOS_APPROVAL_REFERENCE','FAKE-OFFLINE-TEST-AGREEMENT')
    signed=tmp_path/'signed-fixture.txt'
    signed.write_text('This is an offline synthetic fixture. Not an actual signed agreement. '*5)
    meta={
      'retailer':"Mariano's",'grantor':'synthetic','agreement_id':'FAKE-OFFLINE-TEST-AGREEMENT',
      'effective_date':str(date.today()-timedelta(days=1)),'expiry_date':str(date.today()+timedelta(days=1)),
      'authorized_access_method':'API feed access only', 'store_ids':[STORE.id],
      'authorized_categories':[c.name for c in ALL_CATEGORIES],
      'collection_frequency_per_week':2,'commercial_storage_permitted':True,
      'historical_retention_permitted':True,'promotion_and_coupon_collection_permitted':True,
      'signed_agreement_file':str(signed),'signed_agreement_sha256':sha256(signed.read_bytes()).hexdigest()
    }
    path=tmp_path/'metadata.json';path.write_text(json.dumps(meta))
    with pytest.raises(PermissionError,match='browser/website collection'):
        require_authorization(str(path),[STORE],ALL_CATEGORIES)
    meta['authorized_access_method']='browser / website automated collection (synthetic test)'
    path.write_text(json.dumps(meta))
    # The metadata SHA check is an engineering test, not verification of a legal signature.
    require_authorization(str(path),[STORE],ALL_CATEGORIES)
    monkeypatch.setenv('MARIANOS_APPROVAL_REFERENCE','WRONG-ID')
    with pytest.raises(PermissionError,match='Approval reference'):
        require_authorization(str(path),[STORE],ALL_CATEGORIES)