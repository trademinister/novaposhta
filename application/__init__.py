# coding: utf-8
import sys
import os
import logging

#logging.basicConfig(filename="logs.log", level=logging.INFO)

from flask import Flask
from flask_peewee.db import Database
from flask_cors import CORS
from flask_migrate import Migrate

app = Flask(__name__)
app.config.from_pyfile('config.py')

if os.environ.get('YOURAPPLICATION_SETTINGS'):
    app.config.from_envvar('YOURAPPLICATION_SETTINGS')

db = Database(app)
CORS(app, supports_credentials=True)
migrate = Migrate(app, db)

from application.lib.aescipher import AESCipher

KEY_CRYPTO = app.config.get("SECRET_KEY")
cipher = AESCipher(KEY_CRYPTO)

from application import models
from application import routes
