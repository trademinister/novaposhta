import traceback
import json
import datetime

import shopify
from flask import redirect, request, render_template, abort, jsonify, session, make_response, send_file, render_template_string

from application import app
from application.models import *
from application.lib.validator import *
from application.lib.main import *
from application.lib import yageocoder
from application.lib import new_post

@app.route('/set_order', methods=['GET', 'POST'])
def set_order():
    shop_name = request.args.get('shop')

    id = request.args.get('ids[]')

    valid = signature_validation_v2(request, app.config['SHOPIFY_API_SECRET'])

    try:
        merchant = Merchant.get(Merchant.myshopify_domain == shop_name)
    except Merchant.DoesNotExist:
        abort(403)

    if not valid or not merchant.active:
        abort(403)

    m_data = get_metafields(merchant.myshopify_domain, app.config.get('SHOPIFY_API_VERSION'), merchant.token, app.config.get('METAFIELD_NAMESPACE'), 'data')

    post_key = m_data['post_key']

    post = new_post.NewPost(post_key, 'json')

    paid_amount = 0

    with shopify.Session.temp(merchant.myshopify_domain, app.config.get('SHOPIFY_API_VERSION'), merchant.token):
        shop = shopify.Shop.current().to_dict()

        order = shopify.Order.find(id).to_dict()

        transactions = shopify.Transaction.find(order_id=order['id'])

        print(transactions)

    shipping_address = order['shipping_address']

    raw_address = "{}, {}, {}, {}".format(shipping_address['province'], shipping_address["city"], shipping_address["address1"], shipping_address["zip"])

    validated_address = yageocoder.get_full_data(raw_address, 'uk_UA')

    city = post.get_city(validated_address['province'], validated_address['locality'])['Ref']

    for shipping_line in order['shipping_lines']:
        if shipping_line['source'] == app.config.get('CARRIER_SERVICE'):
            datas = shipping_line['code'].split('_')

            service_type = datas[0]

            code = datas[1]

            parcel_point = datas[2] if len(datas) > 2 and not datas[2] in {'1', '2'} else None

            break
    else:
        return abort(422)

    if request.method == 'GET':
        parcel_points = json.loads(City.get(City.city_ref == city).data)

        service_types = post.send('Common', 'getServiceTypes')['data']

        for index, service_type in enumerate(service_types):
            if service_type != 'WarehouseWarehouse':
                continue

            del service_types[index]

            break

        return render_template('set_order.html', parcel_points=parcel_points, service_types=service_types, parcel_point=parcel_point, service_type=datas[0])

    service_type = request.form['service_type']

    parcel_point = request.form['parcel_point']

    for transaction in transactions:
        transaction = transaction.to_dict()

        kind = transaction['kind']

        if kind in {'sale', 'refund', 'capture'}:
            amount = float(transaction['amount'])

            paid_amount += -amount if kind == 'refund' else amount


    locations = {
        'default': {
            'weight': 0,
            'items': []
        }
    }

    for item in order['line_items']:
        quantity = int(item['quantity'])

        weight = quantity * int(item['grams']) / 1000

        if 'origin_location' in item:
            origin_location = item['origin_location']

        else:
            origin_location = locations['default']

        location_id = origin_location['id']

        if not location_id in locations:
            locations[location_id] = {
                'weight': 0,
                'items': []
            }

        location = locations[location_id]

        location['items'].append(item)
        location['weight'] += weight

    province = validated_address['province']
    city = validated_address['locality']

    senders = post.get_counteragents('Sender')

    for sender in senders:
        if sender['Ref'] == m_data['sender']:
            break

    city_sender = m_data['sender_city']

    rec_city_data = post.get_city(province, city)

    city_recipient = rec_city_data['Ref']
    area_recipient = rec_city_data['Area']

    first_name = shipping_address['first_name']
    last_name = shipping_address['last_name']

    phone = order['phone'] if order['phone'] else shipping_address['phone']

    if not phone:
        phone = '380443231616'

    email = order['email'] if order['email'] else shipping_address['email']

    recipient_city = post.get_city(validated_address['province'], validated_address['locality'])['DeliveryCity']

    street_ref = post.get_street(recipient_city, validated_address['street'])['Ref']

    recipient = post.create_recipient(street_ref, validated_address['house'], shipping_address['address2'], first_name, last_name, phone, email)

    recipient_address = post.send('Counterparty', 'getCounterpartyAddresses', {
        'Ref': recipient['Ref'],
        'CounterpartyProperty': 'Recipient'
    })['data'][0]

    recipient_contact = post.send('Counterparty', 'getCounterpartyContactPersons', {
        'Ref': recipient['Ref'],
        'Page': 1
    })['data'][0]

    contact_sender = m_data.get('sender_contact')

    tracks = []

    for key in locations:
        location = locations[key]

        if not len(location['items']):
            continue

        weight = location['weight']

        if not weight:
            weight = float(m_data.get('weight', .1))

        today = datetime.datetime.utcnow() + datetime.timedelta(hours=3)

        weekday = today.weekday()

        if weekday == 5:
            today += datetime.timedelta(days=2)
        elif weekday == 6:
            today += datetime.timedelta(days=1)

        request_data = {
            'PayerType': 'Sender',
            'PaymentMethod': m_data.get('payment_method', 'Cash'),
            'DateTime': f'{today.day}.{today.month}.{today.year}',
            'CargoType': m_data.get('cargo_type', 'Parcel'),
            'Weight': weight,
            'SeatsAmount': round((weight / 30) + .5),
            'Description': order['id'],
            'Cost': order['subtotal_price'],
            'CitySender': city_sender,
            'Sender': sender['Ref'],
            'SenderAddress': m_data['sender_address'],
            'ContactSender': contact_sender,
            'SendersPhone': m_data['senders_phone'],
            'ContactRecipient': recipient_contact['Ref'],
            'RecipientsPhone': phone,
            'CityRecipient': city_recipient,
            'Recipient': recipient['Ref'],
            'RecipientAddress': recipient_address['Ref'],
            'ServiceType': service_type
        }

        if parcel_point:
            print(f'PARCEL_POINT {parcel_point}')

            request_data = {
                **request_data,
                **{
                    'NewAddress': '0',
                    'RecipientName': f'{first_name} {last_name}',
                    'RecipientCityName': city_recipient,
                    'RecipientAddressName': parcel_point,
                    'RecipientHouse': street_ref,
                    'RecipientType': 'PrivatePerson'
                }
            }

        if paid_amount > 0:
            request_data = {
                **request_data,
                **{
                    'BackwardDeliveryData': [
                        {
                            'PayerType': 'Sender',
                            'CargoType': 'Money',
                            'RedeliveryString': str(paid_amount)
                        }
                    ]
                }
            }

        response = post.send('InternetDocument', 'save', request_data)['data'][0]

        print(response)

        tracks.append(response['IntDocNumber'])

    with shopify.Session.temp(merchant.myshopify_domain, app.config.get('SHOPIFY_API_VERSION'), merchant.token):
        shop = shopify.Shop.current().to_dict()

        print(shop)

        fulfillment = shopify.Fulfillment({
              'order_id': order['id'],
              'line_items': order['line_items'],
              'location_id': shop['primary_location_id']
        })

        fulfillment.tracking_numbers = tracks
        fulfillment.tracking_company = app.config.get('CARRIER_SERVICE')
        fulfillment.tracking_urls = [ f'https://novaposhta.ua/ru/tracking/?cargo_number={track_number}&newtracking=1' for track_number in tracks ]
        fulfillment.notify_customer = True
        fulfillment.save()

    tracks_str = ','.join(tracks)

    shipping = Shipping()
    shipping.order_id = order['id']
    shipping.data = json.dumps(order)
    shipping.track_id = tracks_str
    shipping.save()

    print(len(post.send('Counterparty', 'getCounterpartyAddresses', {
        'Ref': recipient['Ref'],
        'CounterpartyProperty': 'Recipient'
    })['data']))

    return redirect(f'https://my.novaposhta.ua/orders/printDocument/orders/{tracks_str}/type/html/apiKey/{post_key}')
