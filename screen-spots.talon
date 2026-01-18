mode: command
-
# === SAVING SPOTS ===

# save a mouse position as a window-specific spot (shows selection GUI)
spot save <user.text>: user.save_spot_window(user.text)

# save a mouse position as a global spot (works in any window)
spot save (all|free|wide|base) <user.text>: user.save_spot(user.text)

# === USING SPOTS ===

# click a saved spot then return the cursor to its prior position
spot [(click|touch)] <user.text>: user.click_spot(user.text)

# move the cursor to a saved spot
spot move <user.text>: user.move_to_spot(user.text)

# hold left click then move the cursor to a saved spot
spot drag <user.text>: user.drag_spot(user.text)

spot swipe <user.text>: user.drag_spot(user.text, 1)

# === WINDOW-ONLY ACCESS (explicit window-spot-only) ===

# click a window-specific spot (only if current window matches)
spot window [(click|touch)] <user.text>: user.click_spot_window(user.text)

# move to a window-specific spot (only if current window matches)
spot window move <user.text>: user.move_to_spot_window(user.text)

# === MANAGEMENT ===

# deletes all current spots
spot clear all: user.clear_spot_dictionary()

# deletes all spots that match the current window
spot clear all window: user.clear_spot_dictionary_window()

# delete a specific spot
spot clear <user.text>: user.clear_spot(user.text)

# display a list of all active spot names (shows global vs window-specific)
spot list [all]: user.list_spot()

# Close the list of active spot names. including 'clothes' because that's commonly misheard by talon
spot (close|clothes)$: user.close_spot_list()

# displays a small colored circle at the location of each saved spot (only shows spots relevant to current window)
spot [toggle] heatmap: user.toggle_spot_heatmap()

# open the spots CSV file for manual editing
spot edit file: user.edit_spots_file()
