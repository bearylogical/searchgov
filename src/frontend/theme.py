from contextlib import contextmanager

from nicegui import ui, app  # Import our registry
from src.frontend.registry import PAGES
from src.auth import handle_logout


@contextmanager
def frame(navigation_title: str):
    """Custom page frame with a dynamically generated navigation menu."""
    # This is the key addition: It forces the main layout to fill the screen's height.
    ui.query(".q-layout").style("min-height: 100vh;")

    with ui.header(elevated=True).style(
        "background-color: #3874c8"
    ).classes("items-center justify-between"):
        with ui.row().classes("w-full items-center"):
            ui.label("SGDI Analytics |").on(
                "click", lambda e: ui.navigate.to("/")
            ).tailwind("text-4xl cursor-pointer")
            ui.label(navigation_title).tailwind("text-4xl")
            ui.element("div").classes("flex-1")  # Spacer

            if app.storage.user.get("is_authenticated"):
                # Show the user profile icon if authenticated
                with ui.element("div").classes("flex items-center gap-2"):
                    ui.icon("account_circle").classes("text-3xl")
                    ui.label(
                        app.storage.user["supabase"]["user"]["email"]
                    ).tailwind("text-lg")
                    ui.button(
                        "Logout", on_click=lambda: handle_logout()
                    ).tailwind("bg-red-500 text-white px-4 py-2 rounded")

            with ui.button(icon="menu"):
                with ui.menu():
                    # Dynamically create menu items from the registry
                    for page in PAGES:
                        ui.menu_item(
                            page["name"],
                            # NOTE: We use a lambda with a default argument
                            # to correctly capture the path for each iteration.
                            on_click=lambda p=page: ui.navigate.to(
                                p["path"]
                            ),
                        )
    # This container is a flex column. Now that its parent has height,
    # `flex-grow` will correctly expand it to fill the space.
    with ui.element("div").classes(
        "flex flex-col w-full p-4 gap-4 flex-grow"
    ):
        yield
    with ui.footer().style("background-color: #3874c8"):
        ui.label("FOOTER")
