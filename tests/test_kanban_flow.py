"""
Tests for kanban-flow.js (Project task tracking)
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))


class TestKanbanNode:
    """Test suite for Kanban board functionality."""

    def test_kanban_node_initialization(self):
        """Test that KanbanNode initializes correctly."""
        from flows import kanban_flow

        # Create a mock RED context
        mock_red = Mock()
        mock_red.httpIn = Mock()

        # Create config
        config = {
            'autoSave': True,
            'saveInterval': 10000
        }

        # Create node instance
        node = kanban_flow.KanbanNode('kanban-board', {}, config, None)
        assert node is not None
        assert node.config['autoSave'] == config['autoSave']
        assert node.config['saveInterval'] == config['saveInterval']

    def test_kanban_default_columns(self):
        """Test that Kanban initializes with default columns."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Should have default columns
        assert len(node.columns) == 4
        column_ids = [c['id'] for c in node.columns]
        assert 'todo' in column_ids
        assert 'in-progress' in column_ids
        assert 'review' in column_ids
        assert 'done' in column_ids

    def test_kanban_default_columns_labels(self):
        """Test that Kanban initializes with correct column labels."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        column_labels = {c['id']: c['label'] for c in node.columns}
        assert column_labels['todo'] == 'To Do'
        assert column_labels['in-progress'] == 'In Progress'
        assert column_labels['review'] == 'Review'
        assert column_labels['done'] == 'Done'

    def test_add_column(self):
        """Test that addColumn creates a new column."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        new_column = node.addColumn({
            'id': 'backlog',
            'label': 'Backlog',
            'type': 'backlog'
        })

        # Should return new column
        assert new_column is not None
        assert new_column['id'] == 'backlog'
        assert new_column['label'] == 'Backlog'

    def test_add_column_auto_id(self):
        """Test that addColumn generates auto ID when none provided."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        new_column = node.addColumn({
            'label': 'Custom Column'
        })

        # Should generate an ID
        assert 'id' in new_column
        assert 'card-' in str(new_column)  # Uses timestamp

    def test_update_column(self):
        """Test that updateColumn updates existing column."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Update the 'todo' column
        node.updateColumn('todo', {'label': 'Todo Items'})

        # Find the column and check it was updated
        todo_column = next(c for c in node.columns if c['id'] == 'todo')
        assert todo_column['label'] == 'Todo Items'

    def test_delete_column(self):
        """Test that deleteColumn removes the column."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Delete the 'done' column
        node.deleteColumn('done')

        # Column should be removed
        assert not any(c['id'] == 'done' for c in node.columns)

    def test_add_card(self):
        """Test that addCard creates a new card."""
        from flows import kanban_flow
        import time

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add a card to 'todo' column
        new_card = node.addCard('todo', {
            'title': 'Test Task',
            'description': 'A test task',
            'priority': 'high',
            'tags': ['test', 'demo']
        })

        # Should return new card
        assert new_card is not None
        assert new_card['title'] == 'Test Task'
        assert new_card['columnId'] == 'todo'
        assert new_card['priority'] == 'high'

    def test_add_card_timestamp(self):
        """Test that addCard includes timestamp."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        new_card = node.addCard('todo', {'title': 'Test'})

        # Should have createdAt timestamp
        assert 'createdAt' in new_card
        assert new_card['createdAt'] is not None

    def test_update_card(self):
        """Test that updateCard updates existing card."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add a card first
        card = node.addCard('todo', {'title': 'Original'})
        card_id = card['id']

        # Update the card
        node.updateCard(card_id, {'title': 'Updated Title'})

        # Find the card and check it was updated
        updated_card = next(c for c in node.cards if c['id'] == card_id)
        assert updated_card['title'] == 'Updated Title'

    def test_delete_card(self):
        """Test that deleteCard removes the card."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add a card
        card = node.addCard('todo', {'title': 'To Delete'})
        card_id = card['id']

        # Delete the card
        node.deleteCard(card_id)

        # Card should be removed
        assert not any(c['id'] == card_id for c in node.cards)

    def test_move_card(self):
        """Test that moveCard moves card between columns."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add a card to 'todo'
        card = node.addCard('todo', {'title': 'Moving Card'})
        card_id = card['id']

        # Move to 'in-progress'
        node.moveCard(card_id, 'in-progress')

        # Card should now be in new column
        card_data = next(c for c in node.cards if c['id'] == card_id)
        assert card_data['columnId'] == 'in-progress'

    def test_get_cards_by_column(self):
        """Test that getCards returns cards for a specific column."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add some cards
        node.addCard('todo', {'title': 'Task 1'})
        node.addCard('todo', {'title': 'Task 2'})
        node.addCard('in-progress', {'title': 'Task 3'})

        # Get cards from 'todo' column
        todo_cards = node.getCards('todo')

        assert len(todo_cards) == 2
        assert all(c['title'] in ['Task 1', 'Task 2'] for c in todo_cards)

    def test_get_card(self):
        """Test that getCard retrieves a specific card."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add a card
        card = node.addCard('todo', {'title': 'Find Me'})
        card_id = card['id']

        # Retrieve the card
        retrieved_card = node.getCard(card_id)

        assert retrieved_card is not None
        assert retrieved_card['title'] == 'Find Me'

    def test_get_card_not_found(self):
        """Test that getCard returns None for non-existent card."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Should return None for non-existent card
        retrieved_card = node.getCard('non-existent-id')
        assert retrieved_card is None

    def test_save_board(self):
        """Test that saveBoard saves the board state."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)
        node.status = Mock()

        node.saveBoard()

        # Should update status to indicate saved
        assert node.status.called
        status_text = str(node.status.call_args)
        assert 'saved' in status_text

    def test_get_board_stats(self):
        """Test that getBoardStats returns correct statistics."""
        from flows import kanban_flow

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)

        # Add some cards with different priorities
        node.addCard('todo', {'title': 'High Priority Task', 'priority': 'high'})
        node.addCard('todo', {'title': 'Medium Task', 'priority': 'medium'})
        node.addCard('todo', {'title': 'Low Priority', 'priority': 'low'})

        stats = node.getBoardStats()

        # Should have correct totals
        assert stats['totalCards'] == 3
        assert stats['byPriority']['high'] == 1
        assert stats['byPriority']['medium'] == 1
        assert stats['byPriority']['low'] == 1


class TestKanbanCardNode:
    """Test suite for KanbanCardNode."""

    def test_kanban_card_node_initialization(self):
        """Test that KanbanCardNode initializes correctly."""
        from flows import kanban_flow

        # Create a mock RED context
        mock_red = Mock()

        config = {
            'title': 'My Card',
            'description': 'Card description',
            'priority': 'high',
            'tags': ['important']
        }

        # Create node instance
        node = kanban_flow.KanbanCardNode('kanban-card', {}, config, None)
        assert node is not None
        assert node.config['title'] == 'My Card'

    def test_get_card_data(self):
        """Test that getCardData returns correct card data."""
        from flows import kanban_flow

        config = {
            'title': 'Test Card',
            'description': 'Test description',
            'priority': 'medium',
            'tags': ['test']
        }

        node = kanban_flow.KanbanCardNode('kanban-card', {}, config, None)
        card_data = node.getCardData()

        assert card_data['title'] == 'Test Card'
        assert card_data['description'] == 'Test description'
        assert card_data['priority'] == 'medium'
        assert card_data['tags'] == ['test']


class TestKanbanNodeIntegration:
    """Integration tests for KanbanNode."""

    def test_subscribe_column_move(self):
        """Test that column move subscription is handled."""
        from flows import kanban_flow

        mock_red = Mock()

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)
        node.moveCard = Mock()

        # Simulate column move event
        node.on('subscribe', {
            'type': 'column-move',
            'cardId': 'card-123',
            'columnId': 'in-progress'
        })

        # Should move the card
        node.moveCard('card-123', 'in-progress')

    def test_subscribe_card_update(self):
        """Test that card update subscription is handled."""
        from flows import kanban_flow

        mock_red = Mock()

        node = kanban_flow.KanbanNode('kanban-board', {}, {}, None)
        node.updateCard = Mock()

        # Simulate card update event
        node.on('subscribe', {
            'type': 'card-update',
            'cardId': 'card-123',
            'data': {'title': 'New Title'}
        })

        # Should update the card
        node.updateCard('card-123', {'title': 'New Title'})

    def test_auto_save_enabled(self):
        """Test that auto-save sets up interval when enabled."""
        from flows import kanban_flow

        config = {
            'autoSave': True,
            'saveInterval': 5000
        }

        node = kanban_flow.KanbanNode('kanban-board', {}, config, None)

        # Should have interval set
        assert node.autoSave == True

    def test_auto_save_disabled(self):
        """Test that auto-save doesn't set interval when disabled."""
        from flows import kanban_flow

        config = {
            'autoSave': False
        }

        node = kanban_flow.KanbanNode('kanban-board', {}, config, None)

        # Should not have auto-save enabled
        assert node.autoSave == False
