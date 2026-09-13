/**
 * Kanban Flow
 * Project task tracking board
 */
module.exports = function (RED) {
    "use strict";

    class KanbanNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.columns = [];
            this.cards = [];
            this.autoSave = false;
        }

        init() {
            // Initialize Kanban board structure
            this.columns = [
                { id: 'todo', label: 'To Do', type: 'todo' },
                { id: 'in-progress', label: 'In Progress', type: 'in-progress' },
                { id: 'review', label: 'Review', type: 'review' },
                { id: 'done', label: 'Done', type: 'done' }
            ];

            this.cards = [];

            // Subscribe to column changes
            this.on('subscribe', (event) => {
                if (event.type === 'column-move') {
                    this.moveCard(event.cardId, event.columnId);
                } else if (event.type === 'card-update') {
                    this.updateCard(event.cardId, event.data);
                }
            });

            // Set up auto-save
            if (this.autoSave) {
                this.setInterval(this.saveBoard, this.config.saveInterval || 10000);
            }
        }

        addColumn(config) {
            const newColumn = {
                id: config.id || `column-${this.cards.length}`,
                label: config.label,
                type: config.type || 'default',
                cards: []
            };
            this.columns.push(newColumn);
            this.send({ payload: newColumn });
            return newColumn;
        }

        updateColumn(id, config) {
            const column = this.columns.find(c => c.id === id);
            if (column) {
                column.label = config.label;
                column.type = config.type;
                this.send({ payload: column });
            }
        }

        deleteColumn(id) {
            this.columns = this.columns.filter(c => c.id !== id);
            this.send({ payload: { message: 'Column deleted' } });
        }

        addCard(columnId, data) {
            const column = this.columns.find(c => c.id === columnId);
            if (!column) return;

            const newCard = {
                id: `card-${Date.now()}`,
                title: data.title,
                description: data.description || '',
                priority: data.priority || 'medium',
                tags: data.tags || [],
                dueDate: data.dueDate,
                createdAt: new Date().toISOString(),
                columnId
            };

            column.cards.push(newCard);
            this.cards.push(newCard);
            this.send({ payload: newCard });
            return newCard;
        }

        updateCard(cardId, data) {
            const card = this.cards.find(c => c.id === cardId);
            if (!card) return;

            Object.assign(card, data);
            this.send({ payload: card, topic: `kanban/card/${cardId}/update` });
        }

        deleteCard(cardId) {
            const index = this.cards.findIndex(c => c.id === cardId);
            if (index !== -1) {
                const card = this.cards.splice(index, 1)[0];
                const column = this.columns.find(c => c.id === card.columnId);
                if (column) {
                    column.cards = column.cards.filter(c => c.id !== cardId);
                }
                this.send({ payload: card, topic: `kanban/card/${cardId}/deleted` });
                return card;
            }
        }

        moveCard(cardId, columnId) {
            const card = this.cards.find(c => c.id === cardId);
            if (!card) return;

            const oldColumn = this.columns.find(c => c.id === card.columnId);
            const newColumn = this.columns.find(c => c.id === columnId);

            if (oldColumn && newColumn) {
                card.columnId = columnId;
                oldColumn.cards = oldColumn.cards.filter(c => c.id !== cardId);
                newColumn.cards.push(card);
                this.send({ payload: card, topic: `kanban/card/${cardId}/moved` });
            }
        }

        getCards(columnId) {
            const column = this.columns.find(c => c.id === columnId);
            return column ? column.cards : [];
        }

        getCard(cardId) {
            return this.cards.find(c => c.id === cardId);
        }

        saveBoard() {
            // Save to local storage or external database
            this.status({
                fill: 'green',
                shape: 'ring',
                text: 'saved'
            });
            this.send({ payload: { message: 'Board saved' } });
        }

        getBoardStats() {
            const stats = {
                totalCards: this.cards.length,
                columns: this.columns.map(c => ({
                    id: c.id,
                    label: c.label,
                    cardCount: c.cards.length
                })),
                byPriority: {
                    high: this.cards.filter(c => c.priority === 'high').length,
                    medium: this.cards.filter(c => c.priority === 'medium').length,
                    low: this.cards.filter(c => c.priority === 'low').length
                }
            };
            return stats;
        }
    }

    RED.nodes.registerType("kanban-board", KanbanNode);

    class KanbanCardNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
        }

        init() {
            // Card-specific initialization
        }

        getCardData() {
            return {
                title: this.config.title,
                description: this.config.description,
                priority: this.config.priority,
                tags: this.config.tags
            };
        }
    }

    RED.nodes.registerType("kanban-card", KanbanCardNode);

    return KanbanNode;
};
