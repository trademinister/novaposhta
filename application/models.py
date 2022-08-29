from peewee import CharField, DateTimeField, TextField, BooleanField, IntegerField, FloatField
from application import db

import datetime

class Shipping(db.Model):
    id = IntegerField(primary_key=True)
    order_id = IntegerField(unique=True)
    data = CharField(null=True)
    created = DateTimeField(default=datetime.datetime.utcnow, null=True)
    track_id = CharField(null=True)
    updated = DateTimeField(default=datetime.datetime.utcnow, null=True)

class Merchant(db.Model):
    id = IntegerField(primary_key=True)
    myshopify_domain = CharField(unique=True)
    name = CharField(null=True)
    merchant = TextField(null=True)
    updated = DateTimeField(default=datetime.datetime.utcnow, null=True)  # время создания в юникоде
    active = BooleanField(default=True, null=True) # Доступен ли магазин или нет
    token = CharField(null=True)

class City(db.Model):
    id = IntegerField(primary_key=True)
    city_ref = CharField(null=False)
    data = TextField()
