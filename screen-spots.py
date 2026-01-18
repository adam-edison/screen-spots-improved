import csv
import os
import socket
import re
from pathlib import Path
from talon import ctrl, Module, actions, imgui, ui, canvas, settings, app, Context
from talon.skia import Paint

# Import the parser from our separate module
from .window_title_parser import get_suggested_patterns

mod = Module()
ctx = Context()


def _find_break_point(text: str, width: int) -> int:
    """Find a good break point (space) near the width, or hard break at width."""
    break_at = text.rfind(" ", 0, width)
    if break_at == -1:
        return width
    return break_at


def _wrap_single_line(text: str, width: int, indent: str) -> tuple[str, str]:
    """Wrap a single line and return (wrapped_line, remaining_text)."""
    if len(text) <= width:
        return f"{indent}{text}", ""
    break_at = _find_break_point(text, width)
    return f"{indent}{text[:break_at]}", text[break_at:].lstrip()


def wrap_text(text: str, width: int = 60, indent: str = "   ") -> list[str]:
    """Wrap text to specified width, returning list of lines with indent."""
    lines = []
    while text:
        line, text = _wrap_single_line(text, width, indent)
        lines.append(line)
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
OLD_SPOTS_FILE = SPOTS_DIR / "screen-spots.csv"  # Legacy file for migration
CSV_HEADERS = ("Name", "X", "Y", "WindowPattern")

# Spot dictionary: {profile: {name: {"coords": [x, y], "window_pattern": str or None}}}
# Profile format: "{hostname}-{screen_index}-{width}x{height}"
spot_dictionary = {}

# Currently active profiles (for screens that are connected)
active_profiles = []

heatmap_showing = False

# State for the window pattern selection GUI
pending_spot_name = None
pending_spot_coords = None
pending_spot_screen_index = None  # Track which screen the spot is being saved for
pending_suggestions = []  # List of {"pattern": str, "description": str, "type": str}
pending_custom_pattern = ""  # For custom text input


# ============ Profile Detection Functions ============

def get_hostname() -> str:
    """Get the machine hostname (without domain suffix)"""
    hostname = socket.gethostname()
    # Remove .local or other domain suffixes
    if "." in hostname:
        hostname = hostname.split(".")[0]
    return hostname


def get_screen_profile(screen_index: int) -> str:
    """Get the profile key for a specific screen index"""
    screens = ui.screens()
    if screen_index < 0 or screen_index >= len(screens):
        screen_index = 0
    screen = screens[screen_index]
    hostname = get_hostname()
    width = int(screen.rect.width)
    height = int(screen.rect.height)
    return f"{hostname}-{screen_index}-{width}x{height}"


def get_all_current_profiles() -> list[str]:
    """Get profile keys for all currently connected screens"""
    profiles = []
    for i in range(len(ui.screens())):
        profiles.append(get_screen_profile(i))
    return profiles


def get_screen_for_point(x: int, y: int) -> int:
    """Determine which screen contains the given point"""
    screens = ui.screens()
    for i, screen in enumerate(screens):
        if screen.rect.contains(x, y):
            return i
    # Fallback to main screen
    return 0


def get_profile_csv_path(profile: str) -> Path:
    """Get the CSV file path for a specific profile"""
    # Sanitize profile for filesystem (replace any problematic chars)
    safe_profile = re.sub(r'[<>:"/\\|?*]', '_', profile)
    return SPOTS_DIR / f"screen-spots-{safe_profile}.csv"


# ============ CSV File Operations ============

def ensure_csv_exists(profile: str):
    """Create the CSV file with headers if it doesn't exist"""
    csv_path = get_profile_csv_path(profile)
    if not csv_path.is_file():
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)


def _parse_spot_row(row: dict) -> tuple[str, dict] | None:
    """Parse a CSV row into a spot entry. Returns (name, spot_data) or None if invalid."""
    name = row.get("Name", "").strip()
    if not name:
        return None
    try:
        x = int(row.get("X", 0))
        y = int(row.get("Y", 0))
        window_pattern = row.get("WindowPattern", "").strip() or None
        return name, {"coords": [x, y], "window_pattern": window_pattern}
    except (ValueError, TypeError):
        return None


def _read_spots_csv(csv_path: Path) -> dict:
    """Read spots from a CSV file path."""
    spots = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result = _parse_spot_row(row)
            if result:
                name, spot_data = result
                spots[name] = spot_data
    return spots


def load_spots_for_profile(profile: str) -> dict:
    """Load spots from a profile's CSV file"""
    csv_path = get_profile_csv_path(profile)
    if not csv_path.is_file():
        return {}
    try:
        return _read_spots_csv(csv_path)
    except Exception as e:
        app.notify(f"Error loading spots for {profile}: {e}")
        return {}


def _load_profile_spots(profile: str) -> dict:
    """Load spots for a profile, returning empty dict if none found."""
    return load_spots_for_profile(profile) or {}


def _notify_spots_loaded(spot_dict: dict):
    """Notify user about loaded spots if any exist."""
    total = sum(len(spots) for spots in spot_dict.values())
    profiles_with_spots = [p for p, s in spot_dict.items() if s]
    if profiles_with_spots:
        app.notify(f"Loaded {total} spots from {len(profiles_with_spots)} profile(s)")


def load_all_spots():
    """Load spots from all profile CSVs for currently connected screens"""
    global spot_dictionary, active_profiles
    active_profiles = get_all_current_profiles()
    spot_dictionary = {profile: _load_profile_spots(profile) for profile in active_profiles}
    _notify_spots_loaded(spot_dictionary)


def save_spots_for_profile(profile: str):
    """Save spots for a specific profile to its CSV file"""
    ensure_csv_exists(profile)
    csv_path = get_profile_csv_path(profile)
    
    spots = spot_dictionary.get(profile, {})
    
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
            for name, spot in spots.items():
                coords = spot["coords"]
                window_pattern = spot.get("window_pattern") or ""
                writer.writerow([name, coords[0], coords[1], window_pattern])
    except Exception as e:
        app.notify(f"Error saving spots for {profile}: {e}")


def add_spot(name: str, x: int, y: int, window_pattern: str = None, screen_index: int = None):
    """Add or update a spot for a specific screen"""
    if screen_index is None:
        screen_index = get_screen_for_point(x, y)
    
    profile = get_screen_profile(screen_index)
    
    # Ensure profile exists in dictionary
    if profile not in spot_dictionary:
        spot_dictionary[profile] = {}
    
    spot_dictionary[profile][name] = {
        "coords": [x, y],
        "window_pattern": window_pattern
    }
    
    save_spots_for_profile(profile)
    refresh()
    
    return profile


def _has_existing_profile_csvs() -> bool:
    """Check if any profile-based CSV files already exist."""
    existing = list(SPOTS_DIR.glob("screen-spots-*.csv"))
    return any(p != OLD_SPOTS_FILE for p in existing)


def _load_old_spots_file() -> dict | None:
    """Load spots from the old CSV file. Returns None on error."""
    try:
        return _read_spots_csv(OLD_SPOTS_FILE)
    except Exception as e:
        app.notify(f"Error reading old spots file: {e}")
        return None


def _backup_old_spots_file(old_spots: dict, profile: str):
    """Backup the old spots file after migration."""
    backup_path = SPOTS_DIR / "screen-spots-migrated-backup.csv"
    try:
        OLD_SPOTS_FILE.rename(backup_path)
        app.notify(f"Migrated {len(old_spots)} spots to {profile}. Old file backed up.")
    except Exception as e:
        app.notify(f"Error during migration: {e}")


def migrate_old_spots():
    """One-time migration from old single CSV to profile-based CSVs"""
    if not OLD_SPOTS_FILE.is_file():
        return
    if _has_existing_profile_csvs():
        return
    old_spots = _load_old_spots_file()
    if not old_spots:
        return
    profile = get_screen_profile(0)
    spot_dictionary[profile] = old_spots
    save_spots_for_profile(profile)
    _backup_old_spots_file(old_spots, profile)


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


def _matches_app_pattern(pattern: str) -> bool:
    """Check if an app: pattern matches the current app."""
    app_pattern = pattern[4:]  # Remove "app:" prefix
    current_app = get_current_app_name()
    return app_pattern.lower() in current_app.lower()


def _matches_regex_pattern(pattern: str, title: str) -> bool:
    """Check if a regex pattern matches the title, with fallback to substring."""
    try:
        return bool(re.search(pattern, title, re.IGNORECASE))
    except re.error:
        return pattern.lower() in title.lower()


def spot_matches_current_window(spot: dict) -> bool:
    """Check if a spot matches the current window (or is global)"""
    window_pattern = spot.get("window_pattern")
    if window_pattern is None:
        return True
    if window_pattern.startswith("app:"):
        return _matches_app_pattern(window_pattern)
    current_title = get_current_window_title()
    if window_pattern.startswith("(?="):
        return _matches_regex_pattern(window_pattern, current_title)
    return window_pattern.lower() in current_title.lower()


def _spot_matches_criteria(spot: dict, window_only: bool) -> bool:
    """Check if a spot matches the search criteria."""
    if window_only:
        return spot.get("window_pattern") is not None and spot_matches_current_window(spot)
    return spot_matches_current_window(spot)


def get_spot_coords(spot_key: str, window_only: bool = False) -> tuple[list, str] | tuple[None, None]:
    """
    Get coordinates for a spot across all active profiles.
    If window_only is True, only return if spot has a window pattern AND matches current window.
    Otherwise, return if spot matches current window (global spots always match).
    Returns (coords [x, y], profile) or (None, None) if not found or doesn't match.
    """
    for profile in active_profiles:
        spot = spot_dictionary.get(profile, {}).get(spot_key)
        if spot and _spot_matches_criteria(spot, window_only):
            return spot["coords"], profile
    return None, None


def find_spot_profile(spot_key: str) -> str | None:
    """Find which profile a spot belongs to"""
    for profile in active_profiles:
        profile_spots = spot_dictionary.get(profile, {})
        if spot_key in profile_spots:
            return profile
    return None


# ============ Window Pattern Selection GUI ============

@imgui.open(y=0)
def gui_select_window_pattern(gui: imgui.GUI):
    """GUI for selecting which part of the window title to match"""
    global pending_spot_name, pending_spot_coords, pending_suggestions, pending_spot_screen_index
    
    # Show which screen/profile this will be saved to
    if pending_spot_screen_index is not None:
        profile = get_screen_profile(pending_spot_screen_index)
        gui.text(f"Save spot: {pending_spot_name}")
        gui.text(f"Screen: {pending_spot_screen_index} ({profile})")
    else:
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


def _format_spot_label(key: str, spot: dict, current_title: str, current_app: str) -> str:
    """Format a spot's display label based on its pattern type."""
    window_pattern = spot.get("window_pattern")
    if window_pattern is None:
        return f"  {key} (global)"
    if window_pattern.startswith("app:"):
        app_pattern = window_pattern[4:]
        prefix = "this app" if app_pattern.lower() in current_app.lower() else "app"
        return f"  {key} ({prefix}: {app_pattern})"
    prefix = "this window" if window_pattern.lower() in current_title.lower() else "window"
    return f"  {key} ({prefix}: {window_pattern})"


def _render_profile_spots(gui: imgui.GUI, profile: str, profile_spots: dict, current_title: str, current_app: str):
    """Render spots for a single profile."""
    gui.text(f"[{profile}]")
    for key, spot in profile_spots.items():
        gui.text(_format_spot_label(key, spot, current_title, current_app))
    gui.spacer()


@imgui.open(y=0)
def gui_list_keys(gui: imgui.GUI):
    """GUI for listing all spots"""
    gui.text("Spot Names")
    gui.text('Say "spot close" to close')
    gui.line()

    current_title = get_current_window_title()
    current_app = get_current_app_name()
    
    for profile in active_profiles:
        profile_spots = spot_dictionary.get(profile, {})
        if profile_spots:
            _render_profile_spots(gui, profile, profile_spots, current_title, current_app)

    if gui.button("Close"):
        actions.user.close_spot_list()


# ============ Heatmap Canvas ============

# We'll create canvases for each screen dynamically
heatmap_canvases = []


def setup_heatmap_canvases():
    """Create a canvas for each screen"""
    global heatmap_canvases
    
    # Close existing canvases
    for can in heatmap_canvases:
        can.close()
    heatmap_canvases = []
    
    # Create a canvas for each screen
    for screen in ui.screens():
        can = canvas.Canvas.from_screen(screen)
        can.register('draw', draw_spot)
        can.hide()
        heatmap_canvases.append(can)


def _get_all_active_spots() -> list[dict]:
    """Get all spots from all active profiles."""
    return [spot for profile in active_profiles for spot in spot_dictionary.get(profile, {}).values()]


def _spot_visible_on_canvas(spot: dict, canvas_rect) -> bool:
    """Check if a spot matches window and is visible on the canvas."""
    if not spot_matches_current_window(spot):
        return False
    coords = spot["coords"]
    return canvas_rect.contains(coords[0], coords[1])


def _get_visible_spot_coords(canvas_rect) -> list[tuple[int, int]]:
    """Get coordinates of all visible spots that match current window and are on this canvas."""
    visible_spots = [s for s in _get_all_active_spots() if _spot_visible_on_canvas(s, canvas_rect)]
    return [(s["coords"][0], s["coords"][1]) for s in visible_spots]


def draw_spot(c):
    c.paint.color = settings.get('user.screen_spots_heatmap_color')
    c.paint.style = Paint.Style.FILL
    size = settings.get('user.screen_spots_heatmap_size')
    for x, y in _get_visible_spot_coords(c.rect):
        c.draw_circle(x, y, size)


def refresh():
    if heatmap_showing:
        for can in heatmap_canvases:
            can.freeze()


def _open_file_with_system(file_path: Path):
    """Open a file using the system's default application."""
    import subprocess
    if app.platform == "mac":
        subprocess.run(["open", "-t", str(file_path)])
    elif app.platform == "windows":
        os.startfile(str(file_path))
    else:
        subprocess.run(["xdg-open", str(file_path)])


def _get_pattern_from_choice(choice: int) -> tuple[str | None, str]:
    """Get window pattern and description from a user's choice."""
    if choice == 0:
        return None, "global"
    window_pattern = pending_suggestions[choice - 1]["pattern"]
    return window_pattern, f"window: {window_pattern}"


def _move_mouse_to_coords(coords: list[int]):
    """Move mouse to coordinates, using slow move if enabled."""
    if settings.get('user.screen_spots_slow_move_enabled'):
        actions.user.slow_mouse_move(coords[0], coords[1])
    else:
        actions.mouse_move(coords[0], coords[1])


def _click_and_return(current_x: float, current_y: float):
    """Click at current position and return to original coordinates."""
    if settings.get('user.screen_spots_slow_move_enabled'):
        actions.user.slow_mouse_click()
        actions.user.slow_mouse_move(current_x, current_y)
    else:
        ctrl.mouse_click(button=0, hold=16000)
        actions.mouse_move(current_x, current_y)


# ============ Actions ============

@mod.action_class
class SpotClass:
    def save_spot(spot_key: str):
        """Saves the current mouse position as a global spot (works in any window)"""
        x = int(actions.mouse_x())
        y = int(actions.mouse_y())
        screen_index = get_screen_for_point(x, y)
        profile = add_spot(spot_key, x, y, None, screen_index)
        app.notify(f"Saved global spot: {spot_key} [{profile}]")

    def save_spot_window(spot_key: str):
        """Opens GUI to save mouse position as a window-specific spot"""
        global pending_spot_name, pending_spot_coords, pending_suggestions, pending_spot_screen_index
        
        pending_spot_coords = [int(actions.mouse_x()), int(actions.mouse_y())]
        pending_spot_name = spot_key
        pending_spot_screen_index = get_screen_for_point(pending_spot_coords[0], pending_spot_coords[1])
        
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
            profile = add_spot(spot_key, pending_spot_coords[0], pending_spot_coords[1], None, pending_spot_screen_index)
            app.notify(f"Saved global spot (no window info): {spot_key} [{profile}]")
            return
        
        ctx.tags = ["user.screen_spots_selecting"]
        gui_select_window_pattern.show()

    def spot_confirm_window_pattern(choice: int):
        """Confirm the window pattern selection (0 = global, 1+ = suggestion index)"""
        global pending_spot_name, pending_spot_coords, pending_suggestions, pending_spot_screen_index
        
        if pending_spot_name is None or pending_spot_coords is None:
            actions.user.spot_cancel_window_selection()
            return
        if choice < 0 or choice > len(pending_suggestions):
            app.notify(f"Invalid choice: {choice}")
            return
        
        window_pattern, pattern_desc = _get_pattern_from_choice(choice)
        profile = add_spot(pending_spot_name, pending_spot_coords[0], pending_spot_coords[1], window_pattern, pending_spot_screen_index)
        app.notify(f"Saved spot: {pending_spot_name} ({pattern_desc}) [{profile}]")
        actions.user.spot_cancel_window_selection()

    def spot_confirm_custom_pattern(pattern: str):
        """Confirm a custom window pattern typed by the user"""
        global pending_spot_name, pending_spot_coords, pending_spot_screen_index
        
        if pending_spot_name is None or pending_spot_coords is None:
            actions.user.spot_cancel_window_selection()
            return
        
        pattern = pattern.strip()
        window_pattern = pattern or None
        pattern_desc = f"window: {pattern}" if pattern else "global"
        if not pattern:
            app.notify("Empty pattern - saving as global")
        
        profile = add_spot(pending_spot_name, pending_spot_coords[0], pending_spot_coords[1], window_pattern, pending_spot_screen_index)
        app.notify(f"Saved spot: {pending_spot_name} ({pattern_desc}) [{profile}]")
        actions.user.spot_cancel_window_selection()

    def spot_cancel_window_selection():
        """Cancel the window pattern selection"""
        global pending_spot_name, pending_spot_coords, pending_suggestions, pending_spot_screen_index
        pending_spot_name = None
        pending_spot_coords = None
        pending_suggestions = []
        pending_spot_screen_index = None
        ctx.tags = []
        gui_select_window_pattern.hide()

    def toggle_spot_heatmap():
        """Display the spots on all screens"""
        global heatmap_showing
        heatmap_showing = not heatmap_showing
        action = (lambda c: c.freeze()) if heatmap_showing else (lambda c: c.hide())
        for can in heatmap_canvases:
            action(can)

    def move_to_spot(spot_key: str) -> bool:
        """
        Moves the cursor to a location, if one was saved for the given key
        and matches the current window.
        Returns true if the cursor was moved.
        """
        coords, profile = get_spot_coords(spot_key, window_only=False)
        if not coords:
            return False
        _move_mouse_to_coords(coords)
        return True

    def move_to_spot_window(spot_key: str) -> bool:
        """
        Moves the cursor to a window-specific spot only.
        Returns true if the cursor was moved (only if spot has window pattern AND matches).
        """
        coords, profile = get_spot_coords(spot_key, window_only=True)
        if not coords:
            return False
        _move_mouse_to_coords(coords)
        return True

    def click_spot(spot_key: str):
        """Clicks the saved mouse position (if it exists and matches) then returns cursor"""
        current_x = actions.mouse_x()
        current_y = actions.mouse_y()
        was_moved = actions.user.move_to_spot(spot_key)
        if was_moved:
            _click_and_return(current_x, current_y)

    def click_spot_window(spot_key: str):
        """Clicks a window-specific spot only (if it exists and matches current window)"""
        current_x = actions.mouse_x()
        current_y = actions.mouse_y()
        was_moved = actions.user.move_to_spot_window(spot_key)
        if was_moved:
            _click_and_return(current_x, current_y)

    def drag_spot(spot_key: str, release_drag: int = 0):
        """Drag the mouse from its current location to the saved position (if it exists)"""
        coords, profile = get_spot_coords(spot_key, window_only=False)
        if not coords:
            return
        actions.user.mouse_drag(0)
        actions.user.move_to_spot(spot_key)
        if release_drag != 0:
            actions.sleep("50ms")
            actions.mouse_release(0)

    def clear_spot_dictionary():
        """Reset all spots for all active profiles"""
        global spot_dictionary
        for profile in active_profiles:
            spot_dictionary[profile] = {}
            save_spots_for_profile(profile)
        refresh()
        app.notify("Cleared all spots for current screens")

    def clear_spot_dictionary_window():
        """Remove all spots specific to the current window pattern (across all profiles)"""
        global spot_dictionary
        current_title = get_current_window_title()
        
        for profile in active_profiles:
            profile_spots = spot_dictionary.get(profile, {})
            # Remove spots that match the current window (but not global spots)
            spot_dictionary[profile] = {
                k: v for k, v in profile_spots.items()
                if v.get("window_pattern") is None or 
                   v.get("window_pattern", "").lower() not in current_title.lower()
            }
            save_spots_for_profile(profile)
        
        refresh()

    def clear_spot(spot_key: str):
        """Remove a specific saved spot from whichever profile it's in"""
        global spot_dictionary
        
        profile = find_spot_profile(spot_key)
        if not profile:
            app.notify(f"Spot not found: {spot_key}")
            return
        del spot_dictionary[profile][spot_key]
        save_spots_for_profile(profile)
        refresh()
        app.notify(f"Cleared spot: {spot_key}")

    def list_spot():
        """Display a list of existing spot names"""
        gui_list_keys.show()

    def close_spot_list():
        """Closes the list of existing spot names"""
        gui_list_keys.hide()

    def edit_spots_file():
        """Open the spots CSV file for the main screen's profile"""
        profile = get_screen_profile(0)
        ensure_csv_exists(profile)
        csv_path = get_profile_csv_path(profile)
        _open_file_with_system(csv_path)

    def reload_spots():
        """Manually reload spots from CSV files for current screens"""
        load_all_spots()
        setup_heatmap_canvases()
        refresh()

    def show_spot_profiles():
        """Show current screen profiles"""
        profiles = get_all_current_profiles()
        for i, profile in enumerate(profiles):
            app.notify(f"Screen {i}: {profile}")


def _convert_old_spot_value(value) -> dict | None:
    """Convert an old storage value to the new spot format."""
    if isinstance(value, list):
        return {"coords": [int(value[0]), int(value[1])], "window_pattern": None}
    if isinstance(value, dict) and "coords" in value:
        coords = value["coords"]
        return {"coords": [int(coords[0]), int(coords[1])], "window_pattern": None}
    return None


def _convert_old_storage_data(old_data: dict) -> dict:
    """Convert old storage data to new spot format."""
    spots = {}
    for name, value in old_data.items():
        converted = _convert_old_spot_value(value)
        if converted:
            spots[name] = converted
    return spots


# Initialize by loading from CSV (or migrating from old storage)
def migrate_from_storage():
    """One-time migration from old Talon storage format to CSV"""
    from talon import storage
    old_data = storage.get("screen-spots", {})
    if not old_data:
        return
    if _has_existing_profile_csvs():
        return
    
    spots = _convert_old_storage_data(old_data)
    if not spots:
        return
    
    profile = get_screen_profile(0)
    spot_dictionary[profile] = spots
    save_spots_for_profile(profile)
    app.notify(f"Migrated {len(spots)} spots from Talon storage to {profile}")


def initialize():
    """Initialize the spots system"""
    # First, try to migrate from old Talon storage
    migrate_from_storage()
    
    # Then migrate from old single CSV file
    migrate_old_spots()
    
    # Load spots for current screen configuration
    load_all_spots()
    
    # Setup heatmap canvases
    setup_heatmap_canvases()


# Run initialization on startup
app.register("ready", lambda: initialize())
