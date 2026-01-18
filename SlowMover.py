import threading
from talon import cron, actions, Module, ctrl, settings
from math import copysign

mod = Module()

mod.setting(
    "screen_spots_slow_move_distance",
    type=int,
    default=200,
    desc="the maximum distance to move in either direction per tick during slow movement",
)


def _clamp_distance(distance: float, max_distance: int) -> float:
    """Clamp a distance to the maximum movement distance."""
    if abs(distance) <= max_distance:
        return distance
    return copysign(max_distance, distance)


class SlowMover:
    def __init__(self):
        self.job = None
        self.lock = threading.RLock()
        self.targets = []

    def _start_if_needed(self):
        """Start the movement job if not already running."""
        if self.job is None:
            self.start()

    def slowly_move_to(self, x, y):
        with self.lock:
            self.targets.append((x, y))
            self._start_if_needed()

    def slowly_click(self):
        with self.lock:
            self.targets.append('click')
            self._start_if_needed()

    def start(self):
        with self.lock:
            cron.cancel(self.job)
            self.job = cron.interval('16ms', self.tick)

    def stop(self):
        with self.lock:
            cron.cancel(self.job)
            self.job = None

    def _process_move_target(self, x, y):
        """Process a movement target."""
        self.small_movement(x, y)

    def _process_click_target(self):
        """Process a click target."""
        ctrl.mouse_click(button=0, hold=16000)
        self.targets.pop(0)

    def tick(self):
        with self.lock:
            if not self.targets:
                self.stop()
                return
            next_target = self.targets[0]
            if type(next_target) is tuple:
                self._process_move_target(next_target[0], next_target[1])
            else:
                self._process_click_target()

    def _calculate_movement(self, target_x, target_y) -> tuple[float, float]:
        """Calculate clamped movement distances."""
        current_x = actions.mouse_x()
        current_y = actions.mouse_y()
        max_dist = settings.get('user.screen_spots_slow_move_distance')
        x_dist = _clamp_distance(target_x - current_x, max_dist)
        y_dist = _clamp_distance(target_y - current_y, max_dist)
        return current_x + x_dist, current_y + y_dist, x_dist, y_dist

    def small_movement(self, target_x, target_y):
        new_x, new_y, x_dist, y_dist = self._calculate_movement(target_x, target_y)
        if x_dist == 0 and y_dist == 0:
            self.targets.pop(0)
            return
        actions.mouse_move(new_x, new_y)

mover = SlowMover()

@mod.action_class
class SlowMoveActions:
    def slow_mouse_move(x: int, y: int):
        """Move the cursor to a new position non instantly"""
        mover.slowly_move_to(x, y)

    def slow_mouse_click():
        """Click the mouse once the cursor has reached the position it is moving to"""
        mover.slowly_click()