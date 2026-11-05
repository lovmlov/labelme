"""Persist button order separately from Qt's toolbar positions and dock state."""

import json

from PySide6 import QtWidgets

from ._tool_bar import ToolBar


def save_toolbar_actions(*, toolbars: list[ToolBar]) -> str:
    return json.dumps(
        {
            toolbar.objectName(): [
                action.property(ToolBar.ACTION_KEY) for action in toolbar.actions()
            ]
            for toolbar in toolbars
        }
    )


def restore_toolbar_actions(*, toolbars: list[ToolBar], state: object = None) -> None:
    defaults = {
        toolbar.objectName(): [
            action.property(ToolBar.ACTION_KEY) for action in toolbar.default_actions
        ]
        for toolbar in toolbars
    }
    actions = {
        action.property(ToolBar.ACTION_KEY): action
        for toolbar in toolbars
        for action in toolbar.default_actions
    }
    order = defaults
    if state is not None:
        try:
            candidate = json.loads(state) if isinstance(state, str) else None
        except (ValueError, TypeError):
            return
        if not isinstance(candidate, dict) or candidate.keys() != defaults.keys():
            return
        if any(
            not isinstance(keys, list) or any(not isinstance(key, str) for key in keys)
            for keys in candidate.values()
        ):
            return
        flattened = [key for keys in candidate.values() for key in keys]
        if len(flattened) != len(actions) or set(flattened) != actions.keys():
            return
        for name, keys in candidate.items():
            # Embedded AI/zoom widgets and separators remain on their original bar.
            # Reject damaged or incompatible state before touching any widget.
            def anchors(keys: list[str], /) -> list[str]:
                return [
                    key
                    for key in keys
                    if actions[key].isSeparator()
                    or isinstance(actions[key], QtWidgets.QWidgetAction)
                ]

            if anchors(keys) != anchors(defaults[name]):
                return
        order = candidate

    for toolbar in toolbars:
        for action in toolbar.actions():
            if not action.isSeparator() and not isinstance(
                action, QtWidgets.QWidgetAction
            ):
                toolbar.removeAction(action)
    for toolbar in toolbars:
        before = None
        for key in reversed(order[toolbar.objectName()]):
            action = actions[key]
            if not action.isSeparator() and not isinstance(
                action, QtWidgets.QWidgetAction
            ):
                if before is None:
                    toolbar.addAction(action)
                else:
                    toolbar.insertAction(before, action)
            before = action
