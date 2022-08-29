import time
import json
import datetime
import multiprocessing as mp
import os
import math
import uuid

import shopify
from flask import redirect, request, render_template, abort, jsonify, session, make_response, send_file, render_template_string

from application import app
from application.models import *
from application.lib.validator import *
from application.lib.main import *
from application.lib import yageocoder
from application.lib import new_post

EARTH_RADIUS = 6372 * 1000 # Радиус земли в метрах

TIMEOUT = 7

def calculate_service(data):
    service_type = data['service_type']
    deliv_time = data['deliv_time']
    shipping_price = data['shipping_price']
    redelivery_price = data['redelivery_price']
    parcel_points = data.get('parcel_points', tuple())

    rates = []

    city = str(uuid.uuid4())

    try:
        offset = datetime.timezone(datetime.timedelta(hours=3))

        max_days = datetime.datetime.strptime(deliv_time['DeliveryDate']['date'].split(' ')[0], '%Y-%m-%d').replace(tzinfo=datetime.timezone(datetime.timedelta(hours=0))) \
         - datetime.datetime.now(offset)

        max_days = max_days.days
    except Exception as e:
        print(str(e))

    min_days = max_days

    if service_type['code'] != 'WarehouseWarehouse':
        rate_name = f'Нова Пошта - доставка {service_type["name"]}'

        rates.append(get_rate(shipping_price, max_days, min_days, rate_name, f'{service_type["code"]}_{city}_0', 'UAH'))

        rates.append(get_rate(redelivery_price, max_days, min_days, f'{rate_name} - накладений платіж', f'{service_type["code"]}_{city}_1', 'UAH'))

    selected_points = []

    for parcel_point in parcel_points:
        distance, parcel_point = parcel_point

        rate = get_rate(shipping_price, max_days, min_days, f'{parcel_point["Description"]}', f'{service_type["code"]}_{city}_{parcel_point["Ref"]}_0', 'UAH')

        redelivery_rate = get_rate(redelivery_price, max_days, min_days, f'{parcel_point["Description"]} - накладений платіж', f'{service_type["code"]}_{city}_{parcel_point["Ref"]}_1', 'UAH')

        selected_points.append((distance, rate, redelivery_rate))

    print(len(parcel_points), "PARCEL POINTS")

    for index, parcel_point in enumerate(selected_points):
        distance, rate, redelivery_rate = parcel_point

        number = str(index + 1)

        if len(number) == 1:
            number = "00{}".format(number)

        if len(number) == 2:
            number = "0{}".format(number)

        rate['service_name'] = f'Нова Пошта ({number}) - {rate["service_name"]}'

        redelivery_rate['service_name'] = f'Нова пошта ({number}) - {redelivery_rate["service_name"]}'

        rates.append(rate)

        rates.append(redelivery_rate)

    return rates

@app.route('/get_rates', methods=['POST'])
def request_data():
    valid = validate_webhook_request(request, app.config.get("SHOPIFY_API_SECRET"))

    if not valid:
        abort(403)

    start_time = time.time()

    end_time = start_time + TIMEOUT

    data = request.get_json()["rate"]

    headers = request.headers

    myshopify_domain = headers['X-Shopify-Shop-Domain']

    # по магазину и выбранным городам не считать
    if myshopify_domain in ('myos-shop.myshopify.com', ):
        _cities = ('Київ', 'Киев', 'Дніпро', 'Днепр', 'Харків', 'Харьков')

        if data.get('destination').get('city') in _cities:
            total = 0

            for item in data.get('items'):
                total += item.get('price') * item.get('quantity')

            if total >= 50000:
                total_price = 0

            else:
                total_price = 10000

            return jsonify({'rates': [
                {
                    'service_name': 'Курьером по городу',
                    #'description': 'Курьером по городу',
                    'service_code': 'courier',
                    'currency': 'UAH',
                    'total_price': str(total_price),
                    #'min_delivery_date': '2020-09-15',
                    #'max_delivery_date': '2020-09-15'

                }
            ]})

    try:
        merchant = Merchant.get(Merchant.myshopify_domain == myshopify_domain)
    except Merchant.DoesNotExist:
        abort(403)

    session = shopify.Session(myshopify_domain, app.config.get("SHOPIFY_API_VERSION"), merchant.token)
    shopify.ShopifyResource.activate_session(session)

    shop = shopify.Shop.current()
    shop_metafields = shop.metafields()

    m_data = get_metafields(merchant.myshopify_domain, app.config.get("SHOPIFY_API_VERSION"), merchant.token, app.config.get("METAFIELD_NAMESPACE"), "data")

    max_parcel_points = int(m_data.get('max_parcel_points', 10))

    if max_parcel_points == -1:
        max_distance = max_parcel_points = float('inf')
    else:
        max_distance = int(m_data.get('max_distance', 5000))

    min_days = int(m_data.get('min_days', 1))

    max_days = int(m_data.get('max_days', 5))

    rates = []

    destination = data["destination"]
    raw_address = "{}, {}, {}".format(destination["city"], destination["address1"], destination["postal_code"])

    print(raw_address)
    items = data["items"]

    y_address = yageocoder.get_full_data(raw_address, 'uk_UA')

    post_key = m_data['post_key']

    post = new_post.NewPost(post_key, 'json')

    city = post.get_city(y_address['province'], y_address['locality'])['Ref']

    default_rate = get_rate(float(m_data.get('price', 600)), max_days, min_days, 'Новая Почта', f'{m_data.get("service_type", "WarehouseWarehouse")}_{city}_0', 'UAH' )

    try:
        print(y_address, "YANDEXA ADDRESS")

        total_weight_kg = 0
        total_price = 0

        for item in items:
            quantity = int(item["quantity"])

            total_weight_kg += item["grams"] * quantity

            total_price += item['price'] * quantity

        total_weight_kg /= 1000

        if not total_weight_kg:
            total_weight_kg = float(m_data.get('weight', .1))

        seats = int(round((total_weight_kg / 30) +.5))

        if seats < 1:
            seats = 1

        total_price /= 100

        delivery_city = post.get_city(y_address['province'], y_address['locality'])

        city_sender = m_data['sender_city']

        if not city:
            return abort(422)

        y_coords = y_address['coords']

        x = float(y_coords['lat']) * math.pi / 180

        sin_x = math.sin(x)
        cos_x = math.cos(x)

        y = float(y_coords['lon']) * math.pi / 180

        sin_y = math.sin(y)
        cos_y = math.cos(y)

        pool_data = []



        for service_type in new_post.SERVICE_TYPES:
            if not m_data.get(service_type['code'], False):
                continue

            deliv_time = post.send('InternetDocument', 'getDocumentDeliveryDate', {
                'CitySender': city_sender,
                'CityRecipient': city,
                'ServiceType': service_type['code']
            })['data'][0]

            if m_data.get('has_free_shipping_price', False) and total_price >= float(m_data.get('free_shipping_price', float('inf'))):
                redelivery_price = shipping_price = 0
            else:
                calc_data = post.send('InternetDocument', 'getDocumentPrice', {
                    'CitySender': city_sender,
                    'CityRecipient': city,
                    'Weight': total_weight_kg,
                    'ServiceType': service_type['code'],
                    'Cost': total_price,
                    'CargoType': m_data.get('cargo_type', 'Parcel'),
                    'SeatsAmount': round((total_weight_kg / 30) + .5),
                    'RedeliveryCalculate': {
                        'CargoType': 'Money',
                        'Amount': total_price
                    }
                }, False)['data'][0]

                redelivery_price = shipping_price = calc_data['Cost']

            parcel_points = []

            if service_type['code'] == 'WarehouseWarehouse':

                for index, parcel_point in enumerate(json.loads(City.get(City.city_ref == city).data)):
                    if parcel_point['CategoryOfWarehouse'] != 'Branch' or  \
                    (int(parcel_point['TotalMaxWeightAllowed']) < total_weight_kg and int(parcel_point['PlaceMaxWeightAllowed']) < total_weight_kg / seats):
                        print(parcel_point['TotalMaxWeightAllowed'])
                        continue

                    pvz_x = float(parcel_point['Latitude'])
                    pvz_y = float(parcel_point['Longitude'])

                    pvz_x = float(pvz_x) * math.pi / 180
                    pvz_y = float(pvz_y) * math.pi / 180

                    pvz_sin_x = math.sin(pvz_x)
                    pvz_cos_x = math.cos(pvz_x)

                    pvz_sin_y = math.sin(pvz_y)
                    pvz_cos_y = math.cos(pvz_y)

                    degree = math.acos(sin_x * pvz_sin_x + cos_x * pvz_cos_x * math.cos(y - pvz_y))

                    distance = EARTH_RADIUS * degree

                    if distance > max_distance:
                        continue

                    parcel_points.append((distance, parcel_point))

                parcel_points.sort(key=lambda item: item[0])

                parcel_points = parcel_points[0:max_parcel_points]

            pool_data.append({
                'service_type': service_type,
                'shipping_price': shipping_price,
                'redelivery_price': redelivery_price,
                'deliv_time': deliv_time,
                'parcel_points': parcel_points
            })


        pool = mp.Pool()

        results = [ pool.apply_async(calculate_service, (data,)) for data in pool_data ]

        for result in results:
            try:
                rates = [*rates, *result.get(timeout=(end_time - time.time()))]
            except Exception as e:
                continue

        pool.close()

        pool.join()

    except Exception as e:
        print(str(e))
        rates.append(default_rate)

    if not len(rates):
        rates.append(default_rate)

    print('start time - ', start_time)
    print('time time - ', time.time())

    return jsonify({"rates":list(rates)})
