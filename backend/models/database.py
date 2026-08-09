"""Shared MongoDB client/database handle."""
from motor.motor_asyncio import AsyncIOMotorClient

from utils import config

client = AsyncIOMotorClient(config.MONGO_URL)
db = client[config.DB_NAME]


def close_client() -> None:
    client.close()
