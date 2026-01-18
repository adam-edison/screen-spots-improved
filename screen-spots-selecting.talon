# Commands available when the window pattern selection GUI is open
tag: user.screen_spots_selecting
-

# Select a window pattern by number
choose <number_small>: user.spot_confirm_window_pattern(number_small)

# Save as global (no window matching)
choose global: user.spot_confirm_window_pattern(0)

# Cancel the selection
spot cancel: user.spot_cancel_window_selection()
