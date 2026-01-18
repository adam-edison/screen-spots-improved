# screen-spots
Save a set of screen locations to later click on or move to using talon voice.

Defines shortcuts for saving the current mouse coordinates to a specific word/phrase. You can then use another shortcut with the same phrase to either move the mouse cursor to the saved position, or click on the saved position and immediately return the cursor to its current position.

The intended use case is to save the position of buttons or other frequently used locations so that you can click on them or return to them more quickly and with less effort.

Your spots are stored in a CSV file (`screen-spots.csv`) that persists across Talon restarts and can be manually edited.

# Installation
Assumes you already have Talon Voice: https://talonvoice.com/

Clone or copy this entire repo into the user/ directory of your talon installation.

# Global vs Window-Specific Spots

Spots can be saved in two modes:

- **Global spots** work in any window (the default behavior)
- **Window-specific spots** only work when the window title contains a specific pattern

This is useful when you have spots that only make sense in certain contexts:
- A "compose" button that only exists in Gmail
- Navigation elements in VS Code that shouldn't trigger in other apps
- Browser tabs with specific web apps open

## How Window Matching Works

When you save a window-specific spot, a GUI appears showing segments of the current window title. For example, if your window title is:

```
GitHub - screen-spots-improved - Cursor
```

You'll see options like:
1. GitHub
2. screen-spots-improved
3. Cursor
4. GitHub - screen-spots-improved - Cursor (full title)

Choose which segment the spot should match. The spot will only activate when that text appears anywhere in the window title (case-insensitive).

# Examples

## Global Spots
Place your mouse cursor over something you click a lot.

Say **"spot save one"** to save it as a global spot.

Say **"spot click one"** or **"spot one"** whenever you want to click that spot (works in any window).

## Window-Specific Spots
Open Gmail in your browser. Place your mouse over the Compose button.

Say **"spot save window compose"** - a GUI appears with window title segments.

Say **"choose 1"** to match "Gmail" (or whichever segment you want).

Now the "compose" spot only works when "Gmail" is in your window title.

Switch to a different tab - say **"spot compose"** - nothing happens.

Switch back to Gmail - say **"spot compose"** - clicks the Compose button!

## Other Commands

Say **"spot move enemy"** to move your mouse over that spot (without clicking)

Say **"spot drag enemy"** to click and drag from the current mouse position to that spot

Say **"spot heatmap"** to toggle showing all saved spots with a small colored circle on the screen (only shows spots relevant to current window)

Say **"spot list"** to see all spots with labels showing whether they are global or window-specific

Say **"spot edit file"** to open the CSV file in your text editor for manual editing

Check screen-spots.talon for more commands. You can delete some or all spots.

# CSV File Format

Spots are stored in `screen-spots.csv` with the following columns:

| Name | X | Y | WindowPattern |
|------|---|---|---------------|
| one | 100 | 200 | |
| compose | 300 | 400 | Gmail |
| sidebar | 50 | 150 | Cursor |

- **Name**: The spoken name for the spot
- **X, Y**: Screen coordinates
- **WindowPattern**: Text that must appear in window title (empty = global)

You can edit this file directly - changes are automatically detected and reloaded.

# Talon Settings
You can use the following settings to customize how this tool functions. You can refer to the unofficial talon wiki for how [talon settings](https://talon.wiki/unofficial_talon_docs/#settings) work.

- `screen_spots_heatmap_color` the color of the drawn dots in the spot heatmap, default="ff0F9D58"
- `screen_spots_heatmap_size` the size of the drawn dots in the spot heatmap, default=5
- `screen_spots_slow_move_enabled` slows the mouse's movement speed during spot commands when enabled (some games don't detect the instant mouse movement correctly). Set to 0 (the default) to disable, any other number to enable
- `screen_spots_slow_move_distance` the maximum distance to move in either direction per tick during slow movement, default=200

# Command Reference

## Saving Spots
| Command | Description |
|---------|-------------|
| `spot save <name>` | Save as global spot (works everywhere) |
| `spot save window <name>` | Save as window-specific spot (shows selection GUI) |

## Using Spots
| Command | Description |
|---------|-------------|
| `spot <name>` | Click spot and return cursor |
| `spot move <name>` | Move cursor to spot |
| `spot drag <name>` | Drag from current position to spot |
| `spot swipe <name>` | Drag and release |
| `spot window <name>` | Click window-specific spot only |
| `spot window move <name>` | Move to window-specific spot only |

## Management
| Command | Description |
|---------|-------------|
| `spot list` | Show all spots |
| `spot close` | Close the spot list |
| `spot heatmap` | Toggle visual overlay |
| `spot clear <name>` | Delete a specific spot |
| `spot clear all` | Delete all spots |
| `spot clear all window` | Delete spots matching current window |
| `spot edit file` | Open CSV file for editing |

## Selection GUI (when saving window spot)
| Command | Description |
|---------|-------------|
| `choose <number>` | Select window pattern by number |
| `choose global` | Save as global instead |
| `spot cancel` | Cancel and don't save |
