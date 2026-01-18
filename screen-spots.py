import csv
import os
from pathlib import Path
from talon import ctrl, Module, actions, imgui, ui, canvas, settings, resource, app, Context

from talon.skia import Paint

# Import the parser from our separate module
from .window_title_parser import get_suggested_patterns

mod = Module()
ctx = Context()


def wrap_text(text: str, width: int = 60, indent: str = "   ") -> list[str]:
    """Wrap text to specified width, returning list of lines with indent."""
    if len(text) <= width:
        return [f"{indent}{text}"]
    
    lines = []
    while text:
        if len(text) <= width:
            lines.append(f"{indent}{text}")
            break
        # Find a good break point (space) near the width
        break_at = text.rfind(" ", 0, width)
        if break_at == -1:
            # No space found, hard break at width
            break_at = width
        lines.append(f"{indent}{text[:break_at]}")
        text = text[break_at:].lstrip()
    return lines


# Tag for when window selection GUI is open
mod.tag("screen_spots_selecting", desc="Tag for when the window pattern selection GUI is open")

mod.setting(
    "screen_spots_heatmap_color",
    type=str,
    default="ff0F9D58",
    desc="set the color of the drawn dots in the spot heatmap",
)

mod.setting(
    "screen_spots_heatmap_size",
    type=int,
    default=5,
    desc="set the size of the drawn dots in the spot heatmap",
)

mod.setting(
    "screen_spots_slow_move_enabled",
    type=int,
    default=0,
    desc="slows the mouse's movement speed during spot commands when enabled (some games don't detect the instant mouse movement correctly). Set to 0 (the default) to disable, any other number to enable",
)

# CSV file path - stored in same directory as this script
SPOTS_DIR = Path(__file__).parent
SPOTS_FILE = SPOTS_DIR / "screen-spots.csv"
CSV_HEADERS = ("Name", "X", "Y", "WindowPattern")

# Spot dictionary: {name: {"coords": [x, y], "window_pattern": str or None}}
spot_dictionary = {}

heatmap_showing = False

# State for the window pattern selection GUI
pending_spot_name = None
pending_spot_coords = None
pending_suggestions = []  # List of {"pattern": str, "description": str, "type": str}
pending_custom_pattern = ""  # For custom text input


def ensure_csv_exists():
    """Create the CSV file with headers if it doesn't exist"""
    if not SPOTS_FILE.is_file():
        with open(SPOTS_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)


def load_spots_from_csv():
    """Load spots from CSV file into spot_dictionary"""
    global spot_dictionary
    spot_dictionary = {}
    
    ensure_csv_exists()
    
    try:
        with open(SPOTS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("Name", "").strip()
                if not name:
                    continue
                try:
                    x = int(row.get("X", 0))
                    y = int(row.get("Y", 0))
                    window_pattern = row.get("WindowPattern", "").strip() or None
                    spot_dictionary[name] = {
                        "coords": [x, y],
                        "window_pattern": window_pattern
                    }
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        app.notify(f"Error loading spots: {e}")


def save_spots_to_csv():
    """Save all spots to CSV file"""
    ensure_csv_exists()
    
    try:
        with open(SPOTS_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
            for name, spot in spot_dictionary.items():
                coords = spot["coords"]
                window_pattern = spot.get("window_pattern") or ""
                writer.writerow([name, coords[0], coords[1], window_pattern])
    except Exception as e:
        app.notify(f"Error saving spots: {e}")


def add_spot_to_csv(name: str, x: int, y: int, window_pattern: str = None):
    """Add or update a single spot in the dictionary and save to CSV"""
    spot_dictionary[name] = {
        "coords": [x, y],
        "window_pattern": window_pattern
    }
    save_spots_to_csv()
    refresh()


# Watch the CSV file for external changes
@resource.watch(str(SPOTS_FILE))
def on_spots_file_change(f):
    load_spots_from_csv()
    refresh()


def get_current_window_title() -> str:
    """Get the current window's title"""
    try:
        return ui.active_window().title or ""
    except:
        return ""


def get_current_app_name() -> str:
    """Get the current window's application name"""
    try:
        return ui.active_window().app.name or ""
    except:
        return ""


def spot_matches_current_window(spot: dict) -> bool:
    """Check if a spot matches the current window (or is global)"""
    import re
    window_pattern = spot.get("window_pattern")
    
    if window_pattern is None:
        # Global spot - always matches
        return True
    
    # Check if it's an app-specific pattern (app:AppName)
    if window_pattern.startswith("app:"):
        app_pattern = window_pattern[4:]  # Remove "app:" prefix
        current_app = get_current_app_name()
        return app_pattern.lower() in current_app.lower()
    
    current_title = get_current_window_title()
    
    # Check if it's a regex pattern (combined pattern with lookaheads)
    if window_pattern.startswith("(?="):
        try:
            return bool(re.search(window_pattern, current_title, re.IGNORECASE))
        except re.error:
            # Invalid regex, fall back to substring match
            return window_pattern.lower() in current_title.lower()
    
    # Simple case-insensitive partial match
    return window_pattern.lower() in current_title.lower()


def get_spot_coords(spot_key: str, window_only: bool = False) -> list | None:
    """
    Get coordinates for a spot.
    If window_only is True, only return if spot has a window pattern AND matches current window.
    Otherwise, return if spot matches current window (global spots always match).
    Returns [x, y] or None if not found or doesn't match.
    """
    if spot_key not in spot_dictionary:
        return None
    
    spot = spot_dictionary[spot_key]
    
    if window_only:
        # Only return window-specific spots that match
        if spot.get("window_pattern") is None:
            return None  # Skip global spots
        if not spot_matches_current_window(spot):
            return None  # Window pattern doesn't match
        return spot["coords"]
    else:
        # Return if spot matches (global always matches, window-specific must match)
        if spot_matches_current_window(spot):
            return spot["coords"]
        return None


# ============ Window Pattern Selection GUI ============

@imgui.open(y=0)
def gui_select_window_pattern(gui: imgui.GUI):
    """GUI for selecting which part of the window title to match"""
    global pending_spot_name, pending_spot_coords, pending_suggestions
    
    gui.text(f"Save spot: {pending_spot_name}")
    gui.line()
    
    # Instructions
    gui.text("Voice commands:")
    gui.text('  "choose <number>" - select a pattern')
    gui.text('  "choose global" - save without window matching')
    gui.text('  "spot cancel" - cancel and don\'t save')
    gui.line()
    
    gui.text("Select window pattern to match:")
    gui.spacer()
    
    for i, suggestion in enumerate(pending_suggestions, 1):
        pattern = suggestion["pattern"]
        desc = suggestion["description"]
        stype = suggestion["type"]
        
        # Show type indicator
        type_label = f"[{stype}]" if stype != "segment" else ""
        
        # Button with number and type, full pattern on next line(s)
        if gui.button(f"{i}. {type_label} {desc}"):
            actions.user.spot_confirm_window_pattern(i)
        
        # Show full pattern below the button, wrapped if needed
        for line in wrap_text(pattern, width=40):
            gui.text(line)
    
    gui.spacer()
    gui.line()
    
    if gui.button("Save as GLOBAL (works in any window)"):
        actions.user.spot_confirm_window_pattern(0)
    
    gui.spacer()
    
    if gui.button("Cancel"):
        actions.user.spot_cancel_window_selection()


@imgui.open(y=0)
def gui_list_keys(gui: imgui.GUI):
    """GUI for listing all spots"""
    gui.text("Spot Names")
    gui.text('Say "spot close" to close')
    gui.line()

    current_title = get_current_window_title()
    current_app = get_current_app_name()
    for key, spot in spot_dictionary.items():
        window_pattern = spot.get("window_pattern")
        if window_pattern is None:
            gui.text(f"{key} (global)")
        elif window_pattern.startswith("app:"):
            app_pattern = window_pattern[4:]
            if app_pattern.lower() in current_app.lower():
                gui.text(f"{key} (this app: {app_pattern})")
            else:
                gui.text(f"{key} (app: {app_pattern})")
        elif window_pattern.lower() in current_title.lower():
            gui.text(f"{key} (this window: {window_pattern})")
        else:
            gui.text(f"{key} (window: {window_pattern})")

    gui.spacer()

    if gui.button("Close"):
        actions.user.close_spot_list()


# ============ Heatmap Canvas ============

can = canvas.Canvas.from_screen(ui.main_screen())

def draw_spot(canvas):
    canvas.paint.color = settings.get('user.screen_spots_heatmap_color')
    canvas.paint.style = Paint.Style.FILL
    for key, spot in spot_dictionary.items():
        # Only draw spots that match current window
        if spot_matches_current_window(spot):
            coords = spot["coords"]
            canvas.draw_circle(coords[0], coords[1], settings.get('user.screen_spots_heatmap_size'))

can.register('draw', draw_spot)
can.hide()

def refresh():
    if heatmap_showing:
        can.freeze()


# ============ Actions ============

@mod.action_class
class SpotClass:
    def save_spot(spot_key: str):
        """Saves the current mouse position as a global spot (works in any window)"""
        x = int(actions.mouse_x())
        y = int(actions.mouse_y())
        add_spot_to_csv(spot_key, x, y, None)
        app.notify(f"Saved global spot: {spot_key}")

    def save_spot_window(spot_key: str):
        """Opens GUI to save mouse position as a window-specific spot"""
        global pending_spot_name, pending_spot_coords, pending_suggestions
        
        pending_spot_name = spot_key
        pending_spot_coords = [int(actions.mouse_x()), int(actions.mouse_y())]
        
        current_title = get_current_window_title()
        current_app = get_current_app_name()
        
        # Get title-based suggestions
        pending_suggestions = get_suggested_patterns(current_title)
        
        # Add app-based suggestion at the beginning if we have an app name
        if current_app:
            pending_suggestions.insert(0, {
                "pattern": f"app:{current_app}",
                "description": f"Any {current_app} window",
                "type": "app"
            })
        
        if not pending_suggestions:
            # No title or app to parse, save as global
            add_spot_to_csv(spot_key, pending_spot_coords[0], pending_spot_coords[1], None)
            app.notify(f"Saved global spot (no window info): {spot_key}")
            return
        
        ctx.tags = ["user.screen_spots_selecting"]
        gui_select_window_pattern.show()

    def spot_confirm_window_pattern(choice: int):
        """Confirm the window pattern selection (0 = global, 1+ = suggestion index)"""
        global pending_spot_name, pending_spot_coords, pending_suggestions
        
        if pending_spot_name is None or pending_spot_coords is None:
            actions.user.spot_cancel_window_selection()
            return
        
        if choice == 0:
            # Save as global
            window_pattern = None
            pattern_desc = "global"
        elif 1 <= choice <= len(pending_suggestions):
            window_pattern = pending_suggestions[choice - 1]["pattern"]
            pattern_desc = f"window: {window_pattern}"
        else:
            app.notify(f"Invalid choice: {choice}")
            return
        
        add_spot_to_csv(pending_spot_name, pending_spot_coords[0], pending_spot_coords[1], window_pattern)
        app.notify(f"Saved spot: {pending_spot_name} ({pattern_desc})")
        
        # Cleanup
        actions.user.spot_cancel_window_selection()

    def spot_confirm_custom_pattern(pattern: str):
        """Confirm a custom window pattern typed by the user"""
        global pending_spot_name, pending_spot_coords
        
        if pending_spot_name is None or pending_spot_coords is None:
            actions.user.spot_cancel_window_selection()
            return
        
        pattern = pattern.strip()
        if not pattern:
            app.notify("Empty pattern - saving as global")
            window_pattern = None
            pattern_desc = "global"
        else:
            window_pattern = pattern
            pattern_desc = f"window: {window_pattern}"
        
        add_spot_to_csv(pending_spot_name, pending_spot_coords[0], pending_spot_coords[1], window_pattern)
        app.notify(f"Saved spot: {pending_spot_name} ({pattern_desc})")
        
        # Cleanup
        actions.user.spot_cancel_window_selection()

    def spot_cancel_window_selection():
        """Cancel the window pattern selection"""
        global pending_spot_name, pending_spot_coords, pending_suggestions
        pending_spot_name = None
        pending_spot_coords = None
        pending_suggestions = []
        ctx.tags = []
        gui_select_window_pattern.hide()

    def toggle_spot_heatmap():
        """Display the spot on the screen"""
        global can, heatmap_showing
        if heatmap_showing:
            can.hide()
            heatmap_showing = False
        else:
            can.freeze()
            heatmap_showing = True

    def move_to_spot(spot_key: str) -> bool:
        """
        Moves the cursor to a location, if one was saved for the given key
        and matches the current window.
        Returns true if the cursor was moved.
        """
        coords = get_spot_coords(spot_key, window_only=False)
        if coords:
            if settings.get('user.screen_spots_slow_move_enabled'):
                actions.user.slow_mouse_move(coords[0], coords[1])
            else:
                actions.mouse_move(coords[0], coords[1])
            return True
        return False

    def move_to_spot_window(spot_key: str) -> bool:
        """
        Moves the cursor to a window-specific spot only.
        Returns true if the cursor was moved (only if spot has window pattern AND matches).
        """
        coords = get_spot_coords(spot_key, window_only=True)
        if coords:
            if settings.get('user.screen_spots_slow_move_enabled'):
                actions.user.slow_mouse_move(coords[0], coords[1])
            else:
                actions.mouse_move(coords[0], coords[1])
            return True
        return False

    def click_spot(spot_key: str):
        """Clicks the saved mouse position (if it exists and matches) then returns cursor"""
        current_x = actions.mouse_x()
        current_y = actions.mouse_y()

        was_moved = actions.user.move_to_spot(spot_key)

        if was_moved:
            if settings.get('user.screen_spots_slow_move_enabled'):
                actions.user.slow_mouse_click()
                actions.user.slow_mouse_move(current_x, current_y)
            else:
                ctrl.mouse_click(button=0, hold=16000)
                actions.mouse_move(current_x, current_y)

    def click_spot_window(spot_key: str):
        """Clicks a window-specific spot only (if it exists and matches current window)"""
        current_x = actions.mouse_x()
        current_y = actions.mouse_y()

        was_moved = actions.user.move_to_spot_window(spot_key)

        if was_moved:
            if settings.get('user.screen_spots_slow_move_enabled'):
                actions.user.slow_mouse_click()
                actions.user.slow_mouse_move(current_x, current_y)
            else:
                ctrl.mouse_click(button=0, hold=16000)
                actions.mouse_move(current_x, current_y)

    def drag_spot(spot_key: str, release_drag: int = 0):
        """Drag the mouse from its current location to the saved position (if it exists)"""
        coords = get_spot_coords(spot_key, window_only=False)
        if coords:
            actions.user.mouse_drag(0)
            actions.user.move_to_spot(spot_key)
            if release_drag != 0:
                actions.sleep("50ms")
                actions.mouse_release(0)

    def clear_spot_dictionary():
        """Reset the active spot list to a new empty dictionary"""
        global spot_dictionary
        spot_dictionary = {}
        save_spots_to_csv()
        refresh()

    def clear_spot_dictionary_window():
        """Remove all spots specific to the current window pattern"""
        global spot_dictionary
        current_title = get_current_window_title()
        # Remove spots that match the current window (but not global spots)
        spot_dictionary = {
            k: v for k, v in spot_dictionary.items()
            if v.get("window_pattern") is None or 
               v.get("window_pattern", "").lower() not in current_title.lower()
        }
        save_spots_to_csv()
        refresh()

    def clear_spot(spot_key: str):
        """Remove a specific saved spot"""
        global spot_dictionary
        if spot_key in spot_dictionary:
            del spot_dictionary[spot_key]
            save_spots_to_csv()
            refresh()

    def list_spot():
        """Display a list of existing spot names"""
        gui_list_keys.show()

    def close_spot_list():
        """Closes the list of existing spot names"""
        gui_list_keys.hide()

    def edit_spots_file():
        """Open the spots CSV file for editing"""
        ensure_csv_exists()
        # Use platform-specific open command
        if app.platform == "mac":
            import subprocess
            subprocess.run(["open", "-t", str(SPOTS_FILE)])
        elif app.platform == "windows":
            os.startfile(str(SPOTS_FILE))
        else:
            import subprocess
            subprocess.run(["xdg-open", str(SPOTS_FILE)])


# Initialize by loading from CSV (or migrating from old storage)
def migrate_from_storage():
    """One-time migration from old storage format to CSV"""
    from talon import storage
    old_data = storage.get("screen-spots", {})
    if old_data and not SPOTS_FILE.exists():
        ensure_csv_exists()
        for name, value in old_data.items():
            if isinstance(value, list):
                # Old format: [x, y]
                add_spot_to_csv(name, int(value[0]), int(value[1]), None)
            elif isinstance(value, dict) and "coords" in value:
                # Intermediate format with app
                coords = value["coords"]
                add_spot_to_csv(name, int(coords[0]), int(coords[1]), None)
        app.notify("Migrated spots to CSV file")

# Run migration and initial load
migrate_from_storage()
load_spots_from_csv()
