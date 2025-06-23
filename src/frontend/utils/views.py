import importlib
from pathlib import Path
from typing import Callable

from nicegui import ui
from src.auth import page as auth_page
import src.auth as auth
from loguru import logger

# Import our new registry
from src.frontend.registry import PAGES


def exclude_from_scan(func: Callable) -> Callable:
    """Decorator to exclude a page from automatic view registration."""
    setattr(func, "_exclude_from_scan", True)
    return func


@auth.login_page
def login():
    auth.login_form().on("success", lambda: ui.navigate.to("/"))


def register_views(
    directory: str | Path = "src/frontend/views",
    app_prefix: str = "src.frontend.views",
    content_func_name: str = "content",
) -> None:
    """
    Scans a directory, populates the central page registry, and registers
    the views as NiceGUI pages.
    """
    views_path = Path(directory)
    logger.info(f"🔍 Scanning for views in: {views_path.resolve()}")

    for file_path in sorted(
        views_path.rglob("*.py")
    ):  # sorted() for a consistent menu order
        if file_path.name.startswith(("_", ".")):
            continue

        module_rel_path = file_path.relative_to(views_path).with_suffix("")
        module_path_parts = module_rel_path.parts
        module_name = f"{app_prefix}.{'.'.join(module_path_parts)}"

        try:
            module = importlib.import_module(module_name)
            content_function = getattr(module, content_func_name, None)

            if not content_function or not callable(content_function):
                continue

            if getattr(content_function, "_exclude_from_scan", False):
                logger.info(
                    f"🚫 Skipping {module_name}: Marked with @exclude_from_scan."
                )
                continue

            url_path = f"/{file_path.stem}"

            # NEW: Create a user-friendly name from the filename
            # 'connectivity' -> 'Connectivity'
            # 'employment_graph' -> 'Employment Graph'
            nice_name = file_path.stem.replace("_", " ").title()

            # NEW: Add the page info to our central registry
            PAGES.append({"name": nice_name, "path": url_path})

            # Register the page with NiceGUI
            auth_page(url_path)(content_function)
            logger.info(f"✅ Registered '{nice_name}' at path '{url_path}'")

        except ImportError as e:
            logger.error(f"❌ Error importing {module_name}: {e}")
