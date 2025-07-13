"""Progress reporting with Rich progress bars."""

from typing import Any

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from coldstore.logger import console


class ProgressManager:
    """Manage progress reporting for cold storage operations."""

    def __init__(self):
        self.progress: Progress | None = None
        self.tasks: dict[str, TaskID] = {}

    def create_progress(self) -> Progress:
        """Create a Rich progress instance with cold storage styling."""
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        )
        return self.progress

    def add_task(self, name: str, description: str, total: int | None = None) -> TaskID:
        """Add a new progress task."""
        if self.progress is None:
            self.create_progress()

        task_id = self.progress.add_task(description, total=total)
        self.tasks[name] = task_id
        return task_id

    def update_task(
        self,
        name: str,
        advance: int | None = None,
        completed: int | None = None,
        description: str | None = None,
        **kwargs: Any,
    ):
        """Update a progress task."""
        if self.progress is None or name not in self.tasks:
            return

        update_kwargs = {}
        if advance is not None:
            update_kwargs["advance"] = advance
        if completed is not None:
            update_kwargs["completed"] = completed
        if description is not None:
            update_kwargs["description"] = description
        update_kwargs.update(kwargs)

        self.progress.update(self.tasks[name], **update_kwargs)

    def complete_task(self, name: str):
        """Mark a task as completed."""
        if self.progress is None or name not in self.tasks:
            return

        task = self.progress.tasks[self.tasks[name]]
        if task.total is not None:
            self.progress.update(self.tasks[name], completed=task.total)

    def remove_task(self, name: str):
        """Remove a task from progress."""
        if self.progress is None or name not in self.tasks:
            return

        self.progress.remove_task(self.tasks[name])
        del self.tasks[name]

    def start(self):
        """Start the progress display."""
        if self.progress is not None:
            self.progress.start()

    def stop(self):
        """Stop the progress display."""
        if self.progress is not None:
            self.progress.stop()

    def __enter__(self):
        """Context manager entry."""
        if self.progress is not None:
            self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.progress is not None:
            self.progress.stop()


def create_progress_manager() -> ProgressManager:
    """Create a progress manager instance."""
    return ProgressManager()
