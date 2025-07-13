"""Rich logging system for Cold Storage Standard - replacing bash color logs."""

from loguru import logger
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

console = Console()

# Global verbosity control
_verbose = False
_quiet = False

# Color scheme matching bash script
COLORS = {
    "info": "bright_blue",
    "success": "bright_green",
    "warning": "yellow",
    "error": "bright_red",
    "step": "blue",
    "detail": "dim white",
    "progress": "bright_magenta",
}


def setup_logging(verbose: bool = False, quiet: bool = False):
    """Set up logging configuration matching bash script behavior."""
    global _verbose, _quiet

    # Store global verbosity state
    _verbose = verbose
    _quiet = quiet

    # Remove default logger
    logger.remove()

    # Handle conflicting options
    if verbose and quiet:
        console.print(
            "[yellow]⚠[/yellow] Warning: Both --verbose and --quiet specified. "
            "Using --quiet (suppressing verbose output)."
        )
        # quiet takes precedence
        level = "WARNING"
        _verbose = False  # Override verbose when conflict
    elif quiet:
        level = "WARNING"
    elif verbose:
        level = "DEBUG"
    else:
        level = "INFO"

    # Add rich handler
    logger.add(
        RichHandler(
            console=console,
            show_time=False,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
        ),
        level=level,
        format="<level>{message}</level>",
    )


def _should_show_info() -> bool:
    """Check if info messages should be shown."""
    return not _quiet


def _should_show_detail() -> bool:
    """Check if detail messages should be shown."""
    return _verbose and not _quiet


def log_info(message: str, prefix: str = "ℹ"):
    """Log info message (blue-green color like bash log_info)."""
    if _should_show_info():
        console.print(f"[{COLORS['info']}]{prefix}[/{COLORS['info']}] {message}")


def log_success(message: str, prefix: str = "✓"):
    """Log success message (green color like bash log_success)."""
    if _should_show_info():
        console.print(f"[{COLORS['success']}]{prefix}[/{COLORS['success']}] {message}")


def log_warning(message: str, prefix: str = "⚠"):
    """Log warning message (yellow color like bash log_warning)."""
    # Warnings always show (even in quiet mode)
    console.print(f"[{COLORS['warning']}]{prefix}[/{COLORS['warning']}] {message}")


def log_error(message: str, prefix: str = "✗"):
    """Log error message (red color like bash log_error)."""
    # Errors always show (even in quiet mode)
    console.print(f"[{COLORS['error']}]{prefix}[/{COLORS['error']}] {message}")


def log_step(message: str, step_num: int | None = None):
    """Log step message (blue color like bash log_step)."""
    if _should_show_info():
        prefix = f"[{step_num}]" if step_num else "▶"
        console.print(f"[{COLORS['step']}]{prefix}[/{COLORS['step']}] {message}")


def log_detail(message: str, prefix: str = "  "):
    """Log detail message (gray color like bash log_detail)."""
    if _should_show_detail():
        console.print(f"[{COLORS['detail']}]{prefix}{message}[/{COLORS['detail']}]")


def log_progress(message: str):
    """Log progress message (magenta color like bash log_progress)."""
    if _should_show_info():
        console.print(f"[{COLORS['progress']}]⏳[/{COLORS['progress']}] {message}")


def create_progress_bar(description: str = "Processing...") -> Progress:
    """Create a rich progress bar matching bash script style."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def show_header(title: str, subtitle: str = ""):
    """Display header panel like bash script headers."""
    if _should_show_info():
        header_text = Text(title, style="bold bright_blue")
        if subtitle:
            header_text.append(f"\n{subtitle}", style="dim")

        console.print(
            Panel(
                header_text,
                border_style="bright_blue",
                padding=(1, 2),
            )
        )


def show_summary(title: str, items: list[str]):
    """Display summary panel like bash script statistics."""
    if _should_show_info():
        summary_text = Text()
        for item in items:
            summary_text.append(f"• {item}\n", style="dim")

        console.print(
            Panel(
                summary_text,
                title=title,
                border_style="bright_green",
                padding=(1, 2),
            )
        )


def confirm_action(message: str, default: bool = True) -> bool:
    """Confirm action with user input."""
    prompt = f"[yellow]?[/yellow] {message}"
    if default:
        prompt += " [dim]\\[Y/n][/dim]"
    else:
        prompt += " [dim]\\[y/N][/dim]"

    console.print(prompt)

    try:
        response = input().strip().lower()
        if not response:
            return default
        return response.startswith("y")
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operation cancelled[/yellow]")
        return False
