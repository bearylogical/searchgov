import logging
from typing import Any, Callable, Dict
import time
from supabase import create_client, Client, AuthApiError
import os

# from gotrue.types import Session
from gotrue import User, Session
from dotenv import load_dotenv
from loguru import logger
from nicegui import app, helpers, ui
from src.frontend import theme

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as ex:
    print(f"Supabase client error: {ex}")


def login_form() -> ui.element:
    with theme.frame("Login"):
        """Create and return the Supabase login form."""
        # Center the form both vertically and horizontally using a full-screen row
        with ui.row().classes("items-center justify-center").style(
            "object-position: center; height: 80vh;"
        ):
            # Create a card with a fixed width and centered
            with ui.card().classes("w-96 p-8"):
                email = (
                    ui.input("Email").props("type=email").classes("w-64")
                )
                password = ui.input(
                    "Password",
                    placeholder="Enter your password",
                    password=True,
                    password_toggle_button=True,
                ).classes("w-64")
                login_btn = ui.button(
                    "Login",
                    on_click=lambda: handle_login(
                        email.value, password.value
                    ),
                ).classes("mt-8")
                return login_btn


def handle_login(email: str, password: str):
    """Handle login with Supabase."""
    try:
        result = supabase.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
                # "options": {
                #     "emailRedirectTo": f"{SUPABASE_URL}/auth/callback"
                # },
            },
        )
        user = result.user
        session = result.session
        if user and session:
            app.storage.user.update(
                {
                    "supabase": {
                        "user": user.dict(),
                        "session": session.dict(),
                        "created_at": time.time(),
                    },
                    "is_authenticated": True,
                }
            )
            ui.notify("Login successful!", type="positive")
            ui.navigate.to("/")
        else:
            ui.notify("Login failed", type="negative")
    except AuthApiError as e:
        logger.error(f"Supabase login error: {e}")
        # Handle specific Supabase authentication errors
        if "seconds" in str(e):
            ui.notify(
                "Login failed: Too many attempts, try again later",
                type="negative",
            )
        else:
            ui.notify("Login failed", type="negative")


def about() -> Dict[str, Any]:
    """Return the user's Supabase profile."""
    return app.storage.user["supabase"]["user"]


def handle_logout() -> None:
    """Logout the user."""
    logging.info("Logging out user...")
    try:
        supabase.auth.sign_out()
        app.storage.user["supabase"] = None
        app.storage.user["is_authenticated"] = False
        ui.notify("Logged out", type="positive")
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        ui.notify("Logout failed", type="negative")
    ui.navigate.to("/")


class page(ui.page):
    """A page that requires the user to be logged in."""

    SESSION_TOKEN_REFRESH_INTERVAL = 30
    LOGIN_PATH = "/login"

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        async def content():
            await ui.context.client.connected()
            if await self._is_logged_in():
                if self.path == self.LOGIN_PATH:
                    self._refresh()
                    ui.navigate.to("/")
                    return
            else:
                if self.path != self.LOGIN_PATH:
                    ui.navigate.to(self.LOGIN_PATH)
                    return
                ui.timer(self.SESSION_TOKEN_REFRESH_INTERVAL, self._refresh)

            if helpers.is_coroutine_function(func):
                await func()
            else:
                func()

        return super().__call__(content)

    @staticmethod
    async def _is_logged_in() -> bool:
        user_data = app.storage.user.get("supabase")
        session_data: Session = (
            Session.validate(user_data.get("session"))
            if user_data
            else None
        )
        if not user_data or not user_data.get("session"):
            return False

        # Optionally, check if session is expired
        # print(session_data)
        if session_data.expires_in < (
            time.time() > user_data["created_at"] + session_data.expires_in
        ):
            return False
        try:
            supabase.auth.get_user(session_data.access_token)
            return True
        except Exception:
            logger.exception("Could not validate user session.")
            ui.notify("Session expired or invalid", type="negative")
            return False

    @staticmethod
    def _refresh() -> None:
        # Supabase sessions are auto-refreshed if using refresh_token
        pass


def login_page(func: Callable[..., Any]) -> Callable[..., Any]:
    """Marks the special page that will contain the login form."""
    return page(page.LOGIN_PATH)(func)
