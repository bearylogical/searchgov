import src.frontend.theme as theme
import src.state as app_state
from src.frontend.components.visualizations.org_charts import (
    create_radial_tree_chart,
    generate_tree_data,
)
from nicegui import ui, html
from loguru import logger
import pyecharts.charts as echarts

import json

# Let's assume these are available for a standalone example
# from unittest.mock import Mock
# app_state = Mock()
# theme = Mock()
# create_radial_tree_chart = Mock()


async def content():
    """Content for the Organizational Evolution page."""

    with theme.frame("Organizational Evolution"):
        ui.label("Observe the evolution of a Ministry").classes(
            "text-2xl font-bold"
        )

        # --- State Management ---
        # We'll keep all our component's state in one place.
        # It's like the ship's computer core, holding all the critical data.
        content_state = {
            "ministry_id": None,
            "org_timeline_dates": [],
            "root_org": None,
            "start_date": None,
            "date_queue": [],
            "tree_object": None,
            "current_date_index": 0,
            "is_running": False,
            "group_by": "Year",  # Default grouping
        }

        # --- UI Element References ---
        # Storing references to UI elements we need to update later.
        refs = {}

        # --- Animation Timer ---
        # This timer will drive our animation frame by frame.
        # It's initialized but not active.
        animation_timer = ui.timer(
            interval=2, callback=lambda: update_frame(), active=False
        )

        # --- UI Layout ---
        with ui.row().classes("items-center"):
            # Ministry Selector
            base_ministries = await (
                app_state.graph_facade.get_base_organizations()
            )
            base_ministries_selection = {
                org[
                    "id"
                ]: f'{org["name"]} ({org["metadata"]["parts"][0].upper()})'
                for org in base_ministries
            }
            ministry_select = ui.select(
                options=base_ministries_selection,
                with_input=True,
                on_change=lambda e: fetch_timeline_dates(e.value),
                label="Select a Ministry",
            ).classes("w-72")
            # Group by dates by year or quarter
            # date_options = ui.select(
            #     options=["Year"],
            #     label="Group Dates By",
            #     on_change=lambda e: date_grouper_handler(e.value),
            #     value="Year",
            # ).classes("w-48")

            # Date Selector
            refs["select_date"] = ui.select(
                options=[],
                label="Select Start Date",
                on_change=lambda e: select_start_date(e.value),
            ).classes("w-48")

            # Control Buttons
            refs["start_button"] = ui.button(
                "Start", on_click=lambda: play_animation()
            )
            refs["pause_button"] = ui.button(
                "Pause", on_click=lambda: pause_animation()
            )
            refs["reset_button"] = ui.button(
                "Reset", on_click=lambda: reset_animation()
            )

        # This container will hold the chart and grow to fill available space.
        graph_container = ui.element("div").classes(
            "flex overflow-hidden w-full flex-grow"
        )
        refs["graph_container"] = graph_container

        # --- UI Bindings ---
        # Make the UI responsive to the state.
        # Like linking the helm controls to the ship's navigation.
        refs["select_date"].bind_enabled_from(
            content_state, "ministry_id", backward=lambda x: x is not None
        )
        refs["start_button"].bind_enabled_from(
            content_state, "ministry_id", backward=lambda x: x is not None
        )
        refs["pause_button"].bind_visibility_from(
            content_state, "is_running"
        )
        refs["reset_button"].bind_enabled_from(
            content_state, "ministry_id", backward=lambda x: x is not None
        )

        # --- Core Logic Functions ---

        def update_frame():
            """The timer calls this function to render a single animation frame."""
            if content_state["current_date_index"] < len(
                content_state["date_queue"]
            ):
                # Get the current date for this frame
                current_date = content_state["date_queue"][
                    content_state["current_date_index"]
                ]
                logger.debug(f"Rendering tree for date: {current_date}")

                # Render the chart
                render_org_tree(current_date)

                # Advance to the next frame
                content_state["current_date_index"] += 1
            else:
                # Animation finished, so we pause.
                logger.debug("Animation sequence finished.")
                pause_animation()

        def play_animation():
            """Starts or resumes the animation."""
            if not content_state["ministry_id"]:
                ui.notify("Please select a ministry first.", type="warning")
                return

            # If we are not already running, set up the date queue
            if not content_state["is_running"]:
                full_timeline = content_state["org_timeline_dates"]
                start_date = content_state["start_date"]

                if start_date:
                    # Filter the timeline to start from the selected date
                    content_state["date_queue"] = [
                        date for date in full_timeline if date >= start_date
                    ]
                else:
                    content_state["date_queue"] = full_timeline

                # If we are resuming, we don't reset the index.
                # If it's a fresh start, the index is already 0 from reset.
                if not content_state["date_queue"]:
                    ui.notify("No timeline data to play.", type="info")
                    return

            logger.debug("Starting animation...")
            content_state["is_running"] = True
            animation_timer.activate()
            # Update UI for better user feedback
            refs["start_button"].visible = False
            refs["pause_button"].visible = True
            refs["select_date"].disable()
            ministry_select.disable()

        def pause_animation():
            """Pauses the animation."""
            logger.debug("Pausing animation.")
            content_state["is_running"] = False
            animation_timer.deactivate()
            # Update UI
            refs["start_button"].visible = True
            refs["start_button"].text = "Resume"
            refs["pause_button"].visible = False

        def reset_animation():
            """Stops and resets the animation and state."""
            logger.debug("Resetting animation.")
            pause_animation()  # Stop the timer first

            # Reset state variables
            content_state["start_date"] = None
            content_state["date_queue"] = []
            content_state["current_date_index"] = 0

            # Reset UI elements
            refs["graph_container"].clear()
            refs["select_date"].set_value(None)
            refs["select_date"].enable()
            ministry_select.enable()
            refs["start_button"].text = "Start"
            ui.notify("Animation reset.")

        async def render_org_tree(selected_date: str):
            """Renders the organization tree for a specific date."""
            res = await app_state.graph_facade.get_active_descendants(
                content_state["ministry_id"], selected_date
            )

            # get org info for the root org

            with refs["graph_container"]:
                # Clear the previous chart

                refs["graph_container"].clear()

                # create a two column layout
                with ui.grid(columns=6).classes("w-full pt-8"):
                    with ui.column().classes(
                        "col-span-2 border border-gray-300"
                    ).style("border-radius: 0.5rem; padding: 1rem;"):
                        # Left side: Org Info page
                        ui.label(
                            f'{content_state["root_org"]["name"]} ({content_state["root_org"]["metadata"]["parts"][0].upper()})'
                        ).classes("text-2xl font-bold col-span-2 ").style(
                            "padding-bottom: 0rem;"
                        )
                        with html.section().classes(
                            "text-gray-500 text-sm col-span-2"
                        ):
                            ui.label(
                                f"Ministry ID: {content_state['ministry_id']}"
                            )
                            ui.label(f"Selected Date: {selected_date}")
                            ui.label(f"Total Active Entities: {len(res)}")
                    with ui.column().classes(
                        "col-span-4 border border-gray-300"
                    ).style(
                        "border-radius: 0.5rem; padding: 1rem;bg-color:#f5f5f5"
                    ):
                        # refs["graph_container"].clear()
                        if not res:
                            ui.label(
                                f"No organizational data found for {selected_date}"
                            ).classes("m-auto text-xl text-gray-500")
                            return

                        tree_obj = create_radial_tree_chart(
                            content_state["root_org"],
                            res,
                            chart_title=None,
                        )

                        # timeline.add(tree_obj, selected_date)
                        # ui.echart(
                        #     json.loads(timeline.dump_options_with_quotes())
                        # ).classes("grow").style("width: 100%; height: 42rem;")

                        ui.echart.from_pyecharts(tree_obj).classes(
                            "grow"
                        ).style(" height: 48rem;")

        async def select_start_date(selected_date: str):
            """Handles the start date selection."""
            content_state["start_date"] = selected_date
            # When a new start date is picked, reset the animation progress
            content_state["current_date_index"] = 0
            refs["start_button"].text = "Start"
            logger.debug(f"Start date set to: {selected_date}")
            await render_org_tree(selected_date)

        async def fetch_timeline_dates(ministry_id: int):
            """Fetches all data needed when a new ministry is selected."""
            # If an animation was running, stop and reset everything.
            if content_state["is_running"]:
                reset_animation()

            logger.debug(
                f"Fetching evolution for Ministry ID: {ministry_id}"
            )
            content_state["ministry_id"] = ministry_id
            timeline_dates = (
                await app_state.graph_facade.get_org_timeline_dates(
                    ministry_id
                )
            )
            # Store the timeline dates and root org in the content state
            # group the dates by year or quarter
            # choose always the last date of the year or quarter in iso8601 format and the result should be in iso8601 format
            if not timeline_dates:
                ui.notify(
                    "No timeline data available for this ministry.",
                    type="warning",
                )
                return
            if content_state["group_by"] == "Year":
                # Group by year, taking the last date of each year, check if the timeline dates are in the previous date list
                timeline_dates = sorted(
                    set(date[:4] + "-01-01" for date in timeline_dates)
                )

                # check with
            elif content_state["group_by"] == "Quarter":
                # Group by quarter, taking the last date of each quarter
                timeline_dates = sorted(
                    set(
                        date[:4]
                        + "-"
                        + str((int(date[5:7]) - 1) // 3 * 3 + 3).zfill(2)
                        + "-01"
                        for date in timeline_dates
                    )
                )
                logger.debug(
                    f"Grouped timeline dates by quarter: {timeline_dates}"
                )
            else:
                # Default to the original dates if no grouping is selected
                timeline_dates = sorted(set(timeline_dates))
            # Update the content state with the new timeline dates and root org

            content_state["org_timeline_dates"] = timeline_dates
            content_state[
                "root_org"
            ] = await app_state.graph_facade.orgs_repo.find_by_org_id(
                ministry_id
            )

            # Update the date selector and reset other states
            refs["select_date"].set_options(timeline_dates)
            refs["select_date"].set_value(timeline_dates[0])
            reset_animation()  # Resets state and UI for the new selection

            logger.debug(f"Data loaded for Ministry ID {ministry_id}.")
            # Optionally, render the first available chart
            if timeline_dates:
                await render_org_tree(timeline_dates[0])

    def date_grouper_handler(value: str):
        """Handles the date grouping selection."""

        # Here you would implement the logic to group dates accordingly.
        # For now, we just log it.
        content_state["group_by"] = value
        refs["select_date"].set_value(value)  # Reset selection
        if content_state["ministry_id"]:
            # Re-fetch the timeline dates with the new grouping
            logger.debug(f"Grouping dates by: {value}")
            fetch_timeline_dates(content_state["ministry_id"])
