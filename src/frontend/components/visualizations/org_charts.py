from typing import List, Dict, Any, Optional
import pyecharts.options as opts
from pyecharts.charts import Tree

from loguru import logger


def _build_tree_structure(
    descendants: List[Dict[str, Any]], root_org: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Converts a flat list of organization dictionaries into a nested
    hierarchical structure suitable for pyecharts Tree.

    Args:
        descendants: A list of descendant organization dictionaries.
        root_org: The dictionary for the parent/root organization.

    Returns:
        A list containing a single root dictionary with nested children.
    """
    # The pyecharts Tree expects a list containing one root dictionary.
    # We use the 'name' key for the display label.
    root_node = {
        "name": root_org["name"].split(":")[-1],
        "id": root_org["id"],
        "children": [],
    }

    # Create a map for O(1) lookup of any node by its ID.
    # We also initialize each node in the format pyecharts expects.
    node_map = {
        org["id"]: {
            "name": org["name"].split(":")[-1],
            "id": org["id"],
            "children": [],
        }
        for org in descendants
    }
    # Add the root to the map so children can find it.
    node_map[root_node["id"]] = root_node

    # Iterate through the original descendants list to link children to parents.
    for org_data in descendants:
        parent_id = org_data.get("parent_org_id")
        if parent_id and parent_id in node_map:
            parent_node = node_map[parent_id]
            child_node = node_map[org_data["id"]]
            parent_node["children"].append(child_node)

    # The final structure is a list containing only the root node.
    return [root_node]


def create_radial_tree_chart(
    root_org: Dict[str, Any],
    descendants: List[Dict[str, Any]],
    chart_title: Optional[str] = None,
    overlay_text: Optional[str] = None,  # <-- The key parameter
    unique_id: Optional[str] = None,
) -> Tree:
    tree_data = _build_tree_structure(descendants, root_org)
    # chart_title = (
    #     f"Organization Chart for {root_org.get('name', 'Root')}"
    #     if not chart_title
    #     else chart_title
    # )

    graphic_elements = []
    if overlay_text:
        graphic_elements.append(
            opts.GraphicText(
                graphic_item=opts.GraphicItem(
                    left="10px", top="50px", z=100
                ),
                graphic_textstyle_opts=opts.GraphicTextStyleOpts(
                    text=overlay_text,
                    font="14px 'Courier New', monospace",
                    graphic_basicstyle_opts=opts.GraphicBasicStyleOpts(
                        # fill="rgba(245, 245, 245, 0.9)",  # Semi-transparent
                        line_width=1,
                    ),
                ),
            )
        )
    # logger.debug(f"Creating radial tree chart with title: {chart_title}")
    chart = (
        Tree(
            init_opts=opts.InitOpts(
                animation_opts=opts.AnimationOpts(
                    animation=False,
                    animation_duration=500,
                    animation_easing="quinticInOut",
                ),
                width="100%",
                height="100%",
                bg_color="#f5f5f5",  # Light background for better contrast
            )
        )
        .add(
            series_name=root_org.get("name", "Organization")
            if not unique_id
            else unique_id,
            data=tree_data,
            pos_top="5%",
            pos_bottom="5%",
            pos_left="7%",
            pos_right="7%",
            layout="radial",
            symbol="circle",
            symbol_size=6,
            is_roam=True,
            zoom=1,
            initial_tree_depth=-1,  # Expand all nodes by default
            label_opts=opts.LabelOpts(
                is_show=False,
                position="right",
                vertical_align="middle",
                font_size=12,
                color="#333",
            ),
            leaves_opts=opts.LabelOpts(
                is_show=False,
                position="right",
                vertical_align="middle",
                font_size=12,
                color="#333",
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="item",
                trigger_on="mousemove",
                formatter="{b}",
            ),
            emphasis_opts=opts.EmphasisOpts(
                focus="ancestor",
            ),
            itemstyle_opts=opts.ItemStyleOpts(
                # Dark grey for nodes
                color="#999",
                border_color="#555",  # Darker blue for borders
                border_width=1,
                opacity=0.8,  # Slightly transparent
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title=chart_title,
                subtitle=overlay_text,
                subtitle_textstyle_opts=opts.TextStyleOpts(
                    font_size=12, font_style="italic"
                ),
            ),
            graphic_opts=graphic_elements,
            tooltip_opts=opts.TooltipOpts(
                trigger="item", trigger_on="mousemove"
            ),
            toolbox_opts=opts.ToolboxOpts(),
            legend_opts=opts.LegendOpts(
                is_show=False,  # Hide legend for radial tree
            ),
        )
    )
    return chart


def generate_tree_data(
    root_org: Dict[str, Any],
    descendants: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generates the hierarchical data structure for the radial tree chart.

    Args:
        root_org: The dictionary for the root organization.
        descendants: The list of descendant organizations.

    Returns:
        A list containing a single root node with nested children.
    """
    return _build_tree_structure(descendants, root_org)
