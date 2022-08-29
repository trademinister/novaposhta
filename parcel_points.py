import json
import os
import multiprocessing as mp

import requests
import pymysql

from application.lib import new_post
from application.lib import yageocoder

DIRNAME = os.getcwd()

if __name__ == '__main__':
    with open(f'{DIRNAME}/application/static/json/settlements.json', 'r') as file:
        settlements =  json.loads(file.read())

    def pool_function(city):
        post = new_post.NewPost('6c5806fb9bae90558ee9783c42a56973', 'json')

        city_ref = city['Ref']

        response = post.send('AddressGeneral', 'getWarehouses', {
            'limit': 500,
            'SettlementRef': city_ref
        })

        parcel_points = response['data']

        connection = pymysql.connect('localhost', 'root', '', 'new_post', charset='utf8')

        with connection:
            cursor = connection.cursor()

            if not len(parcel_points):
                return

            search_sql = f'SELECT `id` FROM `city` WHERE `city_ref`="{city_ref}"'

            cursor.execute(search_sql)

            search_result = cursor.fetchone()

            json_string = json.dumps(parcel_points, ensure_ascii=False)

            update_sql = "UPDATE city SET data=%s WHERE id={}".format(search_result[0]) if search_result else \
            "INSERT INTO city (city_ref, data) VALUES ('{}', %s)".format(city_ref)

            cursor.execute(update_sql, (json_string,))

    for settlement in settlements:
        if settlement['Warehouse'] != '1':
            continue

        process = mp.Process(target=pool_function, args=(settlement,))

        process.start()
