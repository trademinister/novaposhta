import difflib
import multiprocessing as mp

import requests
'''
SERVICE_TYPES = (
    {
        'code': 'DoorsDoors',
        'name': 'От двери до двери'
    },
    {
        'code': 'DoorsWarehouse',
        'name': 'От двери до склада'
    },
    {
        'code': 'WarehouseWarehouse',
        'name': 'От склада до склада'
    },
    {
        'code': 'WarehouseDoors',
        'name': 'От склада до двери'
    }
)
'''


SERVICE_TYPES = (
    {
        'code': 'DoorsDoors',
        'name': 'Від дверей до дверей'
    },
    {
        'code': 'DoorsWarehouse',
        'name': 'Від дверей до складу'
    },
    {
        'code': 'WarehouseWarehouse',
        'name': 'Від складу до складу'
    },
    {
        'code': 'WarehouseDoors',
        'name': 'Від складу до дверей'
    }
)



def get_match_ratio(s1, s2):
  normalized1 = s1.lower()
  normalized2 = s2.lower()

  matcher = difflib.SequenceMatcher(None, normalized1, normalized2)

  return matcher.ratio()

class NewPost(object):
    def __init__(self, api_key, format):
        self.url = f'https://api.novaposhta.ua/v2.0/{format}/'
        self.api_key = api_key

    def send(self, model_name, called_method, method_properties={}, use_key=True):
        request_data = {
            'modelName': model_name,
            'calledMethod': called_method,
            'methodProperties': method_properties
        }

        if use_key:
            request_data['apiKey'] = self.api_key

        #print(request_data)

        response = requests.post(self.url, json=request_data)

        response_data = response.json()

        #print(response_data)

        if not response_data.get('success'):
            raise Exception(', '.join(response_data.get('errors', [])))

        return response_data

    def get_city(self, province, city, limit=5):
        cities = self.send('Address', 'searchSettlements', {
            'CityName': city,
            'Limit': limit
        })

        result = None

        max_match = 0

        for current_city in cities['data'][0]['Addresses']:
            match_ratio = get_match_ratio(city, current_city['MainDescription'])

            if match_ratio > max_match:
                max_match = match_ratio

                result = current_city

        return result

    def get_address(self, city_ref, street, limit=500):
        max_match = 0

        result = None

        page = 1

        request_data = {
            'StreetName': street,
            'SettlementRef': city_ref,
            'Limit': limit
        }

        response_data = self.send('Address', 'searchSettlementStreets', request_data)

        addresses = response_data['data'][0]['Addresses']

        if not len(addresses):
            raise Exception('No addresses found')

        for address in addresses:
            print(street, address['SettlementStreetDescription'])

            match_ratio = get_match_ratio(street, address['SettlementStreetDescription'])

            if match_ratio >= max_match:
                max_match = match_ratio

                result = address

        return result

    def get_street(self, city_ref, street, limit=500):
        page = 1

        request_data = {
            'StreetName': street,
            'CityRef': city_ref
        }

        max_match = 0

        result = None

        while True:
            request_data['Page'] = page

            response_data = self.send('Address', 'getStreet', request_data)

            streets = response_data['data']

            if not len(streets):
                break

            for post_street in streets:

                match_ratio = get_match_ratio(street, post_street['Description'])

                if match_ratio >= max_match:
                    max_match = match_ratio

                    result = post_street

            page += 1

        if not result:
            raise Exception('No addresses found')

        return result


    def get_settlements(self, ref='', region_ref='', string='', warehouse=''):
        result = []

        data = {
            "limit": 500
        }

        if ref:
            data['Ref'] = ref

        if region_ref:
            data['RegionRef'] = region_ref

        if string:
            data['FindByString'] = string

        page = 1

        while True:
            data['Page'] = page

            response = self.send('AddressGeneral', 'getSettlements', data)

            if not len(response['data']):
                break

            result.extend(response['data'])

            page += 1

        return result

    def create_sender(self, first_name, last_name, phone, email, type, middle_name=''):
        return self.send('Counterparty', 'save', {
            'FirstName': first_name,
            'MiddleName': middle_name,
            'LastName': last_name,
            'Phone': phone,
            'Email': email,
            'CounterpartyType': type,
            'CounterpartyProperty': 'Sender'
        })

    def get_sender(self, counterparty_type):
        page = 1

        while True:
            response = self.send('Counterparty', 'getCounterparties', {
                'CounterpartyProperty': 'Sender',
                'Page': page
            })

            if not len(response['data']):
                break

            for sender in response['data']:
                if sender['CounterpartyType'] == counterparty_type:
                    return sender

            page += 1

    def get_contacts(self, ref):
        page = 1

        request_data = {
            'Ref': ref
        }

        results = []

        while True:
            request_data['Page'] = page

            response = self.send('Counterparty', 'getCounterpartyContactPersons', request_data)

            contacts = response['data']

            if not len(contacts):
                break

            results.extend(contacts)

            page += 1

        return results

    def get_sender_contact(self, ref, fio):
        page = 1

        result = None

        max_match = 0

        while True:
            response = self.send('Counterparty', 'getCounterpartyContactPersons', {
                'Ref': ref,
                'Page': page
            })

            if not len(response['data']):
                break

            for contact in response['data']:

                match_ratio = get_match_ratio(fio, contact['Description'])

                if match_ratio >= max_match:
                    max_match = match_ratio

                    result = contact

            page += 1

        return result

    def get_counteragents_addresses(self, ref, type):
        return self.send('Counterparty', 'getCounterpartyAddresses', {
            'Ref': ref,
            'CounterpartyProperty': type
        })['data']

    def get_counteragents_contacts(self, ref):
        result = []

        page = 1

        while True:
            response = self.send('Counterparty', 'getCounterpartyContactPersons')

            if not len(response['data']):
                break

            for contact in response['data']:
                contact['AgentRef'] = ref

            result.extend(response['data'])

            page += 1

        return result

    def get_counteragents(self, type=''):
        result = []

        request_data = {}

        if type:
            request_data['CounterpartyProperty'] = type

        page = 1

        while True:
            request_data['Page'] = page

            response = self.send('Counterparty', 'getCounterparties', request_data)

            if not len(response['data']):
                break

            result.extend(response['data'])

            page += 1

        return result

    def create_recipient(self, street_ref, building, flat, first_name, last_name, phone, email, middle_name=''):
        response = self.send('Counterparty', 'save', {
            'FirstName': first_name,
            'MiddleName': middle_name,
            'LastName': last_name,
            'Phone': phone,
            'Email': email,
            'CounterpartyType': 'PrivatePerson',
            'CounterpartyProperty': 'Recipient'
        })

        response_data = response['data'][0]

        contact_response = self.send('ContactPerson', 'save', {
            'CounterpartyRef': response_data['Ref'],
            'FirstName': first_name,
            'LastName': last_name,
            'MiddleName': middle_name,
            'Phone': phone
        })

        address_data = {
            'Ref': response_data['Ref']
        }

        recipient_addresses = self.send('Counterparty', 'getCounterpartyAddresses', address_data)

        for address in recipient_addresses['data']:
            self.send('Address', 'delete', {
                'Ref': address['Ref']
            })

        self.send('Address', 'save', {
            'CounterpartyRef': response_data['Ref'],
            'StreetRef': street_ref,
            'BuildingNumber': building,
            'Flat': flat,
            'Note': ''
        })

        return response_data

    def get_parcel_points(self, city_name='', city_ref='', limit=500, language=None, max_points=500):
        page = 1

        parcel_points = []

        data = {
        }

        if limit:
            data['limit'] = limit

        if city_name:
            data['CityName'] = city_name

        if city_ref:
            data['CityRef'] = city_ref

        if language:
            data['Language'] = language

        while len(parcel_points) <= max_points:

            data['Page'] = page
            data['page'] = page

            response = self.send('AddressGeneral', 'getWarehouses', data)

            response_data = response['data']

            if not len(response_data):
                search = False

                break

            for parcel_point in response_data:
                parcel_points.append(parcel_point)

                if len(parcel_points) >= max_points:
                    break

            page += 1

        return parcel_points
