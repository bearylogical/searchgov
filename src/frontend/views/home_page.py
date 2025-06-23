from nicegui import ui
from src.frontend import theme


@ui.page("/")
def content():
    """Content for the Home page."""

    with theme.frame("SGDI Analytics Home"):
        ui.label("Welcome to the SGDI Analytics Home Page").classes(
            "text-2xl font-bold"
        )
        ui.label(
            "Explore the Singapore Government DIrectory (SGDI) through various analytics functions."
        ).classes("text-lg")

        ui.separator().classes("my-4")

        # create a 3x1 grid with cards pointing to different pages with height of 14rem
        with ui.grid(columns=3):
            with ui.card().classes("p-4 hover:bg-gray-100 h-56"):
                ui.label("Career Progression").classes(
                    "text-xl font-semibold"
                )
                ui.label("Analyze career progression of a person.")
                ui.button(
                    "Go to Progression Viewer Page",
                    on_click=lambda: ui.navigate.to("/progression"),
                ).classes("mt-12")

            with ui.card().classes("p-4 hover:bg-gray-100 h-56"):
                ui.label("Connectivity Graph").classes(
                    "text-xl font-semibold"
                )
                ui.label(
                    "Visualize the connectivity between different people."
                )
                ui.button(
                    "Go to Connectivity Graph Page",
                    on_click=lambda: ui.navigate.to("/connectivity"),
                ).classes("mt-12")

            with ui.card().classes("p-4 hover:bg-gray-100 h-56"):
                ui.label("Organizational Evolution").classes(
                    "text-xl font-semibold"
                )
                ui.label(
                    "Explore the evolution of government organizations over time."
                )
                ui.button(
                    "Go to Evolution Page",
                    on_click=lambda: ui.navigate.to("/evolution"),
                ).classes("mt-12")
