import secrets

from nicegui import ui, app
from dotenv import load_dotenv
import os
from loguru import logger

import src.frontend.theme as theme
from src.frontend.utils.views import register_views
from src.state import shutdown_app_state, initialize_app_state
from src.middleware import AuthMiddleware

load_dotenv()

# check for debug mode
if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
    # Enable debug mode for NiceGUI
    os.environ["LOGURU_LEVEL"] = "DEBUG"
else:
    # Set the log level to INFO for production
    os.environ["LOGURU_LEVEL"] = "INFO"

# check for development mode
if os.getenv("DEV_MODE", "false").lower() == "true":
    # Enable development mode for NiceGUI
    os.environ["NICEGUI_DEV_MODE"] = "true"
    logger.info("Development mode is enabled. All authentication checks will be skipped.")
else:
    # Set the log level to INFO for production
    os.environ["NICEGUI_DEV_MODE"] = "false"
    app.add_middleware(AuthMiddleware)
    logger.info("Production mode is enabled. Authentication checks will be enforced.")  


@ui.page("/")
def main_page():
    """Main page for the Temporal Graph application."""
    with theme.frame("Home"):
        ui.label("Welcome to the SGDI Analytics Home Page").classes(
            "text-2xl font-bold"
        )


register_views()
app.on_startup(initialize_app_state)
app.on_shutdown(shutdown_app_state)
ui.run(
    port=8080,
    title="SGDI Analytics",
    storage_secret=os.getenv("SESSION_SECRET", secrets.token_hex(32)),
    host="0.0.0.0",
)
