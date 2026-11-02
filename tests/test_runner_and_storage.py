from dataclasses import replace
import json
import pytest
from marianos_scraper.config import Category,Store,Options
from marianos_scraper.storage import LocalStorage,Locked
from marianos_scraper.runner import Pipeline
from marianos_scraper.browser import CrawlOutcome,CoverageGap,StoreMismatch
from marianos_scraper.cli import require_authorization

STORE=Store(id='approved-store-id',zipcode='60601',name="Mariano's",address='123 Main Street, Chicago, IL 60601',verification_text='123 Main Street')
CATEGORIES=[Category('Grocery','https://www.marianos.com/d/grocery'),Category('Produce','https://www.marianos.com/d/produce')]
OPTS=Options(min_records_per_store=3,prior_yield_ratio=.65,prior_category_ratio=.50,max_detail_pages=0)

class FakeAuthorizedHTMLSource:
    """Offline fixture adapter; NEVER a real Mariano's harvest or contest dataset."""
    visited=[]
    fail_at=None
    products_per_category=3
    def __init__(self,store,options):self.store=store
    def __enter__(self):return self
    def __exit__(self,*exc):pass
    def discover_units(self,category):return [(category.name+' All',category.url+'/unit')]
    def crawl_listing(self,category,sub_name,url,progress=None,resume_items=None):
        type(self).visited.append(category.name)
        if self.fail_at==category.name:raise ConnectionError('simulated browser interruption')
        records=[]
        for k in range(self.products_per_category):
            records.append({'category':category.name,'sub_category':sub_name,
              'product_title':f'{category.name} Test Product {k}', 'weight':'12 oz',
              'regular_price':'2.49','sale_price':'','volume_deals_description':'',
              'volume_deals_price':'','digital_deals_description':'',
              'digital_deals_price':'','image_url':'https://www.marianos.com/static/demo.jpg',
              'url':f'https://www.marianos.com/p/{category.name}/{k}',
              'upc':'','ppm':'$0.21/oz','store_brand':'no'})
        if progress:progress(records)
        return CrawlOutcome(records,proof=f"Pickup at Mariano's {self.store.verification_text}",observed_count=len(records),screenshots=[])

@pytest.fixture(autouse=True)
def clean_fake():
    FakeAuthorizedHTMLSource.visited=[]
    FakeAuthorizedHTMLSource.fail_at=None
    FakeAuthorizedHTMLSource.products_per_category=3
    yield

def test_happy_path_and_pointer(tmp_path):
    db=LocalStorage(str(tmp_path))
    report=Pipeline(db,FakeAuthorizedHTMLSource).run(STORE,CATEGORIES,OPTS,slot='2026-10-15')
    assert report['records']==6 and report['status']=='passed'
    assert report['category_counts']=={'Grocery':3,'Produce':3}
    assert report['field_completeness']['ppm']==1.0
    assert db.get_json('published/approved-store-id/latest.json')['sha256']==report['sha256']
    products=db.get_json(report['dataset_key'])
    assert products[0]['gupc']==products[0]['unit_price']==''
    assert len(products)==6
    # Last successful output is immutable / versioned, pointer is small manifest.
    assert db._path(report['dataset_key']).exists()

def test_interrupted_run_preserves_last_success_and_genuinely_resumes(tmp_path):
    db=LocalStorage(str(tmp_path));job=Pipeline(db,FakeAuthorizedHTMLSource)
    first=job.run(STORE,CATEGORIES,OPTS,slot='2026-10-12')
    FakeAuthorizedHTMLSource.fail_at='Produce'
    with pytest.raises(ConnectionError):job.run(STORE,CATEGORIES,OPTS,slot='2026-10-15')
    assert db.get_json('published/approved-store-id/latest.json')['sha256']==first['sha256']
    assert FakeAuthorizedHTMLSource.visited==['Grocery','Produce','Grocery','Produce']
    FakeAuthorizedHTMLSource.fail_at=None
    FakeAuthorizedHTMLSource.visited.clear()
    second=job.run(STORE,CATEGORIES,OPTS,slot='2026-10-15')
    # First completed unit from interrupted second run is NOT re-scraped.
    assert FakeAuthorizedHTMLSource.visited==['Produce']
    assert second['status']=='passed'

def test_abnormally_thin_run_never_publishes(tmp_path):
    db=LocalStorage(str(tmp_path));job=Pipeline(db,FakeAuthorizedHTMLSource)
    first=job.run(STORE,CATEGORIES,OPTS,slot='2026-10-12')
    FakeAuthorizedHTMLSource.products_per_category=1
    with pytest.raises(CoverageGap):job.run(STORE,CATEGORIES,OPTS,slot='2026-10-15')
    assert db.get_json('published/approved-store-id/latest.json')['sha256']==first['sha256']
    assert db.get_json('runs/approved-store-id/2026-10-15/FAILED.json')['status']=='failed'

def test_missing_category_prevents_publish(tmp_path):
    db=LocalStorage(str(tmp_path))
    FakeAuthorizedHTMLSource.products_per_category=0
    with pytest.raises(CoverageGap):Pipeline(db,FakeAuthorizedHTMLSource).run(STORE,CATEGORIES,OPTS,slot='2026-10-15')
    assert db.get_json('published/approved-store-id/latest.json') is None

def test_permission_guard_fail_closed(monkeypatch):
    monkeypatch.delenv('MARIANOS_AUTHORIZED',raising=False)
    monkeypatch.delenv('MARIANOS_APPROVAL_REFERENCE',raising=False)
    with pytest.raises(PermissionError):require_authorization()
    monkeypatch.setenv('MARIANOS_AUTHORIZED','true')
    with pytest.raises(PermissionError):require_authorization()
    monkeypatch.setenv('MARIANOS_APPROVAL_REFERENCE','licensed-feed-or-written-consent-id')
    require_authorization()

def test_file_store_lock_exclusion(tmp_path):
    a=LocalStorage(str(tmp_path));b=LocalStorage(str(tmp_path))
    with a.lease('approved-store-id'):
        with pytest.raises(Locked):
            with b.lease('approved-store-id'):pass

def test_store_proof_validation_blocks_commit(tmp_path):
    class WrongStoreSource(FakeAuthorizedHTMLSource):
        def crawl_listing(self,*args,**kwargs):
            result=super().crawl_listing(*args,**kwargs)
            result.proof='Pickup at wrong store on another street'
            return result
    db=LocalStorage(str(tmp_path))
    with pytest.raises(CoverageGap):Pipeline(db,WrongStoreSource).run(STORE,CATEGORIES,OPTS,slot='2026-10-15')
    assert db.get_json('published/approved-store-id/latest.json') is None