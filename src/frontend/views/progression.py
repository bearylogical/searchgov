# src/frontend/pages/progression.py

import asyncio
from typing import Any, Dict, Optional

from nicegui import ui, run
from loguru import logger

import src.frontend.theme as theme
import src.state as app_state
from src.frontend.components import profile_display

running_query_a: Optional[asyncio.Task] = None


@ui.page("/progression")
def content() -> None:
    refs = {}
    wizard_state = {
        "person_a": None,
        "person_a_employment": [],
        "person_a_consolidated_profile": None,
    }

    def update_person_a_ui():
        """Update the UI using the shared components."""
        if not refs.get("timeline_container") or not refs.get(
            "profile_container"
        ):
            return

        def handle_remove(record: Dict):
            """Callback to handle removing an employment record."""
            try:
                wizard_state["person_a_employment"].remove(record)
                ui.notify("Employment record removed.", type="info")
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not remove employment: {e}")
            finally:
                update_person_a_ui()  # Re-render after state change

        profile_display.build_timeline(
            refs["timeline_container"],
            wizard_state["person_a_employment"],
            on_remove=handle_remove,
        )
        profile = profile_display.build_profile_card(
            refs["profile_container"],
            wizard_state["person_a"],
            wizard_state["person_a_employment"],
        )
        wizard_state["person_a_consolidated_profile"] = profile

    async def search_person_a(search_term: str):
        global running_query_a
        if not search_term:
            refs["search_results_a"].clear()
            return
        if running_query_a:
            running_query_a.cancel()

        coro = run.io_bound(
            app_state.graph_facade.find_person_by_name,
            search_term,
            is_fuzzy=True,
        )
        task = asyncio.create_task(coro)
        running_query_a = task
        try:
            people = await task
            if running_query_a is not task:
                return
            refs["search_results_a"].clear()
            with refs["search_results_a"]:
                if not people:
                    ui.label("No results found.")
                    return
                for person in people:
                    with ui.card().classes(
                        "cursor-pointer hover:bg-gray-200 w-full"
                    ):
                        with ui.row().classes("items-center gap-2").on(
                            "click", lambda p=person: select_person_a(p)
                        ):
                            ui.label(person["name"])
                            parent_entity = (
                                profile_display.get_parent_entity(
                                    person.get("linked_organizations", [])
                                )
                            )
                            if parent_entity["acronym"] != "UNK":
                                ui.label(parent_entity["acronym"]).tailwind(
                                    "bg-red-100 text-red-800 text-sm font-medium me-2 px-2.5 py-0.5 rounded-sm dark:bg-red-900 dark:text-red-300"
                                )
                            ui.label(
                                person["employment_profile"][-1]["org_name"]
                            ).tailwind(
                                "bg-green-100 text-green-800 text-sm font-medium me-2 px-2.5 py-0.5 rounded-sm dark:bg-green-900 dark:text-green-300"
                            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error during search: {e}")
            ui.notify(
                f"An error occurred during search: {e}", type="negative"
            )

    async def select_person_a(person: Dict[str, Any]):
        wizard_state["person_a"] = person
        refs["selected_person_a_label"].set_text(
            f"Selected: {person['name']}"
        )
        refs["search_results_a"].clear()
        ui.notify(f"Selected {person['name']}", type="positive")

        employment_profile = await run.io_bound(
            app_state.graph_facade.get_career_progression_by_name,
            person["name"],
        )
        if employment_profile:
            employment_profile.sort(
                key=lambda x: x.get("start_date", "9999-12-31")
            )
            wizard_state["person_a_employment"] = employment_profile
        else:
            wizard_state["person_a_employment"] = []
        update_person_a_ui()

    def reset_search_a_handler():
        refs["search_results_a"].clear()
        refs["selected_person_a_label"].set_text("Selected: None")
        wizard_state["person_a"] = None
        wizard_state["person_a_employment"] = []
        update_person_a_ui()
        ui.notify("Selection reset.", type="info")

    # --- UI Definition ---
    with theme.frame("Progression"):
        ui.label("Lookup Career Progression Info").classes("text-2xl")
        ui.label("Start typing to search for a person.")
        ui.input(
            "Person", on_change=lambda e: search_person_a(e.value)
        ).props("outlined dense")
        refs["selected_person_a_label"] = ui.label(
            "Selected: None"
        ).classes("text-gray-500 mt-2")
        ui.separator()
        refs["search_results_a"] = ui.column().classes("w-full items-start")

        with ui.column().bind_visibility_from(wizard_state, "person_a"):
            (
                refs["timeline_container"],
                refs["profile_container"],
            ) = profile_display.create_person_details_ui()
            ui.button("Reset", on_click=reset_search_a_handler).props(
                "flat"
            )

    # Initial call to render the empty state of the components
    update_person_a_ui()
