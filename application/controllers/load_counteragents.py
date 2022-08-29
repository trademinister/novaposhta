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


def load_counteragents():
    shop_name = session["shop_name"]


    try:
        merchant = Merchant.get(Merchant.myshopify_domain == shop_name)
    except Merchant.DoesNotExist:
        abort(403)

    if not merchant.active:
        abort(403)

    m_data = get_metafields(merchant.myshopify_domain, app.config.get("SHOPIFY_API_VERSION"), merchant.token, app.config.get("METAFIELD_NAMESPACE"), "data")

    post_key = m_data['post_key']

    post = new_post.NewPost(post_key, 'json')

    counter_agents = [ (counter_agent, post.get_counteragents(counter_agent['Ref'], 'Sender')) \
    for counter_agent in post.get_counteragents('Sender') ]

    return jsonify(counter_agents)
