"""realrap - real random password.

Wireframe cubes that double as a password generator: each cube contributes
one character, derived from a secret random seed plus its current rotation,
size and position, so the more cubes you have the longer the password gets,
and spinning a cube changes its character.

Controls:
  Right-click + hold + drag    - create a new cube (drag out to set its size)
  Left-click + hold + drag     - rotate the cube under the cursor: precisely by
                                  its nearest edge if the cursor is close to
                                  one, otherwise by whichever face it's over.
                                  Starting the drag on empty space instead
                                  sweeps the cursor across the scene, rotating
                                  every cube whose edge the drag path crosses.
  Left-click (short, no drag)  - despawn the cube under the cursor
  Arrow keys                   - rotate whichever cube is currently under the mouse
  Mouse wheel                  - zoom in/out
  N                             - spawn a random cube
  C                             - clear all cubes
  T                             - toggle window transparency (Windows only;
                                  the background is only visually see-through,
                                  clicks on it still reach the app)
  Click Show / Hide             - reveal or mask the password (masked by default)
  Click Copy (bottom bar)       - copy the password to the clipboard; it is
                                  wiped again after 30 s or on exit, and kept
                                  out of the Win+V history and cloud sync
  Click Save Image (bottom bar) - save the cube scene (no UI) into ./screenshots
  Drag title bar / window edge  - move / resize the window (classic Windows style
                                  chrome drawn by the app; double-click the
                                  title bar to maximize)
  Esc / close button            - quit
"""

import colorsys
import ctypes
import ctypes.wintypes
import datetime
import functools
import hashlib
import math
import os
import random
import secrets
import string
import sys

import pygame

try:
    import pyperclip
except ImportError:
    pyperclip = None

# Window size is mutable: the window is resizable, and set_window_size()
# keeps these in sync with it.
WIDTH, HEIGHT = 1350, 1080
MIN_WIDTH, MIN_HEIGHT = 720, 300

# Classic Windows (98/2000) window chrome, drawn by the app itself: the
# window is borderless so the native title bar doesn't show. The cube view
# sits inside it, between the title bar and the bottom bar. VIEW_HEIGHT is
# the y where the bottom bar starts.
FRAME = 4
TITLE_HEIGHT = 18
BAR_HEIGHT = 40
VIEW_TOP = FRAME + TITLE_HEIGHT + 1
VIEW_HEIGHT = HEIGHT - FRAME - BAR_HEIGHT
RESIZE_GRIP = 5
RESIZE_CORNER = 16
CAPTION_BUTTON_SIZE = (16, 14)
DOUBLE_CLICK_MS = 400
WINDOW_TITLE = "realrap"
# Borderless on Windows, where NativeWindow takes over moving/resizing.
WINDOW_FLAGS = pygame.RESIZABLE | (pygame.NOFRAME if sys.platform == "win32" else 0)

BG_COLOR = (0, 0, 0)
PREVIEW_COLOR = (0, 140, 0)
UI_COLOR = (0, 255, 0)

# Fill alpha of a cube's faces: a soft tint of its edge color, a bit
# stronger on faces turned toward the viewer so the cube still reads as 3D.
FACE_ALPHA_MIN = 25
FACE_ALPHA_MAX = 70

# Windows classic system colors.
WIN_FACE = (212, 208, 200)
WIN_LIGHT = (255, 255, 255)
WIN_SHADOW = (128, 128, 128)
WIN_DARK_SHADOW = (64, 64, 64)
WIN_TEXT = (0, 0, 0)
WIN_GRAY_TEXT = (128, 128, 128)
WIN_TITLE_ACTIVE = ((0, 0, 128), (16, 132, 208))
WIN_TITLE_INACTIVE = ((128, 128, 128), (192, 192, 192))
WIN_TITLE_TEXT_INACTIVE = (212, 208, 200)

# Orthographic projection: scale does not depend on depth, so a cube's edges
# always keep their true proportions on screen - no perspective keystoning,
# so cubes always render as real cubes.
BASE_SCALE = 60.0
MIN_CUBE_SIZE = 0.4
MAX_CUBE_SIZE = 2.5

EDGE_HOVER_PX = 8
ROTATE_PIXEL_SENSITIVITY = 0.01
KEY_ROTATE_SPEED = 2.0
CLICK_MOVE_THRESHOLD_PX = 5

# In a PyInstaller .exe, __file__ points into a temp folder that is deleted on
# exit, so screenshots go next to the .exe instead; bundled files (the icon)
# are unpacked to sys._MEIPASS.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(APP_DIR, "screenshots")
ICON_PATH = os.path.join(RESOURCE_DIR, "assets", "icon.png")

# Digits are repeated and specials broadened so both show up far more often
# in generated passwords than a plain a-zA-Z0-9+few-specials mix would.
SPECIAL_CHARS = "!@#$%^&*()-_=+[]{};:,.<>/?~"
CHARSET = string.ascii_letters + (string.digits * 2) + SPECIAL_CHARS

# Every cube's character is an independent draw from CHARSET (digits count
# twice), so each one adds this many bits of entropy - about 6.4.
BITS_PER_CHAR = -sum(
    CHARSET.count(c) / len(CHARSET) * math.log2(CHARSET.count(c) / len(CHARSET)) for c in set(CHARSET)
)
STRENGTH_LEVELS = [  # (minimum bits, label, color)
    (0, "Very weak", (192, 0, 0)),
    (40, "Weak", (224, 96, 0)),
    (56, "Fair", (200, 160, 0)),
    (72, "Good", (0, 150, 0)),
    (96, "Strong", (0, 110, 0)),
]
STRENGTH_FULL_BITS = 128

CLIPBOARD_CLEAR_MS = 30_000

# A pleasant default tilt so a freshly spawned cube reads as 3D immediately.
INITIAL_ANGLE_X = math.radians(25)
INITIAL_ANGLE_Y = math.radians(35)

# Unit cube centered on origin.
CUBE_VERTICES = [
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
]

CUBE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
]

# Each face as 4 vertex indices forming a simple (non-self-intersecting) quad.
CUBE_FACES = [
    (0, 1, 2, 3),  # front
    (5, 4, 7, 6),  # back
    (4, 0, 3, 7),  # left
    (1, 5, 6, 2),  # right
    (3, 2, 6, 7),  # top
    (4, 5, 1, 0),  # bottom
]


def rotate_point(point, angle_x, angle_y, angle_z):
    x, y, z = point

    cos_x, sin_x = math.cos(angle_x), math.sin(angle_x)
    y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x

    cos_y, sin_y = math.cos(angle_y), math.sin(angle_y)
    x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y

    cos_z, sin_z = math.cos(angle_z), math.sin(angle_z)
    x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z

    return x, y, z


class Cube:
    def __init__(self, position=(0.0, 0.0, 0.0), size=1.0):
        self.position = position
        self.size = size
        self.angle_x = INITIAL_ANGLE_X
        self.angle_y = INITIAL_ANGLE_Y
        self.angle_z = 0.0
        # The seed is the password's real entropy source, so it comes from
        # the OS's cryptographic RNG rather than the predictable `random`.
        self.seed = secrets.randbits(32)

    def update(self, dt, extra_x=0.0, extra_y=0.0):
        self.angle_x += extra_x * dt
        self.angle_y += extra_y * dt

    def spin(self, delta_x, delta_y):
        self.angle_x += delta_x
        self.angle_y += delta_y

    def transformed_vertices(self):
        px, py, pz = self.position
        result = []
        for vx, vy, vz in CUBE_VERTICES:
            x, y, z = vx * self.size, vy * self.size, vz * self.size
            x, y, z = rotate_point((x, y, z), self.angle_x, self.angle_y, self.angle_z)
            result.append((x + px, y + py, z + pz))
        return result

    def char(self):
        """Hash of everything about the cube, so changing its rotation, size or
        position changes the character. The secret seed stays in the mix:
        the geometry alone is visible on screen (and in saved images), so a
        password built only from it could be recomputed by anyone who sees it."""
        geometry = (self.angle_x, self.angle_y, self.angle_z, self.size, *self.position)
        key = ":".join([str(self.seed)] + [f"{round(v, 3)}" for v in geometry])
        digest = hashlib.sha256(key.encode()).hexdigest()
        return CHARSET[int(digest[:8], 16) % len(CHARSET)]


def project(point, zoom):
    x, y, _z = point
    scale = BASE_SCALE * zoom
    screen_x = x * scale + WIDTH / 2
    screen_y = -y * scale + (VIEW_TOP + VIEW_HEIGHT) / 2
    return screen_x, screen_y


def unproject_to_plane(screen_pos, zoom):
    scale = BASE_SCALE * zoom
    sx, sy = screen_pos
    x = (sx - WIDTH / 2) / scale
    y = -(sy - (VIEW_TOP + VIEW_HEIGHT) / 2) / scale
    return x, y, 0.0


def view_rect():
    return pygame.Rect(FRAME, VIEW_TOP, WIDTH - 2 * FRAME, VIEW_HEIGHT - VIEW_TOP)


def draw_cube(screen, cube, zoom, color, filled=True):
    verts_3d = cube.transformed_vertices()
    verts_2d = [project(v, zoom) for v in verts_3d]
    if filled:
        draw_cube_faces(screen, cube, verts_3d, verts_2d, color)
    for a, b in CUBE_EDGES:
        pygame.draw.aaline(screen, color, verts_2d[a], verts_2d[b])


def draw_cube_faces(screen, cube, verts_3d, verts_2d, color):
    """Tint the faces turned toward the viewer (they never overlap, since the
    cube is convex). Drawn on a small layer and blitted, because drawing
    translucent shapes straight onto the canvas would replace its pixels
    instead of blending with them."""
    xs = [x for x, _ in verts_2d]
    ys = [y for _, y in verts_2d]
    left, top = math.floor(min(xs)), math.floor(min(ys))
    bounds = pygame.Rect(left, top, math.ceil(max(xs)) - left + 1, math.ceil(max(ys)) - top + 1)
    bounds = bounds.clip(screen.get_rect())  # zoomed-in cubes can be far bigger than the screen
    if not bounds:
        return
    left, top = bounds.topleft
    layer = pygame.Surface(bounds.size, pygame.SRCALPHA)

    center = cube.position
    half = cube.size
    for face in CUBE_FACES:
        # A face's outward normal points from the cube center to the face
        # center; the viewer looks along +z, so it faces them if z < 0.
        face_z = sum(verts_3d[i][2] for i in face) / 4 - center[2]
        facing = -face_z / half
        if facing <= 0:
            continue
        alpha = round(FACE_ALPHA_MIN + (FACE_ALPHA_MAX - FACE_ALPHA_MIN) * facing)
        points = [(verts_2d[i][0] - left, verts_2d[i][1] - top) for i in face]
        pygame.draw.polygon(layer, (*color, alpha), points)
    screen.blit(layer, (left, top))


def point_segment_distance(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    closest_x, closest_y = ax + t * dx, ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def segments_intersect(p1, p2, p3, p4):
    def orientation(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = orientation(p3, p4, p1)
    d2 = orientation(p3, p4, p2)
    d3 = orientation(p1, p2, p3)
    d4 = orientation(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def point_in_polygon(point, poly):
    x, y = point
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def find_target_cube(cubes, mouse_pos, zoom):
    """Prefer a cube whose edge is close to the cursor; else a face it's over."""
    best_edge_cube = None
    best_edge_dist = None

    for cube in cubes:
        verts_2d = [project(v, zoom) for v in cube.transformed_vertices()]
        for a, b in CUBE_EDGES:
            dist = point_segment_distance(mouse_pos, verts_2d[a], verts_2d[b])
            if dist <= EDGE_HOVER_PX and (best_edge_dist is None or dist < best_edge_dist):
                best_edge_cube = cube
                best_edge_dist = dist

    if best_edge_cube is not None:
        return best_edge_cube

    best_face_cube = None
    best_face_depth = None
    for cube in cubes:
        verts_3d = cube.transformed_vertices()
        verts_2d = [project(v, zoom) for v in verts_3d]
        for face in CUBE_FACES:
            poly = [verts_2d[i] for i in face]
            if point_in_polygon(mouse_pos, poly):
                depth = sum(verts_3d[i][2] for i in face) / 4
                if best_face_depth is None or depth < best_face_depth:
                    best_face_cube = cube
                    best_face_depth = depth

    return best_face_cube


def make_random_cube():
    position = (
        random.uniform(-3.5, 3.5),
        random.uniform(-2.5, 2.5),
        random.uniform(-2.0, 2.0),
    )
    size = random.uniform(0.6, 1.4)
    return Cube(position=position, size=size)


class PasswordClipboard:
    """Puts the password on the clipboard and takes it off again after
    CLIPBOARD_CLEAR_MS (or on exit) - unless something else was copied since.

    On Windows the clipboard is written directly, tagged with the formats
    that keep it out of the clipboard history (Win+V), cloud clipboard sync
    and clipboard monitors. Elsewhere it falls back to pyperclip.
    """

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    # Windows honors these markers; the value 0 means "don't" for the latter two.
    PRIVACY_FORMATS = (
        "ExcludeClipboardContentFromMonitorProcessing",
        "CanIncludeInClipboardHistory",
        "CanUploadToCloudClipboard",
    )

    def __init__(self):
        self.win32 = sys.platform == "win32"
        self.clear_at = None
        self.copied_text = None
        self.sequence = None
        if self.win32:
            self.user32 = ctypes.windll.user32
            self.kernel32 = ctypes.windll.kernel32
            self.hwnd = ctypes.c_void_p(pygame.display.get_wm_info()["window"])
            self.kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            self.kernel32.GlobalAlloc.restype = ctypes.c_void_p
            self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            self.kernel32.GlobalLock.restype = ctypes.c_void_p
            self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            self.kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
            self.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            self.user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            self.user32.SetClipboardData.restype = ctypes.c_void_p
            self.user32.RegisterClipboardFormatW.restype = ctypes.c_uint
            self.user32.GetClipboardSequenceNumber.restype = ctypes.c_uint32

    def seconds_left(self):
        if self.clear_at is None:
            return None
        return max(0, (self.clear_at - pygame.time.get_ticks() + 999) // 1000)

    def copy(self, text):
        ok = self._win32_set(text) if self.win32 else self._fallback_set(text)
        if ok:
            self.copied_text = text
            self.clear_at = pygame.time.get_ticks() + CLIPBOARD_CLEAR_MS
            if self.win32:
                self.sequence = self.user32.GetClipboardSequenceNumber()
        return ok

    def update(self):
        if self.clear_at is not None and pygame.time.get_ticks() >= self.clear_at:
            self.clear_if_ours()

    def clear_if_ours(self):
        if self.clear_at is None:
            return
        if self.win32:
            # The sequence number changes whenever anyone writes the
            # clipboard, so an unchanged one means it still holds our copy.
            if self.user32.GetClipboardSequenceNumber() == self.sequence and self._open():
                self.user32.EmptyClipboard()
                self.user32.CloseClipboard()
        elif pyperclip is not None:
            try:
                if pyperclip.paste() == self.copied_text:
                    pyperclip.copy("")
            except Exception:
                pass
        self.clear_at = self.copied_text = self.sequence = None

    def _open(self):
        # Another program may hold the clipboard for a moment; retry briefly.
        for _ in range(10):
            if self.user32.OpenClipboard(self.hwnd):
                return True
            pygame.time.wait(10)
        return False

    def _global_data(self, data):
        handle = self.kernel32.GlobalAlloc(self.GMEM_MOVEABLE, len(data))
        if not handle:
            return None
        ctypes.memmove(self.kernel32.GlobalLock(handle), data, len(data))
        self.kernel32.GlobalUnlock(handle)
        return handle

    def _set_data(self, fmt, data):
        handle = self._global_data(data)
        if handle and not self.user32.SetClipboardData(fmt, handle):
            self.kernel32.GlobalFree(handle)  # only freed by us if Windows didn't take it
            return False
        return bool(handle)

    def _win32_set(self, text):
        if not self._open():
            return False
        try:
            self.user32.EmptyClipboard()
            if not self._set_data(self.CF_UNICODETEXT, text.encode("utf-16-le") + b"\0\0"):
                return False
            for name in self.PRIVACY_FORMATS:
                fmt = self.user32.RegisterClipboardFormatW(name)
                self._set_data(fmt, (0).to_bytes(4, "little"))
            return True
        finally:
            self.user32.CloseClipboard()

    def _fallback_set(self, text):
        if pyperclip is None:
            return False
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            return False


def password_strength(password):
    """(bits, label, color) for a password made of len(password) cube chars."""
    bits = len(password) * BITS_PER_CHAR
    level = [lvl for lvl in STRENGTH_LEVELS if bits >= lvl[0]][-1]
    return bits, level[1], level[2]


def generate_password(cubes):
    return "".join(cube.char() for cube in cubes)


def char_based_color(cube):
    """Hue derived from the cube's current password character - same char
    always maps to the same hue, so the color reflects what it contributes."""
    hue = CHARSET.index(cube.char()) / len(CHARSET)
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def save_screenshot(cubes, zoom):
    """Render the cube scene alone (no window chrome) and save it."""
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill(BG_COLOR)
    for cube in sorted(cubes, key=lambda c: c.position[2], reverse=True):
        draw_cube(surface, cube, zoom, char_based_color(cube))
    surface = surface.subsurface(view_rect())

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = f"realrap_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(SCREENSHOT_DIR, filename)
    pygame.image.save(surface, path)
    return path


def draw_edge(screen, rect, outer_tl, outer_br, inner_tl, inner_br):
    """A classic 2px 3D border: each ring has a top-left and a bottom-right color."""
    rect = pygame.Rect(rect)
    for ring, (tl, br) in enumerate(((outer_tl, outer_br), (inner_tl, inner_br))):
        r = rect.inflate(-2 * ring, -2 * ring)
        pygame.draw.line(screen, tl, r.topleft, (r.right - 2, r.top))
        pygame.draw.line(screen, tl, r.topleft, (r.left, r.bottom - 2))
        pygame.draw.line(screen, br, (r.left, r.bottom - 1), (r.right - 1, r.bottom - 1))
        pygame.draw.line(screen, br, (r.right - 1, r.top), (r.right - 1, r.bottom - 1))


def draw_raised(screen, rect, pressed=False):
    """A push button / window frame edge; sunken while pressed."""
    if pressed:
        draw_edge(screen, rect, WIN_DARK_SHADOW, WIN_LIGHT, WIN_SHADOW, WIN_FACE)
    else:
        draw_edge(screen, rect, WIN_FACE, WIN_DARK_SHADOW, WIN_LIGHT, WIN_SHADOW)


def draw_sunken(screen, rect):
    """The edge around text boxes and client areas."""
    draw_edge(screen, rect, WIN_SHADOW, WIN_LIGHT, WIN_DARK_SHADOW, WIN_FACE)


@functools.lru_cache(maxsize=8)
def horizontal_gradient(size, left_color, right_color):
    width, height = size
    strip = pygame.Surface((width, 1))
    for x in range(width):
        f = x / max(1, width - 1)
        strip.set_at((x, 0), [round(a + (b - a) * f) for a, b in zip(left_color, right_color)])
    return pygame.transform.scale(strip, size)


def draw_horizontal_gradient(screen, rect, left_color, right_color):
    rect = pygame.Rect(rect)
    screen.blit(horizontal_gradient(rect.size, left_color, right_color), rect)


def caption_button_rects():
    """Minimize, maximize and close buttons at the right of the title bar."""
    w, h = CAPTION_BUTTON_SIZE
    y = FRAME + (TITLE_HEIGHT - h) // 2
    close = pygame.Rect(WIDTH - FRAME - 2 - w, y, w, h)
    maximize = close.move(-w - 2, 0)
    minimize = maximize.move(-w, 0)
    return {"min": minimize, "max": maximize, "close": close}


def draw_caption_button(screen, rect, kind, pressed, maximized):
    pygame.draw.rect(screen, WIN_FACE, rect)
    draw_raised(screen, rect, pressed)

    x, y = rect.x + 4 + pressed, rect.y + 3 + pressed
    if kind == "min":
        pygame.draw.rect(screen, WIN_TEXT, (x, y + 6, 6, 2))
    elif kind == "max" and not maximized:
        pygame.draw.rect(screen, WIN_TEXT, (x - 1, y - 1, 9, 8), width=1)
        pygame.draw.line(screen, WIN_TEXT, (x - 1, y), (x + 7, y))
    elif kind == "max":
        for ox, oy in ((2, -1), (0, 2)):
            box = pygame.Rect(x + ox - 1, y + oy, 6, 5)
            pygame.draw.rect(screen, WIN_FACE, box)
            pygame.draw.rect(screen, WIN_TEXT, box, width=1)
            pygame.draw.line(screen, WIN_TEXT, (box.left, box.top + 1), (box.right - 1, box.top + 1))
    else:
        for i in range(2):  # a 2px-wide X, like the classic close glyph
            pygame.draw.line(screen, WIN_TEXT, (x + i, y), (x + 5 + i, y + 6))
            pygame.draw.line(screen, WIN_TEXT, (x + 5 + i, y), (x + i, y + 6))


def draw_title_icon(screen, x, y):
    """A tiny wireframe cube as the window icon."""
    front = pygame.Rect(x, y + 4, 10, 10)
    back = front.move(4, -4)
    pygame.draw.rect(screen, UI_COLOR, back, width=1)
    pygame.draw.rect(screen, UI_COLOR, front, width=1)
    for a, b in ((front.topleft, back.topleft), (front.topright, back.topright),
                 (front.bottomright, back.bottomright)):
        pygame.draw.line(screen, UI_COLOR, a, b)


def draw_window_frame(screen, title_font, title, active, mouse_pos, pressed_caption, maximized):
    whole = pygame.Rect(0, 0, WIDTH, HEIGHT)
    for strip in (
        (0, 0, WIDTH, VIEW_TOP),
        (0, 0, FRAME, HEIGHT),
        (WIDTH - FRAME, 0, FRAME, HEIGHT),
        (0, HEIGHT - FRAME, WIDTH, FRAME),
    ):
        pygame.draw.rect(screen, WIN_FACE, strip)
    draw_raised(screen, whole)
    draw_sunken(screen, view_rect())

    title_rect = pygame.Rect(FRAME, FRAME, WIDTH - 2 * FRAME, TITLE_HEIGHT)
    draw_horizontal_gradient(screen, title_rect, *(WIN_TITLE_ACTIVE if active else WIN_TITLE_INACTIVE))
    draw_title_icon(screen, title_rect.x + 3, title_rect.y + 1)
    text = title_font.render(title, True, WIN_LIGHT if active else WIN_TITLE_TEXT_INACTIVE)
    screen.blit(text, (title_rect.x + 22, title_rect.centery - text.get_height() // 2))

    for kind, rect in caption_button_rects().items():
        pressed = pressed_caption == kind and rect.collidepoint(mouse_pos)
        draw_caption_button(screen, rect, kind, pressed, maximized)


def draw_button(screen, font, rect, label, pressed):
    pygame.draw.rect(screen, WIN_FACE, rect)
    draw_raised(screen, rect, pressed)
    text = font.render(label, True, WIN_TEXT)
    center = (rect.centerx + 1, rect.centery + 1) if pressed else rect.center
    screen.blit(text, text.get_rect(center=center))


def draw_strength(screen, font, rect, password):
    """A segmented classic progress bar plus "Good (77 bits)"."""
    meter = pygame.Rect(rect.left, rect.top, 58, rect.height)
    pygame.draw.rect(screen, WIN_LIGHT, meter)
    draw_sunken(screen, meter)
    if not password:
        text = font.render("No password", True, WIN_GRAY_TEXT)
    else:
        bits, label, color = password_strength(password)
        inner = meter.inflate(-6, -6)
        filled = round(inner.width * min(1.0, bits / STRENGTH_FULL_BITS))
        for x in range(inner.left, inner.left + filled, 7):
            pygame.draw.rect(screen, color, (x, inner.top, min(5, inner.left + filled - x), inner.height))
        text = font.render(f"{label} ({round(bits)} bits)", True, color)
    screen.blit(text, (meter.right + 6, rect.centery - text.get_height() // 2))


def draw_bottom_bar(
    screen,
    ui_font,
    password_font,
    password,
    char_colors,
    buttons,
    show_password,
    copy_flash_until,
    clipboard_seconds_left,
    save_flash_until,
    mouse_pos,
    mouse_down,
):
    bar = pygame.Rect(FRAME, VIEW_HEIGHT, WIDTH - 2 * FRAME, BAR_HEIGHT)
    pygame.draw.rect(screen, WIN_FACE, bar)

    label = ui_font.render("Password:", True, WIN_TEXT)
    screen.blit(label, (bar.left + 8, bar.centery - label.get_height() // 2))

    textbox = pygame.Rect(0, 0, 0, 23)
    textbox.left = bar.left + 16 + label.get_width()
    textbox.width = max(40, buttons["show"].left - 4 - textbox.left)
    textbox.centery = bar.centery
    pygame.draw.rect(screen, WIN_LIGHT, textbox)
    draw_sunken(screen, textbox)

    inner = textbox.inflate(-8, -4)
    screen.set_clip(inner)
    if not password:
        placeholder = ui_font.render("(create cubes to generate a password)", True, WIN_GRAY_TEXT)
        screen.blit(placeholder, (inner.left, inner.centery - placeholder.get_height() // 2))
    else:
        # The full-brightness cube colors are hard to read on white, so the
        # text uses a darker shade of the same hue. Hidden, each char is a
        # "*" that still carries its cube's color.
        glyphs = [
            password_font.render(ch if show_password else "*", True, [c * 7 // 10 for c in color])
            for ch, color in zip(password, char_colors)
        ]
        total = sum(g.get_width() for g in glyphs)
        x = inner.left if total <= inner.width else inner.right - total  # keep the newest chars visible
        for glyph in glyphs:
            screen.blit(glyph, (x, inner.centery - glyph.get_height() // 2))
            x += glyph.get_width()
    screen.set_clip(None)

    draw_strength(screen, ui_font, buttons["strength"], password)

    now = pygame.time.get_ticks()
    if now < copy_flash_until:
        copy_label = "Copied!"
    elif clipboard_seconds_left is not None:
        copy_label = f"Copy ({clipboard_seconds_left}s)"  # countdown until it's wiped
    else:
        copy_label = "Copy"
    for name, label_text in (
        ("show", "Hide" if show_password else "Show"),
        ("save", "Saved!" if now < save_flash_until else "Save Image"),
        ("copy", copy_label),
    ):
        rect = buttons[name]
        draw_button(screen, ui_font, rect, label_text, mouse_down and rect.collidepoint(mouse_pos))


def enable_window_glass():
    """Let DWM composite the window using its pixels' alpha byte (Windows only).

    Fully transparent pixels then show the desktop behind, but stay part of
    the window for hit-testing, so clicks on them still reach the app.
    """
    if sys.platform != "win32":
        return False

    class DWM_BLURBEHIND(ctypes.Structure):
        _fields_ = [
            ("dwFlags", ctypes.c_uint32),
            ("fEnable", ctypes.c_int),
            ("hRgnBlur", ctypes.c_void_p),
            ("fTransitionOnMaximized", ctypes.c_int),
        ]

    DWM_BB_ENABLE = 0x1
    DWM_BB_BLURREGION = 0x2
    gdi32 = ctypes.windll.gdi32
    gdi32.CreateRectRgn.restype = ctypes.c_void_p
    hwnd = pygame.display.get_wm_info()["window"]
    # An empty blur region turns on per-pixel alpha without actually blurring
    # anything (same trick GLFW uses for transparent framebuffers).
    region = gdi32.CreateRectRgn(0, 0, -1, -1)
    blur = DWM_BLURBEHIND(DWM_BB_ENABLE | DWM_BB_BLURREGION, 1, region, 0)
    ok = ctypes.windll.dwmapi.DwmEnableBlurBehindWindow(ctypes.c_void_p(hwnd), ctypes.byref(blur)) == 0
    gdi32.DeleteObject(ctypes.c_void_p(region))
    return ok


def make_canvas(window):
    """An offscreen surface laid out like the window but with a real alpha byte."""
    r, g, b, _ = window.get_masks()
    return pygame.Surface(window.get_size(), pygame.SRCALPHA, 32, (r, g, b, 0xFF000000))


def present(window, canvas):
    """Copy the canvas into the window as raw pixels, keeping its alpha byte
    (a normal blit would drop it, since the window surface has no alpha).
    DWM expects premultiplied alpha, otherwise the fully transparent pixels
    around anti-aliased text would still glow in the text's color."""
    if window.get_pitch() == canvas.get_pitch() and window.get_size() == canvas.get_size():
        window.get_buffer().write(canvas.premul_alpha().get_buffer().raw)
    else:
        window.blit(canvas, (0, 0))
    pygame.display.flip()


def set_window_size(width, height):
    global WIDTH, HEIGHT, VIEW_HEIGHT
    WIDTH, HEIGHT = max(MIN_WIDTH, width), max(MIN_HEIGHT, height)
    VIEW_HEIGHT = HEIGHT - FRAME - BAR_HEIGHT


def make_button_rects():
    """Bottom bar layout, right to left: Copy, Save Image, strength, Show."""
    y = VIEW_HEIGHT + (BAR_HEIGHT - 23) // 2
    copy = pygame.Rect(WIDTH - FRAME - 8 - 80, y, 80, 23)
    save = pygame.Rect(copy.left - 6 - 90, y, 90, 23)
    strength = pygame.Rect(save.left - 14 - 175, y, 175, 23)
    show = pygame.Rect(strength.left - 10 - 50, y, 50, 23)
    return {"copy": copy, "save": save, "strength": strength, "show": show}


def hit_test(pos, maximized):
    """Which part of the window `pos` is over: a resize edge ("t", "bl", ...),
    a caption button ("min", "max", "close"), "caption", "chrome" or "view"."""
    x, y = pos
    if not maximized:
        left, right = x < RESIZE_GRIP, x >= WIDTH - RESIZE_GRIP
        top, bottom = y < RESIZE_GRIP, y >= HEIGHT - RESIZE_GRIP
        if left or right:
            top, bottom = top or y < RESIZE_CORNER, bottom or y >= HEIGHT - RESIZE_CORNER
        if top or bottom:
            left, right = left or x < RESIZE_CORNER, right or x >= WIDTH - RESIZE_CORNER
        edges = ("t" if top else "") + ("b" if bottom else "") + ("l" if left else "") + ("r" if right else "")
        if edges:
            return edges
    for kind, rect in caption_button_rects().items():
        if rect.collidepoint(pos):
            return kind
    if y < VIEW_TOP:
        return "caption"
    if view_rect().collidepoint(pos):
        return "view"
    return "chrome"


RESIZE_CURSORS = {
    "l": pygame.SYSTEM_CURSOR_SIZEWE, "r": pygame.SYSTEM_CURSOR_SIZEWE,
    "t": pygame.SYSTEM_CURSOR_SIZENS, "b": pygame.SYSTEM_CURSOR_SIZENS,
    "tl": pygame.SYSTEM_CURSOR_SIZENWSE, "br": pygame.SYSTEM_CURSOR_SIZENWSE,
    "tr": pygame.SYSTEM_CURSOR_SIZENESW, "bl": pygame.SYSTEM_CURSOR_SIZENESW,
}


class NativeWindow:
    """Moves, resizes and maximizes the borderless window through Win32,
    since there is no native frame to do it. A no-op off Windows."""

    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010

    def __init__(self):
        self.enabled = sys.platform == "win32"
        self.drag = None
        self.restore_rect = None  # set while maximized
        if self.enabled:
            self.user32 = ctypes.windll.user32
            self.hwnd = ctypes.c_void_p(pygame.display.get_wm_info()["window"])

    @property
    def maximized(self):
        return self.restore_rect is not None

    def _cursor(self):
        point = ctypes.wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def _rect(self):
        rect = ctypes.wintypes.RECT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom

    def _set_rect(self, left, top, right, bottom, move_only=False):
        flags = self.SWP_NOSIZE | self.SWP_NOZORDER | self.SWP_NOACTIVATE
        self.user32.SetWindowPos(self.hwnd, None, left, top, 0, 0, flags)
        # The size goes through SDL: it doesn't notice a borderless window
        # being resized behind its back, and would keep drawing at the old size.
        if not move_only and (right - left, bottom - top) != (WIDTH, HEIGHT):
            set_window_size(right - left, bottom - top)
            pygame.display.set_mode((WIDTH, HEIGHT), WINDOW_FLAGS)

    def start_drag(self, mode):
        """mode is "move" or a resize edge string from hit_test()."""
        if self.enabled:
            self.drag = (mode, self._cursor(), self._rect())

    def update_drag(self):
        if self.drag is None:
            return
        mode, (start_x, start_y), (left, top, right, bottom) = self.drag
        cursor_x, cursor_y = self._cursor()
        dx, dy = cursor_x - start_x, cursor_y - start_y
        if mode == "move":
            self._set_rect(left + dx, top + dy, right + dx, bottom + dy, move_only=True)
            return
        if "l" in mode:
            left = min(left + dx, right - MIN_WIDTH)
        if "r" in mode:
            right = max(right + dx, left + MIN_WIDTH)
        if "t" in mode:
            top = min(top + dy, bottom - MIN_HEIGHT)
        if "b" in mode:
            bottom = max(bottom + dy, top + MIN_HEIGHT)
        self._set_rect(left, top, right, bottom)

    def end_drag(self):
        self.drag = None

    def toggle_maximize(self):
        """Fill the monitor's work area (so the taskbar stays visible)."""
        if not self.enabled:
            return
        if self.maximized:
            self._set_rect(*self.restore_rect)
            self.restore_rect = None
            return

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint32),
                ("rcMonitor", ctypes.wintypes.RECT),
                ("rcWork", ctypes.wintypes.RECT),
                ("dwFlags", ctypes.c_uint32),
            ]

        MONITOR_DEFAULTTONEAREST = 2
        self.user32.MonitorFromWindow.restype = ctypes.c_void_p
        monitor = self.user32.MonitorFromWindow(self.hwnd, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        self.user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info))
        self.restore_rect = self._rect()
        work = info.rcWork
        self._set_rect(work.left, work.top, work.right, work.bottom)


def main():
    pygame.init()
    # The title bar is ours, so the window must start fully on screen.
    desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
    set_window_size(min(WIDTH, desktop_w * 9 // 10), min(HEIGHT, desktop_h * 9 // 10))
    window = pygame.display.set_mode((WIDTH, HEIGHT), WINDOW_FLAGS)
    transparent = enable_window_glass()
    screen = make_canvas(window)
    pygame.display.set_caption(WINDOW_TITLE)
    if os.path.exists(ICON_PATH):
        pygame.display.set_icon(pygame.image.load(ICON_PATH))
    clock = pygame.time.Clock()
    native = NativeWindow()

    ui_font = pygame.font.SysFont("tahoma", 13)
    title_font = pygame.font.SysFont("tahoma", 13, bold=True)
    password_font = pygame.font.SysFont("lucidaconsole,consolas", 16)

    buttons = make_button_rects()
    clipboard = PasswordClipboard()
    show_password = False

    cubes = []
    zoom = 1.0
    copy_flash_until = 0
    save_flash_until = 0

    creating_cube = False
    new_cube_center = (0.0, 0.0, 0.0)
    new_cube_start_screen = (0, 0)
    new_cube_size = MIN_CUBE_SIZE

    left_press_pos = None
    left_press_target = None
    left_dragged = False

    pressed_caption = None
    last_caption_click = 0
    current_cursor = None

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                set_window_size(event.w, event.h)
                if (WIDTH, HEIGHT) != (event.w, event.h):
                    pygame.display.set_mode((WIDTH, HEIGHT), WINDOW_FLAGS)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_n:
                    cubes.append(make_random_cube())
                elif event.key == pygame.K_t:
                    transparent = not transparent
                elif event.key == pygame.K_c:
                    cubes = []
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                region = hit_test(event.pos, native.maximized)
                if event.button == 1:
                    if region in RESIZE_CURSORS:
                        native.start_drag(region)
                    elif region in ("min", "max", "close"):
                        pressed_caption = region
                    elif region == "caption":
                        now = pygame.time.get_ticks()
                        if now - last_caption_click < DOUBLE_CLICK_MS:
                            native.toggle_maximize()
                        elif not native.maximized:
                            native.start_drag("move")
                        last_caption_click = now
                    elif buttons["copy"].collidepoint(mx, my):
                        password = generate_password(cubes)
                        if password and clipboard.copy(password):
                            copy_flash_until = pygame.time.get_ticks() + 900
                    elif buttons["show"].collidepoint(mx, my):
                        show_password = not show_password
                    elif buttons["save"].collidepoint(mx, my):
                        save_screenshot(cubes, zoom)
                        save_flash_until = pygame.time.get_ticks() + 900
                    elif region == "view":
                        left_press_pos = event.pos
                        left_press_target = find_target_cube(cubes, event.pos, zoom)
                        left_dragged = False
                elif event.button == 3 and region == "view":
                    creating_cube = True
                    new_cube_start_screen = event.pos
                    new_cube_center = unproject_to_plane(event.pos, zoom)
                    new_cube_size = MIN_CUBE_SIZE
                elif event.button == 4:
                    zoom *= 1.1
                elif event.button == 5:
                    zoom /= 1.1
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    native.end_drag()
                    # Caption buttons act on release, like real ones.
                    if pressed_caption is not None and hit_test(event.pos, native.maximized) == pressed_caption:
                        if pressed_caption == "close":
                            running = False
                        elif pressed_caption == "max":
                            native.toggle_maximize()
                        else:
                            pygame.display.iconify()
                    pressed_caption = None
                if event.button == 1 and left_press_target is not None:
                    if not left_dragged and left_press_target in cubes:
                        cubes.remove(left_press_target)
                    left_press_pos = None
                    left_press_target = None
                    left_dragged = False
                elif event.button == 3 and creating_cube:
                    cubes.append(Cube(position=new_cube_center, size=new_cube_size))
                    creating_cube = False
            elif event.type == pygame.MOUSEMOTION:
                if left_press_target is not None:
                    sx, sy = event.pos
                    lx, ly = left_press_pos
                    if math.hypot(sx - lx, sy - ly) > CLICK_MOVE_THRESHOLD_PX:
                        left_dragged = True
                    dx, dy = event.rel
                    left_press_target.spin(dy * ROTATE_PIXEL_SENSITIVITY, dx * ROTATE_PIXEL_SENSITIVITY)
                elif left_press_pos is not None and event.buttons[0]:
                    # Started the drag on empty space: sweep-rotate every cube
                    # whose edge the drag path crosses this step.
                    prev_pos = (event.pos[0] - event.rel[0], event.pos[1] - event.rel[1])
                    cur_pos = event.pos
                    dx, dy = event.rel
                    for cube in cubes:
                        verts_2d = [project(v, zoom) for v in cube.transformed_vertices()]
                        for a, b in CUBE_EDGES:
                            if segments_intersect(prev_pos, cur_pos, verts_2d[a], verts_2d[b]):
                                cube.spin(dy * ROTATE_PIXEL_SENSITIVITY, dx * ROTATE_PIXEL_SENSITIVITY)
                                break
                if creating_cube:
                    sx, sy = event.pos
                    lx, ly = new_cube_start_screen
                    pixel_dist = math.hypot(sx - lx, sy - ly)
                    new_cube_size = max(MIN_CUBE_SIZE, min(MAX_CUBE_SIZE, pixel_dist / (BASE_SCALE * zoom)))

        native.update_drag()

        window = pygame.display.get_surface()
        if screen.get_size() != window.get_size():
            screen = make_canvas(window)
            buttons = make_button_rects()

        clipboard.update()

        mouse_pos = pygame.mouse.get_pos()
        hover_region = hit_test(mouse_pos, native.maximized)
        hover_target = None
        if hover_region == "view":
            hover_target = find_target_cube(cubes, mouse_pos, zoom)

        cursor = RESIZE_CURSORS.get(native.drag[0] if native.drag else hover_region, pygame.SYSTEM_CURSOR_ARROW)
        if cursor != current_cursor:
            pygame.mouse.set_system_cursor(cursor)
            current_cursor = cursor

        keys = pygame.key.get_pressed()
        key_spin_x = 0.0
        key_spin_y = 0.0
        if keys[pygame.K_UP]:
            key_spin_x -= KEY_ROTATE_SPEED
        if keys[pygame.K_DOWN]:
            key_spin_x += KEY_ROTATE_SPEED
        if keys[pygame.K_LEFT]:
            key_spin_y -= KEY_ROTATE_SPEED
        if keys[pygame.K_RIGHT]:
            key_spin_y += KEY_ROTATE_SPEED
        if hover_target is not None and (key_spin_x or key_spin_y):
            hover_target.update(dt, extra_x=key_spin_x, extra_y=key_spin_y)

        screen.fill((*BG_COLOR, 0) if transparent else BG_COLOR)

        cube_colors = {cube: char_based_color(cube) for cube in cubes}

        for cube in sorted(cubes, key=lambda c: c.position[2], reverse=True):
            draw_cube(screen, cube, zoom, cube_colors[cube])

        if creating_cube:
            preview_cube = Cube(position=new_cube_center, size=new_cube_size)
            draw_cube(screen, preview_cube, zoom, PREVIEW_COLOR, filled=False)

        password = generate_password(cubes)
        char_colors = [cube_colors[cube] for cube in cubes]
        draw_window_frame(
            screen,
            title_font,
            WINDOW_TITLE,
            pygame.key.get_focused(),
            mouse_pos,
            pressed_caption,
            native.maximized,
        )
        draw_bottom_bar(
            screen,
            ui_font,
            password_font,
            password,
            char_colors,
            buttons,
            show_password,
            copy_flash_until,
            clipboard.seconds_left(),
            save_flash_until,
            mouse_pos,
            pygame.mouse.get_pressed()[0],
        )

        present(window, screen)

    clipboard.clear_if_ours()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
