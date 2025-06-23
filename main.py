from nicegui import ui, app
from dotenv import load_dotenv
import os


import src.frontend.theme as theme
from src.frontend.utils.views import register_views
from src.state import shutdown_app_state, initialize_app_state

load_dotenv()

# check for debug mode
if os.getenv("DEBUG_MODE", "False").lower() == "true":
    # Enable debug mode for NiceGUI
    os.environ["LOGURU_LEVEL"] = "DEBUG"
else:
    # Set the log level to INFO for production
    os.environ["LOGURU_LEVEL"] = "INFO"


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
ui.run(title="SGDI Analytics", storage_secret="test_secret")
