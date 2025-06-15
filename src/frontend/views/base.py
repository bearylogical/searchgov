# template for a NiceGUI page

import src.frontend.theme as theme
from src.frontend.utils.views import exclude_from_scan


@exclude_from_scan
def content():
    with theme.frame("Connectivity Graph"):
        pass
