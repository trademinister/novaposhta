import json
import shopify
import datetime
import requests
import time

from application.models import Merchant
from application import cipher, app

def parse_metafield_value(metafield):
    value = metafield if isinstance(metafield, str) else metafield.value

    return json.loads(cipher.decrypt(json.loads(value)["data"].encode("utf-8")))

def pause_sdk(sleep):
    if shopify.Limits.credit_used() > shopify.Limits.credit_limit() / 2:
        time.sleep(sleep)


def get_metafields(store_name, api_version, store_token, namespace, key):
    try:
        merchant = Merchant.get(Merchant.myshopify_domain == store_name)
    except Exception as e:
        print(e)

    if merchant.merchant:
        return parse_metafield_value(merchant.merchant)

    with shopify.Session.temp(store_name, api_version, store_token):
        shop = shopify.Shop.current()

        metafields = shopify.Metafield.find(namespace=namespace, key=key)

        if not len(metafields):
            return None

        return parse_metafield_value(metafields[0])

def get_permission_url(shop_name):
    shopify.Session.setup(api_key=app.config['SHOPIFY_API_KEY'],
                          secret=app.config['SHOPIFY_API_SECRET'])
    session = shopify.Session(shop_name)
    scope = app.config.get('SCOPE')
    redirect_url = app.config['REDIRECT_URL']
    return session.create_permission_url(scope, redirect_url)

def prepare_api_headers(token):
    return {"X-Shopify-Access-Token": token,"Content-Type": "application/json"}

def create_carrier_service(shop_name,token):
    headers = prepare_api_headers(token)
    url = 'https://{}/admin/carrier_services.json'.format(shop_name)
    data = {
        'carrier_service': {
            'name': 'Axibox',
            'callback_url': 'https://{}/request_data'.format(app.config.get("HOSTNAME")),
            'service_discovery': True
        }
    }

    return requests.post(url, json=data, headers=headers)

def get_rate(price=600,max_days=3,min_days=14, service_name="", service_code="", currency=""):
    time_now = datetime.datetime.now()
    min_delivery = (time_now + datetime.timedelta(days=min_days)).strftime('%Y-%m-%d')
    max_delivery = (time_now + datetime.timedelta(days=max_days)).strftime('%Y-%m-%d')

    return {
        "service_name": service_name,
        "service_code": service_code,
        "total_price": int(float(price) * 100),
        "currency": currency,
        "min_delivery_date": min_delivery,
        "max_delivery_date": max_delivery
    }
