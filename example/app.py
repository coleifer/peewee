import datetime
import peewee

from flask import Flask, request, session, g, redirect, url_for, \
        abort, render_template, flash
from functools import wraps
from hashlib import md5

# config
DATABASE = 'tweepee.db'
DEBUG = True
SECRET_KEY = 'hin6bab8ge25*r=x&amp;+5$0kn=-#log$pt^#@vrqjld!^2ci@g*b'

app = Flask(__name__)
app.config.from_object(__name__)

database = peewee.Database(DATABASE)

# model definitions
class User(peewee.Model):
    username = peewee.CharField()
    password = peewee.CharField()
    email = peewee.CharField()
    join_date = peewee.DateTimeField()

    class Meta:
        database = database

    def following(self):
        return User.select().join(
            Relationship, on='to_user_id'
        ).where(from_user=self).order_by('username')

    def followers(self):
        return User.select().join(
            Relationship
        ).where(to_user=self).order_by('username')

    def is_following(self, user):
        return Relationship.select().where(
            from_user=self,
            to_user=user
        ).count() > 0

    def gravatar_url(self, size=80):
        return 'http://www.gravatar.com/avatar/%s?d=identicon&s=%d' % \
            (md5(self.email.strip().lower().encode('utf-8')).hexdigest(), size)


class Relationship(peewee.Model):
    from_user = peewee.ForeignKeyField(User, related_name='relationships')
    to_user = peewee.ForeignKeyField(User, related_name='related_to')

    class Meta:
        database = database


class Message(peewee.Model):
    user = peewee.ForeignKeyField(User)
    content = peewee.TextField()
    pub_date = peewee.DateTimeField()

    class Meta:
        database = database


# utils
def create_tables():
    database.connect()
    User.create_table()
    Relationship.create_table()
    Message.create_table()

def auth_user(user):
    session['logged_in'] = True
    session['user'] = user
    session['username'] = user.username
    flash('You are logged in as %s' % (user.username))

def login_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return inner

def object_list(template_name, qr, var_name='object_list', **kwargs):
    kwargs.update(
        page=int(request.args.get('page', 1)),
        pages=qr.count() / 20 + 1
    )
    kwargs[var_name] = qr.paginate(kwargs['page'])
    return render_template(template_name, **kwargs)

# custom filters
@app.template_filter('is_following')
def is_following(from_user, to_user):
    return from_user.is_following(to_user)

# request handlers
@app.before_request
def before_request():
    g.db = database
    g.db.connect()

@app.after_request
def after_request(response):
    g.db.close()
    return response

# views
@app.route('/')
def homepage():
    if session.get('logged_in'):
        return private_timeline()
    else:
        return public_timeline()

@app.route('/private/')
def private_timeline():
    user = session['user']
    messages = Message.select().where(
        user__in=user.following()
    ).order_by(('pub_date', 'desc'))
    return object_list('private_messages.html', messages, 'message_list')

@app.route('/public/')
def public_timeline():
    messages = Message.select().order_by(('pub_date', 'desc'))
    return object_list('public_messages.html', messages, 'message_list')

@app.route('/join/', methods=['GET', 'POST'])
def join():
    if request.method == 'POST' and request.form['username']:
        try:
            user = User.get(username=request.form['username'])
            flash('That username is already taken')
        except StopIteration:
            user = User.create(
                username=request.form['username'],
                password=md5(request.form['password']).hexdigest(),
                email=request.form['email'],
                join_date=datetime.datetime.now()
            )
            auth_user(user)
            return redirect(url_for('homepage'))

    return render_template('join.html')

@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' and request.form['username']:
        try:
            user = User.get(
                username=request.form['username'],
                password=md5(request.form['password']).hexdigest()
            )
        except StopIteration:
            flash('The password entered is incorrect')
        else:
            auth_user(user)
            return redirect(url_for('homepage'))

    return render_template('login.html')

@app.route('/logout/')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('homepage'))

@app.route('/following/')
@login_required
def following():
    user = session['user']
    return object_list('user_following.html', user.following(), 'user_list')

@app.route('/followers/')
@login_required
def followers():
    user = session['user']
    return object_list('user_followers.html', user.followers(), 'user_list')

@app.route('/users/')
def user_list():
    users = User.select().order_by('username')
    return object_list('user_list.html', users, 'user_list')

@app.route('/users/<username>/')
def user_detail(username):
    try:
        user = User.get(username=username)
    except StopIteration:
        abort(404)
    messages = user.message_set.order_by(('pub_date', 'desc'))
    return object_list('user_detail.html', messages, 'message_list', user=user)

@app.route('/users/<username>/follow/', methods=['POST'])
@login_required
def user_follow(username):
    try:
        user = User.get(username=username)
    except StopIteration:
        abort(404)
    Relationship.get_or_create(
        from_user=session['user'],
        to_user=user,
    )
    flash('You are now following %s' % user.username)
    return redirect(url_for('user_detail', username=user.username))

@app.route('/users/<username>/unfollow/', methods=['POST'])
@login_required
def user_unfollow(username):
    try:
        user = User.get(username=username)
    except StopIteration:
        abort(404)
    Relationship.delete().where(
        from_user=session['user'],
        to_user=user,
    ).execute()
    flash('You are no longer following %s' % user.username)
    return redirect(url_for('user_detail', username=user.username))

@app.route('/create/', methods=['GET', 'POST'])
@login_required
def create():
    user = session['user']
    if request.method == 'POST' and request.form['content']:
        message = Message.create(
            user=user,
            content=request.form['content'],
            pub_date=datetime.datetime.now()
        )
        flash('Your message has been created')
        return redirect(url_for('user_detail', username=user.username))

    return render_template('create.html')


# allow running from the command line
if __name__ == '__main__':
    app.run()
