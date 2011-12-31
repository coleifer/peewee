import datetime

from flask import Flask, request, session, g, redirect, url_for, \
        abort, render_template, flash
from functools import wraps
from hashlib import md5
from peewee import *

# config - aside from our database, the rest is for use by Flask
DATABASE = 'tweepee.db'
DEBUG = True
SECRET_KEY = 'hin6bab8ge25*r=x&amp;+5$0kn=-#log$pt^#@vrqjld!^2ci@g*b'

# create a flask application - this ``app`` object will be used to handle
# inbound requests, routing them to the proper 'view' functions, etc
app = Flask(__name__)
app.config.from_object(__name__)

# create a peewee database instance -- our models will use this database to
# persist information
database = SqliteDatabase(DATABASE)

# model definitions -- the standard "pattern" is to define a base model class
# that specifies which database to use.  then, any subclasses will automatically
# use the correct storage. for more information, see:
# http://charlesleifer.com/docs/peewee/peewee/models.html#model-api-smells-like-django
class BaseModel(Model):
    class Meta:
        database = database

# the user model specifies its fields (or columns) declaratively, like django
class User(BaseModel):
    username = CharField()
    password = CharField()
    email = CharField()
    join_date = DateTimeField()

    # it often makes sense to put convenience methods on model instances, for
    # example, "give me all the users this user is following":
    def following(self):
        # query other users through the "relationship" table
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


# this model contains two foreign keys to user -- it essentially allows us to
# model a "many-to-many" relationship between users.  by querying and joining
# on different columns we can expose who a user is "related to" and who is
# "related to" a given user
class Relationship(BaseModel):
    from_user = ForeignKeyField(User, related_name='relationships')
    to_user = ForeignKeyField(User, related_name='related_to')


# a dead simple one-to-many relationship: one user has 0..n messages, exposed by
# the foreign key.  because we didn't specify, a users messages will be accessible
# as a special attribute, User.message_set
class Message(BaseModel):
    user = ForeignKeyField(User)
    content = TextField()
    pub_date = DateTimeField()


# simple utility function to create tables
def create_tables():
    database.connect()
    User.create_table()
    Relationship.create_table()
    Message.create_table()

# flask provides a "session" object, which allows us to store information across
# requests (stored by default in a secure cookie).  this function allows us to
# mark a user as being logged-in by setting some values in the session data:
def auth_user(user):
    session['logged_in'] = True
    session['user'] = user
    session['username'] = user.username
    flash('You are logged in as %s' % (user.username))

# view decorator which indicates that the requesting user must be authenticated
# before they can access the view.  it checks the session to see if they're
# logged in, and if not redirects them to the login view.
def login_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return inner

# given a template and a SelectQuery instance, render a paginated list of
# objects from the query inside the template
def object_list(template_name, qr, var_name='object_list', **kwargs):
    kwargs.update(
        page=int(request.args.get('page', 1)),
        pages=qr.count() / 20 + 1
    )
    kwargs[var_name] = qr.paginate(kwargs['page'])
    return render_template(template_name, **kwargs)

# retrieve a single object matching the specified query or 404 -- this uses the
# shortcut "get" method on model, which retrieves a single object or raises a
# DoesNotExist exception if no matching object exists
# http://charlesleifer.com/docs/peewee/peewee/models.html#Model.get)
def get_object_or_404(model, **kwargs):
    try:
        return model.get(**kwargs)
    except model.DoesNotExist:
        abort(404)

# custom template filter -- flask allows you to define these functions and then
# they are accessible in the template -- this one returns a boolean whether the
# given user is following another user.
@app.template_filter('is_following')
def is_following(from_user, to_user):
    return from_user.is_following(to_user)

# request handlers -- these two hooks are provided by flask and we will use them
# to create and tear down a database connection on each request.  peewee will do
# this for us, but its generally a good idea to be explicit.
@app.before_request
def before_request():
    g.db = database
    g.db.connect()

@app.after_request
def after_request(response):
    g.db.close()
    return response

# views -- these are the actual mappings of url to view function
@app.route('/')
def homepage():
    # depending on whether the requesting user is logged in or not, show them
    # either the public timeline or their own private timeline
    if session.get('logged_in'):
        return private_timeline()
    else:
        return public_timeline()

@app.route('/private/')
def private_timeline():
    # the private timeline exemplifies the use of a subquery -- we are asking for
    # messages where the person who created the message is someone the current
    # user is following.  these messages are then ordered newest-first.
    user = session['user']
    messages = Message.select().where(
        user__in=user.following()
    ).order_by(('pub_date', 'desc'))
    return object_list('private_messages.html', messages, 'message_list')

@app.route('/public/')
def public_timeline():
    # simply display all messages, newest first
    messages = Message.select().order_by(('pub_date', 'desc'))
    return object_list('public_messages.html', messages, 'message_list')

@app.route('/join/', methods=['GET', 'POST'])
def join():
    if request.method == 'POST' and request.form['username']:
        try:
            # use the .get() method to quickly see if a user with that name exists
            user = User.get(username=request.form['username'])
            flash('That username is already taken')
        except User.DoesNotExist:
            # if not, create the user and store the form data on the new model
            user = User.create(
                username=request.form['username'],
                password=md5(request.form['password']).hexdigest(),
                email=request.form['email'],
                join_date=datetime.datetime.now()
            )
            
            # mark the user as being 'authenticated' by setting the session vars
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
        except User.DoesNotExist:
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
    # using the "get_object_or_404" shortcut here to get a user with a valid
    # username or short-circuit and display a 404 if no user exists in the db
    user = get_object_or_404(User, username=username)
    
    # get all the users messages ordered newest-first -- note how we're accessing
    # the messages -- user.message_set.  could also have written it as:
    # Message.select().where(user=user).order_by(('pub_date', 'desc'))
    messages = user.message_set.order_by(('pub_date', 'desc'))
    return object_list('user_detail.html', messages, 'message_list', user=user)

@app.route('/users/<username>/follow/', methods=['POST'])
@login_required
def user_follow(username):
    user = get_object_or_404(User, username=username)
    Relationship.get_or_create(
        from_user=session['user'],
        to_user=user,
    )
    flash('You are now following %s' % user.username)
    return redirect(url_for('user_detail', username=user.username))

@app.route('/users/<username>/unfollow/', methods=['POST'])
@login_required
def user_unfollow(username):
    user = get_object_or_404(User, username=username)
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
