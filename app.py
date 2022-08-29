from application import *

if __name__ == '__main__':
    app.run(host=app.config.get('IP'), port=app.config.get('PORT'), debug=True)
