"""Kanban flow mirror -- project task tracking board.

Python mirror of ``flows/kanban-flow.js``: a Kanban board node
(``KanbanNode``) and a card node (``KanbanCardNode``) for Node-RED.
"""

import time

DEFAULT_COLUMNS = [
    {"id": "todo", "label": "To Do", "type": "todo", "cards": []},
    {"id": "in-progress", "label": "In Progress", "type": "in-progress", "cards": []},
    {"id": "review", "label": "Review", "type": "review", "cards": []},
    {"id": "done", "label": "Done", "type": "done", "cards": []},
]


class _CallRecorder:
    """Minimal call recorder exposing ``called``/``call_args`` like a Mock.

    Node-RED nodes expose ``status()`` and ``send()``; the mirror records
    calls so unit tests can assert on them without unittest.mock.
    """

    def __init__(self):
        self._calls = []

    def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        return None

    @property
    def called(self):
        """True once at least one call has been recorded."""
        return bool(self._calls)

    @property
    def call_args(self):
        """Arguments of the most recent call as an ``(args, kwargs)`` tuple."""
        return self._calls[-1] if self._calls else None

    def reset(self):
        """Forget all recorded calls."""
        self._calls = []


class KanbanNode:
    """Kanban board node (mirror of the ``kanban-board`` Node-RED node)."""

    def __init__(self, node_type, msg, config, node=None):
        self.type = node_type
        self.config = dict(config or {})
        # Deep-copy the default columns so each node owns its card lists.
        self.columns = [
            {**column, "cards": list(column["cards"])} for column in DEFAULT_COLUMNS
        ]
        self.cards = []
        self.autoSave = bool(self.config.get("autoSave", False))
        self.saveInterval = self.config.get("saveInterval", 10000)
        self.status = _CallRecorder()
        self.send = _CallRecorder()
        self._handlers = {}

    # -- event handling ------------------------------------------------------
    def on(self, event, handler):
        """Register a callable ``handler`` for ``event``.

        When ``handler`` is a dict it is treated as an event payload and
        dispatched immediately (mirroring the JS ``subscribe`` events).
        """
        if callable(handler):
            self._handlers.setdefault(event, []).append(handler)
        elif isinstance(handler, dict):
            self._dispatch(event, handler)

    def _dispatch(self, event, data):
        if event == "subscribe":
            event_type = data.get("type")
            if event_type == "column-move":
                self.moveCard(data.get("cardId"), data.get("columnId"))
            elif event_type == "card-update":
                self.updateCard(data.get("cardId"), data.get("data") or {})
        for handler in self._handlers.get(event, []):
            handler(data)

    # -- column management ---------------------------------------------------
    def addColumn(self, config):
        """Create a board column, auto-generating an id when omitted."""
        config = dict(config or {})
        column = {
            "id": config.get("id") or f"card-{int(time.time() * 1000)}",
            "label": config.get("label"),
            "type": config.get("type", "default"),
            "cards": [],
        }
        self.columns.append(column)
        self.send({"payload": column})
        return column

    def updateColumn(self, column_id, config):
        """Update an existing column's label/type; returns the column or None."""
        config = config or {}
        for column in self.columns:
            if column["id"] == column_id:
                if "label" in config:
                    column["label"] = config["label"]
                if "type" in config:
                    column["type"] = config["type"]
                self.send({"payload": column})
                return column
        return None

    def deleteColumn(self, column_id):
        """Remove a column from the board."""
        self.columns = [c for c in self.columns if c["id"] != column_id]
        self.send({"payload": {"message": "Column deleted"}})
        return None

    # -- card management -----------------------------------------------------
    def addCard(self, column_id, data):
        """Add a card to a column; returns the new card or None."""
        data = dict(data or {})
        column = self._column(column_id)
        if column is None:
            return None
        card = {
            "id": f"card-{time.time_ns()}",
            "title": data.get("title"),
            "description": data.get("description", ""),
            "priority": data.get("priority", "medium"),
            "tags": list(data.get("tags") or []),
            "dueDate": data.get("dueDate"),
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "columnId": column_id,
        }
        column["cards"].append(card)
        self.cards.append(card)
        self.send({"payload": card})
        return card

    def updateCard(self, card_id, data):
        """Update an existing card; returns the card or None."""
        card = self.getCard(card_id)
        if card is None:
            return None
        card.update(dict(data or {}))
        self.send({"payload": card, "topic": f"kanban/card/{card_id}/update"})
        return card

    def deleteCard(self, card_id):
        """Remove a card from the board; returns the removed card or None."""
        for index, card in enumerate(self.cards):
            if card["id"] == card_id:
                del self.cards[index]
                column = self._column(card["columnId"])
                if column is not None:
                    column["cards"] = [c for c in column["cards"] if c["id"] != card_id]
                self.send({"payload": card, "topic": f"kanban/card/{card_id}/deleted"})
                return card
        return None

    def moveCard(self, card_id, column_id):
        """Move a card between columns; returns the card or None."""
        card = self.getCard(card_id)
        if card is None:
            return None
        old_column = self._column(card["columnId"])
        new_column = self._column(column_id)
        if old_column is None or new_column is None:
            return None
        card["columnId"] = column_id
        old_column["cards"] = [c for c in old_column["cards"] if c["id"] != card_id]
        new_column["cards"].append(card)
        self.send({"payload": card, "topic": f"kanban/card/{card_id}/moved"})
        return card

    def getCards(self, column_id):
        """Return the cards of a column (copy; empty list if unknown)."""
        column = self._column(column_id)
        return list(column["cards"]) if column else []

    def getCard(self, card_id):
        """Return a card by id or None."""
        for card in self.cards:
            if card["id"] == card_id:
                return card
        return None

    def saveBoard(self):
        """Persist the board (simulated) and flag the node as saved."""
        self.status({"fill": "green", "shape": "ring", "text": "saved"})
        self.send({"payload": {"message": "Board saved"}})
        return None

    def getBoardStats(self):
        """Return board statistics (totals, columns, per-priority counts)."""
        return {
            "totalCards": len(self.cards),
            "columns": [
                {"id": c["id"], "label": c["label"], "cardCount": len(c["cards"])}
                for c in self.columns
            ],
            "byPriority": {
                "high": sum(1 for c in self.cards if c.get("priority") == "high"),
                "medium": sum(1 for c in self.cards if c.get("priority") == "medium"),
                "low": sum(1 for c in self.cards if c.get("priority") == "low"),
            },
        }

    def _column(self, column_id):
        for column in self.columns:
            if column["id"] == column_id:
                return column
        return None


class KanbanCardNode:
    """Kanban card node (mirror of the ``kanban-card`` Node-RED node)."""

    def __init__(self, node_type, msg, config, node=None):
        self.type = node_type
        self.config = dict(config or {})

    def getCardData(self):
        """Return the card's display data from its configuration."""
        return {
            "title": self.config.get("title"),
            "description": self.config.get("description"),
            "priority": self.config.get("priority"),
            "tags": list(self.config.get("tags") or []),
        }
