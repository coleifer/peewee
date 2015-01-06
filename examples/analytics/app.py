"""
Example "Analytics" app. To start using this on your site, do the following:

* Create a postgresql database with HStore support:

    createdb analytics
    psql analytics -c "create extension hstore;"

* Create an account for each domain you intend to collect analytics for, e.g.

    Account.create(domain='charlesleifer.com')

* Update configuration values marked "TODO", e.g. DOMAIN.

* Run this app using the WSGI server of your choice.

* Using the appropriate account id, add a `<script>` tag to each site you want
  to collect analytics data from. I place mine at the bottom of the <body>:

    <script src="http://yourdomain.com/a.js?id=<your account id>"></script>

Take a look at `reports.py` for some interesting queries you can perform
on your pageview data.
"""
import datetime
import os
from urlparse import parse_qsl, urlparse

from flask import Flask, Response, abort, request
from peewee import create_model_tables
from peewee import *
from playhouse.postgres_ext import HStoreField
from playhouse.postgres_ext import PostgresqlExtDatabase


# Analytics settings.
BEACON = '47494638396101000100800000dbdfef00000021f90401000000002c00000000010001000002024401003b'.decode('hex')  # 1px gif.
DATABASE_NAME = 'analytics'
DOMAIN = 'http://analytics.yourdomain.com'  # TODO: change me.
JAVASCRIPT = """(function(id){
    var d=document,i=new Image,e=encodeURIComponent;
    i.src='%s/a.gif?id='+id+'&url='+e(d.location.href)+'&ref='+e(d.referrer)+'&t='+e(d.title);
    })(%s)""".replace('\n', '')

# Flask settings.
DEBUG = bool(os.environ.get('DEBUG'))
SECRET_KEY = 'secret - change me'  # TODO: change me.

app = Flask(__name__)
app.config.from_object(__name__)

database = PostgresqlExtDatabase(
    DATABASE_NAME,
    user='postgres')

class BaseModel(Model):
    class Meta:
        database = database

class Account(BaseModel):
    domain = CharField()

    def verify_url(self, url):
        netloc = urlparse(url).netloc
        url_domain = '.'.join(netloc.split('.')[-2:])  # Ignore subdomains.
        return self.domain == url_domain

class PageView(BaseModel):
    account = ForeignKeyField(Account, related_name='pageviews')
    url = TextField()
    timestamp = DateTimeField(default=datetime.datetime.now)
    title = TextField(default='')
    ip = CharField(default='')
    referrer = TextField(default='')
    headers = HStoreField()
    params = HStoreField()

    @classmethod
    def create_from_request(cls, account, request):
        parsed = urlparse(request.args['url'])
        params = dict(parse_qsl(parsed.query))

        return PageView.create(
            account=account,
            url=parsed.path,
            title=request.args.get('t') or '',
            ip=request.headers.get('x-forwarded-for', request.remote_addr),
            referrer=request.args.get('ref') or '',
            headers=dict(request.headers),
            params=params)

@app.route('/a.gif')
def analyze():
    # Make sure an account id and url were specified.
    if not request.args.get('id') or not request.args.get('url'):
        abort(404)

    # Ensure the account id is valid.
    try:
        account = Account.get(Account.id == request.args['id'])
    except Account.DoesNotExist:
        abort(404)

    # Ensure the account id matches the domain of the URL we wish to record.
    if not account.verify_url(request.args['url']):
        abort(403)

    # Store the page-view data in the database.
    PageView.create_from_request(account, request)

    # Return a 1px gif.
    response = Response(app.config['BEACON'], mimetype='image/gif')
    response.headers['Cache-Control'] = 'private, no-cache'
    return response

@app.route('/a.js')
def script():
    account_id = request.args.get('id')
    if account_id:
        return Response(
            app.config['JAVASCRIPT'] % (app.config['DOMAIN'], account_id),
            mimetype='text/javascript')
    return Response('', mimetype='text/javascript')

@app.errorhandler(404)
def not_found(e):
    return Response('<h3>Not found.</h3>')

# Request handlers -- these two hooks are provided by flask and we will use them
# to create and tear down a database connection on each request.
@app.before_request
def before_request():
    g.db = database
    g.db.connect()

@app.after_request
def after_request(response):
    g.db.close()
    return response


if __name__ == '__main__':
    create_model_tables([Account, PageView], fail_silently=True)
    app.run(debug=True)
