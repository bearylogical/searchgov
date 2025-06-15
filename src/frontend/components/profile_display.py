# src/frontend/components/profile_display.py

from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass

from nicegui import ui
from loguru import logger


@dataclass
class Profile:
    """A consolidated profile for a person."""

    anchor_name: str
    aliases: List[str]
    ids: List[int]
    org_ids: List[int]
    start_date: Optional[str]  # Can be 'N/A'
    end_date: Optional[str]  # Can be 'N/A'


def get_parent_entity(linked_orgs: List[Dict[str, Any]]) -> Dict[str, str]:
    """Get the parent organization from a list of linked organizations."""
    if not linked_orgs:
        return {"name": "Unknown", "acronym": "UNK", "type": "unknown"}
    try:
        parent_ministry = [
            e
            for e in linked_orgs
            if "ministry" in e["metadata"].get("sgdi_entity_type", "")
        ]
        parent_stat_board = [
            e
            for e in linked_orgs
            if "statutory" in e["metadata"].get("sgdi_entity_type", "")
        ]
    except KeyError as e:
        logger.error(f"KeyError in get_parent_entity: {e}")
        return {"name": "Unknown", "acronym": "UNK", "type": "unknown"}
    else:
        if parent_ministry and parent_stat_board:
            return {
                "name": parent_stat_board[0]["name"],
                "acronym": parent_stat_board[0]["metadata"]["parts"][
                    -1
                ].upper(),
                "type": "statutory board",
            }
        elif parent_ministry:
            return {
                "name": parent_ministry[0]["name"],
                "acronym": parent_ministry[0]["metadata"]["parts"][
                    0
                ].upper(),
                "type": "ministry",
            }
        else:
            return {
                "name": linked_orgs[0]["name"],
                "acronym": linked_orgs[0]["metadata"]["parts"][0].upper(),
                "type": linked_orgs[0].get("sgdi_entity_type", "unknown"),
            }


def build_timeline(
    container: ui.element,
    employment_list: List[Dict],
    on_remove: Callable[[Dict], None],
):
    """
    Builds the editable timeline UI inside a given container.

    :param container: The NiceGUI element to build the timeline in.
    :param employment_list: The list of employment records.
    :param on_remove: A callback function to execute when an item is removed.
    """
    container.clear()
    with container:
        if not employment_list:
            ui.label("No employment records to edit.").classes(
                "text-gray-500"
            )
            return

        with ui.timeline(side="right"):
            for employment in employment_list:
                entry_container = ui.timeline_entry(
                    f'Identified Name : {employment["person_actual_name"]}',
                    icon="work",
                    title=f'{employment["rank"]}, {employment["entity_name"].title()}',
                    subtitle=f"{employment['start_date']} till {employment['end_date']}",
                )
                with entry_container:
                    ui.button(
                        "Remove",
                        on_click=lambda emp=employment: on_remove(emp),
                    ).props("flat dense color=negative")


def build_profile_card(
    container: ui.element,
    person_details: Optional[Dict],
    employment_list: List[Dict],
) -> Optional[Profile]:
    """
    Builds the consolidated profile UI inside a given container.

    :param container: The NiceGUI element to build the profile in.
    :param person_details: The base details of the selected person.
    :param employment_list: The list of employment records.
    :return: The generated Profile object, or None.
    """
    container.clear()
    with container:
        if not person_details or not employment_list:
            ui.label("Profile will appear here.").classes("text-gray-500")
            return None

        # --- Profile Calculation ---
        start_dates = [
            e["start_date"] for e in employment_list if e.get("start_date")
        ]
        end_dates = [
            e["end_date"] for e in employment_list if e.get("end_date")
        ]
        profile = Profile(
            anchor_name=person_details["name"],
            aliases=list(
                set(e["person_actual_name"] for e in employment_list)
            ),
            ids=list(set(e["person_id"] for e in employment_list)),
            org_ids=list(set(e["org_id"] for e in employment_list)),
            start_date=min(start_dates) if start_dates else "N/A",
            end_date=max(end_dates) if end_dates else "N/A",
        )

        # --- UI Building ---
        with ui.card_section():
            ui.label(profile.anchor_name).classes("text-lg")
            ui.label(f"Aliases: {', '.join(profile.aliases)}").classes(
                "text-sm text-gray-500"
            )
            ui.label(
                f"Employment Period: {profile.start_date} to {profile.end_date}"
            ).classes("text-sm text-gray-500")
            agencies = {
                get_parent_entity(e.get("linked_org", []))["name"]
                for e in employment_list
                if e.get("entity_name")
            }
            ui.label(
                f"Ministries/Stat Boards: {', '.join(agencies)}"
            ).classes("text-sm text-gray-500 wrap")

        for employment in employment_list:
            with ui.item().props("dense").classes("ml-0"):
                with ui.item_section():
                    ui.item_label(
                        f'{employment["rank"]}, {employment["entity_name"].title()}'
                    ).classes("font-semibold")
                    parent_entity = get_parent_entity(
                        employment.get("linked_org", [])
                    )
                    ui.label(f'Parent Ministry : {parent_entity["name"]}')
                    ui.item_label(
                        f"{employment['start_date']} - {employment['end_date']}"
                    ).props("caption")
        return profile


def create_person_details_ui() -> Tuple[ui.column, ui.column]:
    """
    Creates the side-by-side layout for timeline and profile.

    :return: A tuple containing the timeline content container and the profile content container.
    """
    with ui.row().classes("w-full gap-4 mt-4 no-wrap"):
        # Left side: Editable Timeline
        with ui.card().classes("grow"):
            with ui.card_section():
                ui.label("Career Timeline").classes("text-lg font-semibold")
            ui.separator()
            timeline_content = ui.column().classes("w-full p-4")

        # Right side: Consolidated Profile
        with ui.card().classes("grow"):
            with ui.card_section():
                ui.label("Individual Profile").classes(
                    "text-lg font-semibold"
                )
            ui.separator()
            profile_content = ui.column().classes("w-full")

    return timeline_content, profile_content
