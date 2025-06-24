# src/frontend/pages/connectivity.py

import asyncio
from datetime import date
from typing import Any, Dict, Optional

from nicegui import ui, run
from loguru import logger

import src.frontend.theme as theme
import src.state as app_state

# Import the shared module and the Profile class
from src.frontend.components import profile_display
from src.frontend.components.profile_display import Profile

running_query_a: Optional[asyncio.Task] = None
running_query_b: Optional[asyncio.Task] = None


@ui.page("/connectivity")
async def content() -> None:
    refs = {}
    wizard_state = {
        "person_a": None,
        "person_b": None,
        "connections_list": [],
        "target_date": date.today().strftime("%Y-%m-%d"),
        "person_a_employment": [],
        "person_a_consolidated_profile": None,
        "person_b_employment": [],
        "person_b_consolidated_profile": None,
    }

    def update_ui(person_key: str):
        """Generic UI updater for either person A or B."""
        timeline_container = refs.get(
            f"person_{person_key}_timeline_content"
        )
        profile_container = refs.get(f"person_{person_key}_profile_content")
        final_profile_container = refs.get(
            f"person_{person_key}1_profile_content"
        )

        if not timeline_container or not profile_container:
            return

        def handle_remove(record: Dict):
            """Nested callback to handle removal for the correct person."""
            try:
                wizard_state[f"person_{person_key}_employment"].remove(
                    record
                )
                ui.notify("Employment record removed.", type="info")
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not remove employment: {e}")
            finally:
                update_ui(person_key)

        profile_display.build_timeline(
            timeline_container,
            wizard_state[f"person_{person_key}_employment"],
            on_remove=handle_remove,
        )
        profile = profile_display.build_profile_card(
            profile_container,
            wizard_state[f"person_{person_key}"],
            wizard_state[f"person_{person_key}_employment"],
        )
        wizard_state[f"person_{person_key}_consolidated_profile"] = profile

        if final_profile_container and wizard_state[f"person_{person_key}"]:
            profile_display.build_profile_card(
                final_profile_container,
                wizard_state[f"person_{person_key}"],
                wizard_state[f"person_{person_key}_employment"],
            )

    async def select_person(person: Dict[str, Any], person_key: str):
        """Handles selecting a person and fetching their full profile."""
        wizard_state[f"person_{person_key}"] = person
        refs[f"selected_person_{person_key}_label"].set_text(
            f"Selected: {person['name']}"
        )
        refs[f"search_results_{person_key}"].clear()
        ui.notify(
            f"Selected {person['name']} as Person {person_key.upper()}.",
            type="positive",
        )

        employment_profile = await run.io_bound(
            app_state.graph_facade.get_career_progression_by_name,
            person["name"],
        )
        if employment_profile:
            employment_profile.sort(
                key=lambda x: x.get("start_date", "9999-12-31")
            )
            wizard_state[f"person_{person_key}_employment"] = (
                employment_profile
            )
        else:
            wizard_state[f"person_{person_key}_employment"] = []

        update_ui(person_key)

        if person_key == "a":
            refs["person_b_input"].enable()

    async def search_person_a(search_term: str) -> None:
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
                            "click", lambda p=person: select_person(p, "a")
                        ):
                            ui.label(person["name"])
                            # CORRECTED: Call the shared get_parent_entity
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
            ui.notify(
                f"An error occurred during search: {e}", type="negative"
            )

    async def search_person_b(search_term: str) -> None:
        global running_query_b
        if not wizard_state.get("person_a_consolidated_profile"):
            return
        if not search_term:
            refs["search_results_b"].clear()
            return
        if running_query_b:
            running_query_b.cancel()

        coro = run.io_bound(
            app_state.graph_facade.find_person_by_name,
            search_term,
            is_fuzzy=True,
        )
        task = asyncio.create_task(coro)
        running_query_b = task
        try:
            people = await task
            if running_query_b is not task:
                return
            refs["search_results_b"].clear()
            with refs["search_results_b"]:
                if not people:
                    ui.label("No results found.")
                    return
                for person in people:
                    with ui.card().classes(
                        "cursor-pointer hover:bg-gray-200 w-full"
                    ):
                        with ui.row().classes("items-center gap-2").on(
                            "click", lambda p=person: select_person(p, "b")
                        ):
                            ui.label(person["name"])
                            # CORRECTED: Call the shared get_parent_entity
                            parent_entity = (
                                profile_display.get_parent_entity(
                                    person.get("linked_organizations", [])
                                )
                            )
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
            ui.notify(
                f"An error occurred during search: {e}", type="negative"
            )

    def reset_search_a_handler() -> None:
        """Resets state for Person A and B and updates the UI."""
        refs["search_results_a"].clear()
        refs["selected_person_a_label"].set_text("Selected: None")
        wizard_state["person_a"] = None
        wizard_state["person_a_employment"] = []
        wizard_state["person_a_consolidated_profile"] = None
        wizard_state["person_b"] = None
        wizard_state["person_b_employment"] = []
        wizard_state["person_b_consolidated_profile"] = None
        update_ui("a")
        update_ui("b")
        refs["person_b_input"].disable()
        ui.notify("Person A selection reset.", type="info")

    async def execute_find_path() -> None:
        person_a: Profile = wizard_state.get(
            "person_a_consolidated_profile"
        )
        person_b: Profile = wizard_state.get(
            "person_b_consolidated_profile"
        )
        if not person_a or not person_b:
            ui.notify("Please select both people first.", type="warning")
            return

        refs["final_results_area"].clear()
        with refs["final_results_area"]:
            with ui.row().classes("items-center"):
                ui.spinner(size="lg")
                ui.label("Finding the shortest path...").classes("ml-4")

        try:
            path = await run.io_bound(
                app_state.graph_facade.find_shortest_path,
                person_a.ids,
                person_b.ids,
            )
            refs["final_results_area"].clear()
            with refs["final_results_area"]:
                if not path:
                    ui.label(
                        f"No path found between {person_a.anchor_name} and {person_b.anchor_name}."
                    )
                else:
                    ui.label("Connection Path Found!").classes(
                        "text-xl mb-2"
                    )
                    ui.label(
                        f"It takes {len(path) //2 - 1} people to connect {person_a.anchor_name} and {person_b.anchor_name}."
                    ).classes("text-sm text-gray-500 mb-4")
                    # logger.info(path)
                    with ui.row().classes("items-center gap-2"):
                        for i, item in enumerate(path):
                            if item["node_type"] == "person":
                                chip = ui.chip(
                                    item["name"],
                                    color="blue-600",
                                    text_color="white",
                                )
                                # get the relevant rank based on the org
                                if i < len(path) - 1:
                                    related_org = int(path[i + 1]["org_id"])
                                else:
                                    related_org = int(path[i - 1]["org_id"])
                                # filter employment records relavant to this org
                                employment_records = item[
                                    "employment_profile"
                                ]
                                relevant_employment = [
                                    emp
                                    for emp in employment_records
                                    if emp["org_id"] == related_org
                                ]
                                # get most recent employment record
                                if relevant_employment:
                                    most_recent = max(
                                        relevant_employment,
                                        key=lambda x: x["start_date"],
                                    )
                                    chip.tooltip(
                                        f"{item['name']} ({most_recent['rank']})"
                                    )
                            elif item["node_type"] == "organization":
                                chip = ui.chip(
                                    item["name"],
                                    color="green-600",
                                    text_color="white",
                                )

                            if i < len(path) - 1:
                                ui.icon("arrow_right_alt")
        except Exception as e:
            refs["final_results_area"].clear()
            with refs["final_results_area"]:
                ui.label(f"An error occurred: {e}")

    # --- UI Definition ---
    with theme.frame("Connectivity Graph"):
        ui.label("Find the Shortest Path Between Two Colleagues").classes(
            "text-2xl"
        )

        with ui.stepper().props("horizontal").classes("w-full") as stepper:
            with ui.step("Select Person A"):
                ui.label("Start typing to search for the first person.")
                ui.input(
                    "Person A", on_change=lambda e: search_person_a(e.value)
                ).props("outlined dense")
                refs["selected_person_a_label"] = ui.label(
                    "Selected: None"
                ).classes("text-gray-500 mt-2")
                ui.separator()
                refs["search_results_a"] = ui.column().classes(
                    "w-full items-start"
                )

                with ui.column().bind_visibility_from(
                    wizard_state, "person_a"
                ):
                    # CORRECTED: Call the shared UI factory
                    (
                        refs["person_a_timeline_content"],
                        refs["person_a_profile_content"],
                    ) = profile_display.create_person_details_ui()
                    with ui.stepper_navigation():
                        ui.button("Next", on_click=stepper.next)
                        ui.button(
                            "Reset", on_click=reset_search_a_handler
                        ).props("flat")

            with ui.step("Select Person B"):
                ui.label(
                    "Select a connected person. You can also type to search."
                )
                refs["person_b_input"] = ui.input(
                    "Person B", on_change=lambda e: search_person_b(e.value)
                ).props("outlined dense")
                refs["person_b_input"].disable()
                refs["selected_person_b_label"] = ui.label(
                    "Selected: None"
                ).classes("text-gray-500 mt-2")
                refs["search_results_b"] = ui.column().classes(
                    "w-full items-start"
                )

                with ui.column().bind_visibility_from(
                    wizard_state, "person_b"
                ):
                    # CORRECTED: Call the shared UI factory again
                    (
                        refs["person_b_timeline_content"],
                        refs["person_b_profile_content"],
                    ) = profile_display.create_person_details_ui()
                    with ui.stepper_navigation():
                        ui.button("Back", on_click=stepper.previous).props(
                            "flat"
                        )
                        ui.button("Next", on_click=stepper.next)

            with ui.step("Find Path"):
                ui.label(
                    "Confirm the details and find the connection."
                ).classes("text-lg")
                with ui.row().classes("w-full gap-4 mt-4 no-wrap"):
                    with ui.card().classes("grow"):
                        with ui.card_section():
                            ui.label("Person A: Final Profile").classes(
                                "text-lg font-semibold"
                            )
                        ui.separator()
                        refs["person_a1_profile_content"] = (
                            ui.column().classes("w-full")
                        )
                    with ui.card().classes("grow"):
                        with ui.card_section():
                            ui.label("Person B: Final Profile").classes(
                                "text-lg font-semibold"
                            )
                        ui.separator()
                        refs["person_b1_profile_content"] = (
                            ui.column().classes("w-full")
                        )
                refs["final_results_area"] = ui.column().classes(
                    "w-full my-4"
                )
                with ui.stepper_navigation():
                    ui.button(
                        "Find Shortest Path", on_click=execute_find_path
                    )
                    ui.button("Back", on_click=stepper.previous).props(
                        "flat"
                    )
                    ui.button(
                        "Start Over", on_click=lambda: ui.navigate.reload()
                    ).props("flat")
