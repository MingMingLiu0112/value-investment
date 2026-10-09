"""Worksheet XML post-processing for staged frontend sheets."""
from __future__ import annotations

import re
from typing import Iterable, Mapping
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_MAP = {"m": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS}

_SINGLE_QUOTE = chr(39)
_DOUBLE_QUOTE = chr(34)

# Matches =HYPERLINK("#<sheet>!<cell>","<display>") recorded as a formula.
_NAVIGATION_FORMULA = re.compile(
    "HYPERLINK\\("
    + _DOUBLE_QUOTE
    + "#"
    + _SINGLE_QUOTE
    + "([^"
    + _SINGLE_QUOTE
    + "]+)"
    + _SINGLE_QUOTE
    + "!([A-Z]{1,3}[1-9][0-9]*)"
    + _DOUBLE_QUOTE
    + ","
    + _DOUBLE_QUOTE
    + "([^"
    + _DOUBLE_QUOTE
    + "\\r\\n]*)"
    + _DOUBLE_QUOTE
    + "\\)"
)

_HYPERLINK_PRECEDING = (
    "sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols",
    "sheetData", "sheetCalcPr", "sheetProtection", "protectedRanges",
    "scenarios", "autoFilter", "sortState", "dataConsolidate",
    "customSheetViews", "mergeCells", "phoneticPr",
    "conditionalFormatting", "dataValidations",
)

_SHEET_CHILD_ORDER = (
    "sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols",
    "sheetData", "sheetCalcPr", "sheetProtection", "protectedRanges",
    "scenarios", "autoFilter", "sortState", "dataConsolidate",
    "customSheetViews", "mergeCells", "phoneticPr",
    "conditionalFormatting", "dataValidations", "hyperlinks",
    "printOptions", "pageMargins", "pageSetup", "headerFooter",
    "rowBreaks", "colBreaks", "customProperties", "cellWatches",
    "ignoredErrors", "smartTags", "drawing", "legacyDrawing",
    "legacyDrawingHF", "picture", "oleObjects", "controls",
    "webPublishItems", "tableParts", "extLst",
)


def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def add_native_navigation(
    root: ET.Element,
    existing_paths: Mapping[str, str],
) -> None:
    """Turn verified in-sheet HYPERLINK formulas into native hyperlinks."""
    links: dict[str, dict[str, str]] = {}
    for cell in root.iter(f"{{{MAIN_NS}}}c"):
        formula = cell.find(f"{{{MAIN_NS}}}f")
        if formula is None:
            continue
        match = _NAVIGATION_FORMULA.fullmatch(formula.text or "")
        if match is None:
            continue
        destination, coordinate, display = match.groups()
        if destination not in existing_paths:
            raise ValueError(
                "Native navigation target does not exist in the retained workbook"
            )
        reference = cell.get("r")
        links[reference] = {
            "ref": reference,
            "location": (
                f"{_SINGLE_QUOTE}{destination}{_SINGLE_QUOTE}!{coordinate}"
            ),
            "display": display,
        }
    hyperlinks = root.find("m:hyperlinks", NS_MAP)
    if hyperlinks is not None:
        if len({link.get("ref") for link in hyperlinks}) != len(hyperlinks):
            raise ValueError("Duplicate native navigation references")
        for link in hyperlinks:
            if dict(link.attrib) != links.get(link.get("ref")):
                raise ValueError(
                    "Native navigation differs from its verified formula"
                )
    if not links:
        return
    if hyperlinks is None:
        hyperlinks = ET.Element(f"{{{MAIN_NS}}}hyperlinks")
        index = max(
            [0]
            + [
                position + 1
                for position, element in enumerate(root)
                if _local_name(element.tag) in _HYPERLINK_PRECEDING
            ]
        )
        root.insert(index, hyperlinks)
    existing_refs = {link.get("ref") for link in hyperlinks}
    for coordinate, attributes in links.items():
        if coordinate not in existing_refs:
            ET.SubElement(hyperlinks, f"{{{MAIN_NS}}}hyperlink", attributes)


def enable_fit_to_page(root: ET.Element) -> None:
    """Force one-page-wide landscape printing without a fixed scale."""
    properties = root.find("m:sheetPr", NS_MAP)
    if properties is None:
        properties = ET.Element(f"{{{MAIN_NS}}}sheetPr")
        root.insert(0, properties)
    page_properties = properties.find("m:pageSetUpPr", NS_MAP)
    if page_properties is None:
        page_properties = ET.SubElement(
            properties, f"{{{MAIN_NS}}}pageSetUpPr"
        )
    page_properties.set("fitToPage", "1")
    setup = root.find("m:pageSetup", NS_MAP)
    if setup is None:
        setup = ET.SubElement(root, f"{{{MAIN_NS}}}pageSetup")
    setup.attrib.pop("scale", None)
    setup.attrib.update(
        orientation="landscape",
        paperSize="8",
        fitToWidth="1",
        fitToHeight="0",
    )
    order = {name: position for position, name in enumerate(_SHEET_CHILD_ORDER)}
    root[:] = sorted(
        root,
        key=lambda element: order.get(_local_name(element.tag), len(order)),
    )


def apply_frozen_panes(
    root: ET.Element,
    frozen_rows: int,
    frozen_columns: int,
) -> None:
    """Freeze the header rows and optional leading columns."""
    view = root.find("m:sheetViews/m:sheetView", NS_MAP)
    if view is None:
        return
    for pane in view.findall("m:pane", NS_MAP):
        view.remove(pane)
    ET.SubElement(
        view,
        f"{{{MAIN_NS}}}pane",
        {
            "ySplit": str(frozen_rows),
            "topLeftCell": f"{chr(65 + frozen_columns)}{frozen_rows + 1}",
            "activePane": "bottomRight" if frozen_columns else "bottomLeft",
            "state": "frozen",
        },
    )
    if frozen_columns:
        view.find("m:pane", NS_MAP).set("xSplit", str(frozen_columns))
    view.set("zoomScale", "90")


def post_process_replacement_sheet(
    root: ET.Element,
    *,
    existing_paths: Mapping[str, str],
    frozen_rows: int = 4,
    frozen_columns: int = 0,
    fit_to_page: bool = False,
    native_navigation: bool = False,
) -> None:
    """Apply the opt-in worksheet post-processing steps in order."""
    if native_navigation:
        add_native_navigation(root, existing_paths)
    if fit_to_page:
        enable_fit_to_page(root)
    apply_frozen_panes(root, frozen_rows, frozen_columns)


__all__ = [
    "MAIN_NS",
    "NS_MAP",
    "PKG_REL_NS",
    "REL_NS",
    "add_native_navigation",
    "apply_frozen_panes",
    "enable_fit_to_page",
    "post_process_replacement_sheet",
]
