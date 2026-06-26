from fastapi import Depends, FastAPI, HTTPException
from contextlib import asynccontextmanager
from peewee import *
from playhouse.pwasyncio import AsyncPostgresqlDatabase
from playhouse.pydantic_utils import to_pydantic


db = AsyncPostgresqlDatabase('peewee_test')

class User(db.Model):
    name = CharField(verbose_name='Full Name', help_text='Display name')
    email = CharField(unique=True)
    status = IntegerField(default=1, choices=(
        (1, 'Active'),
        (2, 'Inactive'),
        (3, 'Deleted')))

# Generate pydantic schemas suitable for create and responses.
# Schemas will include metadata from verbose_name, help_text, choices, and
# default settings.
UserCreate = to_pydantic(User, model_name='UserCreate')
UserResponse = to_pydantic(User, exclude_autofield=False, model_name='UserResponse')

async def get_db():
    # Hold a pooled connection open for the duration of the request.
    async with db:
        yield db

@asynccontextmanager
async def lifespan(app):
    # Create tables (if they don't exist) at application startup.
    async with db:
        await db.acreate_tables([User])
    yield
    await db.close_pool()  # Shut-down pool and exit.

app = FastAPI(lifespan=lifespan)

@app.get('/users', response_model=list[UserResponse])
async def list_users(db=Depends(get_db)):
    rows = await User.select().dicts().aexecute()
    return [UserResponse(**row) for row in rows]

@app.post('/users', response_model=UserResponse)
async def create_user(data: UserCreate, db=Depends(get_db)):
    user = await User.acreate(**data.model_dump())
    return UserResponse.model_validate(user)

@app.get('/users/{user_id}', response_model=UserResponse)
async def get_user(user_id: int, db=Depends(get_db)):
    try:
        user = await db.get(User.select().where(User.id == user_id))
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail='User not found')
    return UserResponse.model_validate(user)
