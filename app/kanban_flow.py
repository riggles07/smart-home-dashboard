"""Kanban Flow - Task Management"""
from enum import Enum

class Status(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class Task:
    """Kanban task"""
    def __init__(self, title: str, description: str = ""):
        self.title = title
        self.description = description
        self.status = Status.TODO

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "status": self.status.value
        }

class KanbanBoard:
    """Kanban board for task tracking"""

    def __init__(self):
        self.columns = ["todo", "in_progress", "done"]
        self.tasks = []

    def add_task(self, task: Task):
        """Add task to TODO column"""
        self.tasks.append(task)

    def move_task(self, task_title: str, new_status: Status):
        """Move task to new column"""
        for task in self.tasks:
            if task.title == task_title:
                task.status = new_status
                return True
        return False

    def get_tasks_by_status(self, status: Status):
        """Get all tasks with given status"""
        return [t for t in self.tasks if t.status == status]
