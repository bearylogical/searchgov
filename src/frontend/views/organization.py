# src/frontend/pages/progression.py

import asyncio
from typing import Any, Dict, Optional
import json

from nicegui import ui
from loguru import logger

import src.frontend.theme as theme
import src.state as app_state
from src.frontend.components import profile_display

running_query_a: Optional[asyncio.Task] = None

# Define Tailwind classes for reuse
RED_CHIP = (
    "bg-red-100 text-red-800 text-sm font-medium me-2 px-2.5 py-0.5 "
    "rounded-sm dark:bg-red-900 dark:text-red-300"
)
GREEN_CHIP = (
    "bg-green-100 text-green-800 text-sm font-medium me-2 px-2.5 py-0.5 "
    "rounded-sm dark:bg-green-900 dark:text-green-300"
)


@ui.page("/org")
async def content() -> None:
    refs = {}
    wizard_state = {
        "org": None,
        "org_employment": [],
        "org_consolidated_profile": None,
    }

    def update_org_ui():
        """Update the UI using the shared components."""
        if not refs.get("timeline_container") or not refs.get(
            "profile_container"
        ):
            return

        def handle_remove(record: Dict):
            """Callback to handle removing an employment record."""
            try:
                wizard_state["org_employment"].remove(record)
                ui.notify("Employment record removed.", type="info")
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not remove employment: {e}")
            finally:
                update_org_ui()  # Re-render after state change

        profile_display.build_timeline(
            refs["timeline_container"],
            wizard_state["org_employment"],
            on_remove=handle_remove,
        )
        profile = profile_display.build_profile_card(
            refs["profile_container"],
            wizard_state["org"],
            wizard_state["org_employment"],
        )
        wizard_state["org_consolidated_profile"] = profile

    async def search_org(search_term: str):
        global running_query_a
        if not search_term:
            refs["search_results"].clear()
            return
        if running_query_a:
            running_query_a.cancel()

        task = asyncio.create_task(
            app_state.graph_facade.find_organisation_by_name(
                search_term,
                is_fuzzy=True,
            )
        )
        running_query_a = task
        try:
            orgs = await task
            if running_query_a is not task:
                return
            refs["search_results"].clear()
            with refs["search_results"]:
                if not orgs:
                    ui.label("No results found.")
                    return
                for org in orgs:
                    with ui.card().classes(
                        "cursor-pointer hover:bg-gray-200 w-full"
                    ):
                        with ui.row().classes("items-center gap-2").on(
                            "click", lambda p=org: select_org(p)
                        ):
                            ui.label(org["name"])
                            logger.debug(f"Found org: {org['name']} : {org.get('metadata', {})}")
                            metadata = json.loads(org.get("metadata", "{}"))
                            logger.debug(f"Metadata for {org['name']}: {metadata}")
                            res = {"name": "Unknown", "acronym": "UNK", "parent_acronym": "UNK", "type": "unknown"}
                            if len(metadata["parts"]) > 1:
                                res["type"] = "Sub-Organization"
                            elif len(metadata["parts"]) == 1:
                                res["type"] = "Base Ministry"
                            
                            res["parent_acronym"] = metadata["parts"][0].upper() if metadata["parts"] else "UNK"
                            res["acronym"] = metadata["parts"][-1].upper() if metadata["parts"] else "UNK"

                            if res["parent_acronym"] != "UNK":
                                ui.label(res["parent_acronym"]).tailwind(
                                    RED_CHIP
                                )
                            if res["type"] != "Base Ministry":
                                ui.label(
                                    res["acronym"]
                                ).tailwind(GREEN_CHIP)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Error during search: {e}")
            ui.notify(
                f"An error occurred during search: {e}", type="negative"
            )
            raise

    async def select_org(org: Dict[str, Any]):
        wizard_state["org"] = org
        refs["selected_org_label"].set_text(
            f"Selected: {org['name']}"
        )
        refs["search_results"].clear()
        ui.notify(f"Selected {org['name']}", type="positive")

        employment_profile = (
            await app_state.graph_facade.get_career_progression_by_name(
                org["name"]
            )
        )
        if employment_profile:
            employment_profile.sort(
                key=lambda x: x.get("start_date", "9999-12-31")
            )
            wizard_state["org_employment"] = employment_profile
        else:
            wizard_state["org_employment"] = []
        update_org_ui()

    def reset_search_a_handler():
        refs["search_results"].clear()
        refs["selected_org_label"].set_text("Selected: None")
        wizard_state["org"] = None
        wizard_state["org_employment"] = []
        update_org_ui()
        ui.notify("Selection reset.", type="info")

    # --- UI Definition ---
    with theme.frame("Organization Info"):
        ui.label("Lookup Organization Info").classes("text-2xl")
        ui.label("Start typing to search for an organization.")
        ui.input(
            "Organization", on_change=lambda e: search_org(e.value)
        ).props("outlined dense")
        refs["selected_org_label"] = ui.label(
            "Selected: None"
        ).classes("text-gray-500 mt-2")
        ui.separator()
        refs["search_results"] = ui.column().classes("w-full items-start")

        with ui.column().bind_visibility_from(wizard_state, "org"):
            # (
            #     refs["timeline_container"],
            #     refs["profile_container"],
            # ) = profile_display.create_org_details_ui()
            # ui.button("Reset", on_click=reset_search_a_handler).props(
            #     "flat"
            # )
            None

    # Initial call to render the empty state of the components
    update_org_ui()
