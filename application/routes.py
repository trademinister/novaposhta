import traceback
import json
import base64
import sys
import os
import base64
import hashlib
import hmac
import time
import multiprocessing as mp
from urllib.parse import urlencode, quote_plus

import shopify
import requests
from flask import redirect, request, render_template, abort, jsonify, make_response, send_file, render_template_string
from flask import session as flask_session

from application import app
from application import cipher
from application.models import *
from application.lib import new_post
from application.lib.validator import *
from application.lib.main import *
from application.controllers.set_order import *
from application.controllers.get_rates import *
from application.controllers.load_counteragents import *

DIRNAME = app.config.get("DIRNAME")

@app.route("/install")
def install():
    return render_template("install.html")

@app.route('/start', methods=['GET'])
def start():
    came_from = request.args.get('shop')

    try:
        merchant = Merchant.get(Merchant.myshopify_domain == came_from)
    except Merchant.DoesNotExist:
        abort(403)

    valid = signature_validation(request.args.items(),app.config.get("SHOPIFY_API_SECRET"))

    if not (valid and merchant.active):
        abort(403)

    shippings = []

    with shopify.Session.temp(came_from, app.config.get("SHOPIFY_API_VERSION"), merchant.token):
        shop = shopify.Shop.current()

        locations = shopify.Location.find(limit=250)

    print('Getting metafields')

    fields = get_metafields(merchant.myshopify_domain, app.config.get("SHOPIFY_API_VERSION"), merchant.token, app.config.get("METAFIELD_NAMESPACE"), "data")

    print('Found metafields')

    if not fields:
        fields = {}

    language = fields.get('language', 'ru')

    fields['language'] = language

    try:
        with open("{}/application/static/json/locales/{}.json".format(DIRNAME, language), "r") as file:
            localization = json.loads(file.read())
    except FileNotFoundError:
        localization = {}

    if not fields and localization:

        fields = localization["fields"]

        fields = { key: "" for key in fields }

        loc_fields = localization["fields"]

        for key in loc_fields:
            fields[key] = ""

    try:
        post_key = fields['post_key']

        post = new_post.NewPost(post_key, 'json')

        counter_agents = [ (counter_agent, \
        [ (address['Description'], address['Ref']) \
        for address in post.get_counteragents_addresses(counter_agent['Ref'], 'Sender') ], \
        [ (contact['Description'], contact['Ref']) for contact in post.get_contacts(counter_agent['Ref']) ] ) \
        for counter_agent in post.get_counteragents('Sender') ]

    except Exception as e:
        print(str(e))
        counter_agents = []

    try:
        settlements = []

        with open('application/static/json/settlements.json', 'r') as file:
            settlements = [{
                "label": f'{settlement["Description"]}, {settlement["AreaDescription"]}',
                "value": settlement['Ref']
            } for settlement in json.loads(file.read()) if settlement["Warehouse"] == "1" ]

    except Exception as e:
        print(e)
        settlements = []

    try:
        with open("{}/application/static/json/fields.json".format(DIRNAME), "r") as file:
            scheme = json.loads(file.read())
    except FileNotFoundError:
        scheme = []

    blocks = localization.get("blocks") if localization.get("blocks") else {}

    scheme_fields = localization.get("fields") if localization.get("fields") else {}

    def circle(block, language):
        items = block["items"]

        for item in items:
            type = item.get("type", "")

            if type != "div":
                name = item["props"]["name"]

                if name == "sender":
                    options = []

                    for index, counter_agent in enumerate(counter_agents):
                        agent_data = counter_agent[0]

                        fio = f"{agent_data['LastName']} {agent_data['FirstName']} {agent_data['MiddleName']}"

                        options.append({
                            "label": fio,
                            "value": agent_data['Ref']
                        })

                    item["props"]["options"] = options

                elif name == "sender_city":
                    item["props"]["options"] = settlements

                item["props"]["label"] = scheme_fields.get(name) if scheme_fields.get(name) else "missing_translation_{}".format(name)
            else:
                circle(item, language)

    for block in scheme:
        id = block["id"]

        scheme_block = blocks.get(id)

        if not scheme_block:
            continue

        if id == 'location':
            block_items = block.get('items', [])

            for location in locations:
                location = location.to_dict()

                item_name = "location_{}".format(location['id'])

                localization['fields'][item_name] = location['name']

                block_items.append(
                    {
                        "type": "Select",
                        "props": {
                            "name": item_name,
                            "options": settlements
                        }
                    }
                )

        block["title"] = scheme_block["title"]

        block["description"] = scheme_block["description"]

        circle(block, language)

    return json.dumps({
        "status": True,
        "fields": fields,
        "scheme": scheme,
        "localization": localization,
        "counter_agents": counter_agents,
        "settlements": list(settlements)
    })

@app.route('/shop_erasure', methods=['POST'])
def shop_erasure():
    headers = request.headers

    if not 'X-Shopify-Shop-Domain' in headers:
        abort(403)

    myshopify_domain = headers['X-Shopify-Shop-Domain']

    if not request.is_json:
        abort(403)

    try:

        data = request.get_json()

        merchant = Merchant.get(Merchant.myshopify_domain == myshopify_domain)

        if not validate_webhook_request(request,app.config['SHOPIFY_API_SECRET']):
            abort(403)

        merchant.delete_instance()

    except Merchant.DoesNotExist:
        abort(422)

    return jsonify({"status":True})

@app.route('/app')
def home():
    print(session, "SESSION")
    try:
        print(request.args)
        # проверка подписи
        if not signature_validation(request.args.items(), app.config['SHOPIFY_API_SECRET']):
            abort(403)

        shop_name = request.args.get('shop')
        print(shop_name)
        flask_session['shop_name'] = shop_name

        headers = request.headers

        print(headers)

    except:
        traceback.print_exc()
        abort(403)

    return render_template('home.html')

@app.route('/authorize')
def authorize():
    def get_permission_url(shop_name):
        shopify.Session.setup(api_key=app.config['SHOPIFY_API_KEY'], secret=app.config['SHOPIFY_API_SECRET'])
        session = shopify.Session(shop_name, app.config.get("SHOPIFY_API_VERSION"))
        scope = app.config.get('SCOPE')
        redirect_url = app.config['REDIRECT_URL']
        return session.create_permission_url(scope, redirect_url)

    """авторизация приложения"""
    shop_name = request.args.get('shop')
    permission_url = get_permission_url(shop_name)
    return redirect(permission_url)

@app.route('/finalize')
def finalize():
    def create_carrier_service(shop_name, token):
        headers = prepare_api_headers(token)
        url = 'https://{}/admin/carrier_services.json'.format(shop_name)
        data = {
            'carrier_service': {
                'name': app.config.get('CARRIER_SERVICE'),
                'callback_url': 'https://{}/get_rates'.format(app.config.get("HOSTNAME")),
                'service_discovery': True
            }
        }

        return requests.post(url, json=data, headers=headers)

    print(request.args)

    shop_name = request.args.get('shop')

    shopify.Session.setup(api_key=app.config['SHOPIFY_API_KEY'],
                          secret=app.config['SHOPIFY_API_SECRET'])
    session = shopify.Session(shop_name, app.config.get("SHOPIFY_API_VERSION"))
    token = session.request_token(request.args.to_dict())

    c_response = create_carrier_service(shop_name, token)

    try:
        merchant = Merchant.get(Merchant.myshopify_domain == shop_name)
        print('merchant FOUND')
    except Merchant.DoesNotExist:
        print('MERCHANT NOT FOUND, CREATING A NEW ONE')
        merchant = Merchant()
        merchant.myshopify_domain = shop_name
        merchant.name = shop_name.split('.')[0]

    merchant.token = token
    merchant.save()

    """with shopify.Session.temp(shop_name, app.config.get("SHOPIFY_API_VERSION"), merchant.token):
        shop = shopify.Shop.current()

        for webhook in app.config.get("WEBHOOKS"):
            shopify_webhook = shopify.Webhook()

            shopify_webhook.topic = webhook["webhook"]
            shopify_webhook.address = webhook["url"]

            success = shopify_webhook.save()

            print(f"{webhook['webhook']} webhook installation: {success}")"""

    url = 'https://{}/admin/apps/{}'
    # редирект в админку
    return redirect(url.format(shop_name, app.config.get('SHOPIFY_API_KEY')))

@app.route('/update_shop', methods=['GET', 'POST'])
def update_shop():
    if request.method == 'GET':
        return jsonify({"status":True})

    print(request.is_json)
    print(request.get_data())
    print(request.headers)

    if not request.is_json:
        abort(400)

    data = request.get_json()

    print(data)

    came_from = data["search"]["shop"]

    try:
        merchant = Merchant.get(Merchant.myshopify_domain == came_from)
    except Merchant.DoesNotExist:
        abort(400)

    if not merchant.active or not signature_validation(data["search"].items(), app.config.get("SHOPIFY_API_SECRET")):
        abort(403)

    session = shopify.Session(came_from, app.config.get("SHOPIFY_API_VERSION"), merchant.token)

    shopify.ShopifyResource.activate_session(session)

    shop = shopify.Shop.current()

    metafield_data = json.dumps({
        "data": cipher.encrypt(json.dumps(data)).decode("utf-8")
    })

    merchant.merchant = metafield_data

    merchant.save()

    metafield = {
        'namespace': app.config.get('METAFIELD_NAMESPACE'),
        'key': "data",
        'value_type': "json_string",
        'value': metafield_data
    }

    print("metafield added: ", metafield)

    shop.add_metafield(shopify.Metafield(metafield))

    return jsonify({"status":True})
