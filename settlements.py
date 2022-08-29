import json
import os

from application.lib import new_post

token = '6c5806fb9bae90558ee9783c42a56973'

DIRNAME = os.getcwd()

if __name__ == '__main__':
    post = new_post.NewPost(token, 'json')

    print(f'{DIRNAME}/application/static/json/settlements.json')

    settlements = post.get_settlements()

    with open(f'{DIRNAME}/application/static/json/settlements.json', 'w') as file:
        file.write(json.dumps(settlements, ensure_ascii=False))
