import json
from pathlib import Path
import pytest
from marianos_scraper.schema import FIELDS,record,validate,RecordError,APPROX_WEIGHT,fingerprint
from marianos_scraper.extract import extract_cards,enrich_from_details,finalize_card
from marianos_scraper.promotions import classify
from marianos_scraper.config import load_categories

EXAMPLE_HTML='''
<html><body><main>
  <article class="product-card" data-testid="product-card">
    <a href="/p/kroger-pasta/0001234000078?some=untouched"><h3>Kroger® Pasta Shells</h3></a>
    <span data-testid="product-size">16 oz</span>
    <span data-testid="regular-price">$3.99</span>
    <span data-testid="sale-price">$2.99</span>
    <span data-testid="ppm">$0.19/oz</span>
    <span data-testid="promotion">Mix or Match 5 for $10, must buy 5</span>
    <span data-testid="coupon">$1.99 each with Digital Coupon; Limit 5</span>
    <img src="https://www.marianos.com/img/original.jpg?size=large" />
  </article>
  <article class="product-card">
    <a href="/p/fresh-fish/0001234000001"><h3>Fresh Fish</h3></a>
    <span data-testid="product-size">approx. 1.5 lb</span><span data-testid="price">$8.99</span>
  </article>
</main></body></html>
'''
DETAIL_HTML='''<main><h1>Kroger® Pasta Shells</h1><p>UPC: 0001234000078</p>
 <script type="application/ld+json">{"@type":"Product","gtin13":"0001234000078","name":"Kroger Pasta"}</script>
 <span data-testid="ppm">$0.19/oz</span></main>'''

def test_fields_exact_and_ordered():
    assert len(FIELDS)==22
    assert FIELDS[-1]=='crawl_date'
    assert FIELDS[17:21] == ('upc','gupc','ppm','unit_price')
    p=record({'category':'Grocery','product_title':'A','url':'https://www.marianos.com/p/a/123',
      'zipcode':'60404','store_location':'123 test road','regular_price':'$3.5',
      'upc':'0000000000123','gupc':'NEVER','unit_price':'12345','store_brand':'wrong'},'2026-10-17')
    assert list(p)==list(FIELDS)
    assert p['regular_price']=='3.50'
    assert p['upc']=='0000000000123'
    assert p['gupc']==p['unit_price']==''
    assert p['store_brand']=='no'
    assert p['crawl_date']=='2026-10-17'
    validate(p)
    assert 'remarks' not in p and 'gupc14' not in p
    assert 'null' not in json.dumps(p)

def test_no_calculated_ppm_or_promo():
    cases=[
      ('2 for $5','volume','5.00'),
      ('Buy 1, Get 1 Free','volume',''),
      ('Mix or Match 5 for $10','volume','10.00'),
      ('Must buy 4 at $1.99 each','volume','1.99'),
      ('Clip Coupon: Save $2','digital',''),
      ('$3.99 each with Digital Coupon','digital','3.99'),
      ('Save $5 when you buy 5 with Digital Coupon','digital',''),
      ('20% off with clipped coupon','digital',''),
      ('Regular sale today','other',''),
    ]
    for text,kind,price in cases:
        o=classify(text)
        assert (o.kind,o.displayed_price)==(kind,price),text

def test_extract_real_html_structure_without_inferred_values():
    cards=extract_cards(EXAMPLE_HTML,'Grocery','Pasta')
    assert len(cards)==1
    item=enrich_from_details(cards[0],DETAIL_HTML)
    assert item['upc']=='0001234000078'
    assert item['weight']=='16 oz'
    assert item['ppm']=='$0.19/oz'
    assert item['regular_price']=='3.99'
    assert item['sale_price']=='2.99'
    assert item['volume_deals_price']=='10.00'
    assert item['digital_deals_price']=='1.99'
    assert item['store_brand']=='yes'
    assert item['image_url']=='https://www.marianos.com/img/original.jpg?size=large'
    assert item['url'].endswith('/0001234000078?some=untouched')
    assert item['digital_deals_description'].endswith('Limit 5')

def test_weight_approximate_filters():
    for x in ['approx. 1 lb','approximately 2 oz','about 2 lb','Estimated Weight','avg. wt 4 lb']:
        assert APPROX_WEIGHT.search(x),x

def test_no_upc_or_ppm_made_up():
    cards=extract_cards('<article class="product-card"><a href="/p/pasta/0000000000001"><h3>Brand Pasta</h3></a><span data-testid="price">$5.00</span><span data-testid="product-size">10 oz</span></article>',"Grocery","Pasta")
    p=finalize_card(cards[0]); assert p['upc']=='' and p['ppm']==''
    assert p['regular_price']=='5.00'

def test_all_required_csv_categories_read():
    cats=load_categories('config/Marianos_Category_URLs.csv')
    assert len(cats)==28
    assert {c.name for c in cats}>={'Coupons','Produce','Light Bulbs','Hardware Home Improvement'}


def test_validation_rejects_wrong_field_order_and_approx():
    p=record({'category':'Grocery','product_title':'A','url':'https://www.marianos.com/p/a/123',
     'zipcode':'12345','store_location':'123 First'},'2026-10-17')
    with pytest.raises(RecordError):validate(dict(reversed(list(p.items()))))
    p['weight']='approximately 1.5 lbs'
    with pytest.raises(RecordError):validate(p)