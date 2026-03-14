from typing import Optional
import logging
from dotenv import load_dotenv
from loguru import logger
import os

# Import your facade
from src.app.temporal_graph import TemporalGraph

# We define the variable here, but it will be None until we explicitly
# initialize it. The type hint helps with autocompletion and static analysis.
graph_facade: Optional[TemporalGraph] = None

load_dotenv()
# extract env variables for database connection
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_DB = os.getenv("POSTGRES_DB", "temporal_org")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")


def _check_env() -> None:
    """Fail fast if required environment variables are missing."""
    missing = [
        var
        for var in (
            "POSTGRES_HOST",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
        )
        if not os.getenv(var)
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in the values."
        )


async def initialize_app_state():
    """
    Creates the single instance of our TemporalGraph facade.
    This should be called once when the application starts.
    """
    global graph_facade
    if graph_facade is None:
        _check_env()
        logger.info("🚀 Initializing TemporalGraph facade...")
        try:
            graph_facade = TemporalGraph(
                host=POSTGRES_HOST,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                port=POSTGRES_PORT,
            )
            await graph_facade.db_connection.connect()
            logger.info("✅ TemporalGraph facade initialized.")
        except Exception as e:
            logger.error(
                f"❌ Failed to initialize TemporalGraph facade: {e}"
            )
    else:
        logger.warning("⚠️ TemporalGraph facade already initialized.")


async def shutdown_app_state():
    """
    Gracefully shuts down the facade, closing database connections.
    This should be called once when the application stops.
    """
    global graph_facade
    if graph_facade:
        logger.info("🔌 Shutting down TemporalGraph facade...")
        await graph_facade.close()
        graph_facade = None
        logger.info("✅ TemporalGraph facade shut down.")
