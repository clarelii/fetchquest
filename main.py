# /// script
# dependencies = [
#   "pygame-ce",
#   "pillow",
# ]
# ///

import asyncio
import os
import random
import math
import sys
import pygame
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))

VIEW_W, VIEW_H = 300, 170
SCALE = 4
TILE = 16
FPS = 60
GRAVITY = 780
MAX_FALL = 280
RUN_SPEED = 92
JUMP_VEL = -318
COYOTE = 0.09
JUMP_BUFFER = 0.12

LEVEL_WIDTH = 480
LEVEL = (
    ["." * LEVEL_WIDTH for _ in range(11)]
    + ["S" + "." * (LEVEL_WIDTH - 1)]
    + ["#" * LEVEL_WIDTH for _ in range(4)]
)

def asset(*parts):

    return os.path.join(ROOT, *parts)

def load_gif(path):

    gif = Image.open(path)
    frames = []
    durations = []

    for i in range(gif.n_frames):

        gif.seek(i)
        durations.append(max(gif.info.get("duration", 80) / 1000.0, 0.04))
        frame = gif.convert("RGBA")
        pixels = frame.load()

        for y in range(frame.height):

            for x in range(frame.width):

                r, g, b, a = pixels[x, y]

                if a < 8 or r + g + b < 12:

                    pixels[x, y] = (0, 0, 0, 0)

        surf = pygame.image.fromstring(frame.tobytes(), frame.size, "RGBA")

        frames.append(surf.convert_alpha())

    return frames, durations

def load_image(path):

    return pygame.image.load(path).convert_alpha()

def load_heartcard(path):
    source = Image.open(path).convert("RGBA")
    values = []
    for r, g, b, a in source.getdata():
        lum = round(0.299 * r + 0.587 * g + 0.114 * b)
        shade = 255 if lum >= 222 else max(0, min(255, round(lum * 0.40)))
        values.append((shade, shade, shade, a))
    source.putdata(values)
    return pygame.image.fromstring(source.tobytes(), source.size, "RGBA").convert_alpha()

def load_tinted_layer(path, color):
    """tint bg"""
    image = Image.open(path).convert("RGBA")
    tinted = Image.new("RGBA", image.size, (*color, 0))
    tinted.putalpha(image.getchannel("A"))
    return pygame.image.fromstring(tinted.tobytes(), tinted.size, "RGBA").convert_alpha()

def load_white_tileset(path):

    im = Image.open(path).convert("RGBA")

    pixels = im.load()

    for y in range(im.height):

        for x in range(im.width):

            r, g, b, a = pixels[x, y]

            if a > 10 and r + g + b < 400:

                pixels[x, y] = (236, 236, 232, 255)

            else:

                pixels[x, y] = (0, 0, 0, 0)

    return pygame.image.fromstring(im.tobytes(), im.size, "RGBA").convert_alpha()

class Anim:

    def __init__(self, frames, durations, loop=True):
        self.frames = frames
        self.durations = durations
        self.loop = loop
        self.time = 0.0
        self.index = 0
        self.done = False

    def reset(self):
        self.time = 0.0
        self.index = 0
        self.done = False

    def update(self, dt):

        if self.done:
            return

        self.time += dt

        while self.time >= self.durations[self.index]:
            self.time -= self.durations[self.index]
            self.index += 1

            if self.index >= len(self.frames):

                if self.loop:
                    self.index = 0

                else:
                    self.index = len(self.frames) - 1
                    self.done = True
                    break

    def image(self):

        return self.frames[self.index]

class Camera:

    def __init__(self, width, height):
        self.x = 0.0
        self.y = float(max(0, height - VIEW_H - 22))
        self.width = width
        self.height = height

    def follow(self, rect, dt):
        tx = rect.centerx - VIEW_W * 0.42
        self.x += (tx - self.x) * min(1.0, dt * 8)
        self.x = max(0, min(self.x, self.width - VIEW_W))

class World:

    def __init__(self, tileset):

        width = max(len(row) for row in LEVEL)

        self.rows = [list(row.ljust(width, ".")) for row in LEVEL]
        self.h = len(self.rows)
        self.w = width
        self.pixel_w = self.w * TILE
        self.pixel_h = self.h * TILE
        self.tileset = tileset
        self.tile_cache = {}
        self.solids = set("#B=")
        self.spawn = (TILE * 2, TILE * 10)
        self.goal = pygame.Rect(0, 0, TILE, TILE * 2)
        self.checkpoints = []
        self.decor = []
        self.water = []
        self.platforms = []
        self.blocks = []
        self.enemies = []
        self._scan()

    def ground_y_at(self, x):
        """Continuous rolling terrain with gentle slopes and no holes."""
        x = max(0, min(self.pixel_w - 1, x))
        ramp = min(1.0, max(0.0, (x - 130) / 230.0))
        return 192 - ramp * (11 * math.sin(x / 115.0) + 10 * math.sin(x / 255.0))

    def at(self, x, y):

        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return "#"

        return self.rows[y][x]

    def _scan(self):

        for y, row in enumerate(self.rows):

            for x, ch in enumerate(row):

                r = pygame.Rect(x * TILE, y * TILE, TILE, TILE)

                if ch == "S":

                    self.spawn = (r.x + 18, r.y + 2)
                    self.checkpoints.append(pygame.Rect(r.x, r.y, TILE, TILE * 2))
                    self.rows[y][x] = "."

                elif ch == "F":

                    self.goal = pygame.Rect(r.x, r.y - TILE, TILE, TILE * 2)
                    self.checkpoints.append(pygame.Rect(r.x, r.y, TILE, TILE * 2))
                    self.rows[y][x] = "."

                elif ch == "E":

                    pass
                    self.rows[y][x] = "."

                elif ch == "d":
                    self.decor.append((x, y))

                elif ch == "~":
                    self.water.append(r)

                elif ch == "=":
                    self.platforms.append(r)

                elif ch in "#B":
                    self.blocks.append(r)

    def tile_image(self, col, row):

        key = (col, row)

        if key not in self.tile_cache:
            self.tile_cache[key] = self.tileset.subsurface(
                pygame.Rect(col * TILE, row * TILE, TILE, TILE)
            )

        return self.tile_cache[key]

    def autotile(self, x, y):
        ch = self.at(x, y)
        if ch == "~":

            above = self.at(x, y - 1)
            variant = (x + y) % 2
            if above != "~":

                return (9 + variant, 2)
            return (9 + variant, 3)

        if ch == "d":
            return (x % 4, 3)

        if ch == "=":
            left = self.at(x - 1, y) == "="
            right = self.at(x + 1, y) == "="

            if left and right:
                return (5 + (x % 2), 0)

            if right and not left:
                return (4, 0)

            if left and not right:
                return (7, 0)

            return (8, 0)

        if ch == "B":

            up = self.at(x, y - 1) == "B"
            down = self.at(x, y + 1) == "B"
            left = self.at(x - 1, y) == "B"
            right = self.at(x + 1, y) == "B"

            if not up:
                row = 0
            elif not down:
                row = 2
            else:
                row = 1

            if not left and right:
                col = 4
            elif left and not right:
                col = 7
            elif not left and not right:
                col = 8
            else:
                col = 5 + (x % 2)

            return (col, row)

        if ch == "#":

            up = self.at(x, y - 1) == "#"
            down = self.at(x, y + 1) in "#B"
            left = self.at(x - 1, y) == "#"
            right = self.at(x + 1, y) == "#"

            if not up:
                row = 0

            elif not down:
                row = 2

            else:
                row = 1

            if not left and right:
                col = 0

            elif left and not right:
                col = 2

            elif not left and not right:
                col = 3

            else:
                col = 1

            return (col, row)

        return None

    def draw(self, surf, cam):

        x0 = max(0, int(cam.x) // TILE - 1)
        y0 = max(0, int(cam.y) // TILE - 1)
        x1 = min(self.w, x0 + VIEW_W // TILE + 3)
        y1 = min(self.h, y0 + VIEW_H // TILE + 3)

        for y in range(y0, y1):

            for x in range(x0, x1):
                if y >= 12:
                    continue
                spec = self.autotile(x, y)

                if not spec:
                    continue

                img = self.tile_image(*spec)

                surf.blit(img, (x * TILE - int(cam.x), y * TILE - int(cam.y)))

                if self.at(x, y) == "." and self.at(x, y + 1) == "#" and (x + y) % 5 == 0:

                    tuft = self.tile_image(x % 4, 3)

                    surf.blit(tuft, (x * TILE - int(cam.x), y * TILE - int(cam.y)))

        ground_color = (236, 236, 232)
        surface_color = (216, 216, 210)
        first = max(0, int(cam.x) - 2)
        last = min(self.pixel_w, int(cam.x) + VIEW_W + 3)
        for wx in range(first, last):
            top = round(self.ground_y_at(wx) - cam.y)
            sx = wx - int(cam.x)
            if top < VIEW_H:
                pygame.draw.line(surf, ground_color,
                                 (sx, max(0, top)), (sx, VIEW_H - 1))
                if 0 <= sx < VIEW_W and 0 <= top < VIEW_H:
                    surf.set_at((sx, top), surface_color)

    def solid_rects_near(self, rect):

        x0 = max(0, rect.left // TILE - 1)
        y0 = max(0, rect.top // TILE - 1)
        x1 = min(self.w, rect.right // TILE + 2)
        y1 = min(self.h, rect.bottom // TILE + 2)
        out = []

        for y in range(y0, y1):

            for x in range(x0, x1):

                ch = self.at(x, y)

                if ch in "#B":
                    out.append((pygame.Rect(x * TILE, y * TILE, TILE, TILE), ch))
                elif ch == "=":
                    out.append((pygame.Rect(x * TILE, y * TILE, TILE, 6), ch))
        return out

    def in_water(self, rect):

        probe = pygame.Rect(rect.x + 2, rect.centery, rect.w - 4, rect.h // 2)

        for pool in self.water:
            if probe.colliderect(pool):
                return True

        return False

class Enemy:

    def __init__(self, x, y):

        self.rect = pygame.Rect(x + 2, y + 6, 12, 10)
        self.vx = 28
        self.alive = True
        self.flash = 0.0

    def update(self, dt, world):

        if not self.alive:
            return

        self.rect.x += self.vx * dt

        hits = world.solid_rects_near(self.rect)

        for solid, ch in hits:

            if ch == "=":
                continue

            if self.rect.colliderect(solid):

                if self.vx > 0:
                    self.rect.right = solid.left

                else:
                    self.rect.left = solid.right

                self.vx *= -1

        foot = pygame.Rect(

            self.rect.left + (10 if self.vx > 0 else -4),
            self.rect.bottom,
            4,
            4,
        )

        grounded = False

        for solid, _ch in world.solid_rects_near(foot):

            if foot.colliderect(solid):
                grounded = True
                break

        if not grounded:

            self.vx *= -1
            self.rect.x += self.vx * dt

        self.flash = max(0.0, self.flash - dt)

    def draw(self, surf, cam):

        if not self.alive:
            return

        r = pygame.Rect(
            self.rect.x - int(cam.x),
            self.rect.y - int(cam.y),
            self.rect.w,
            self.rect.h,
        )

        color = (255, 255, 255) if self.flash > 0 else (188, 188, 188)

        pygame.draw.rect(surf, color, r, border_radius=3)

        eye_y = r.y + 3

        if self.vx >= 0:

            pygame.draw.rect(surf, (20, 20, 20), (r.x + 7, eye_y, 2, 2))
            pygame.draw.rect(surf, (20, 20, 20), (r.x + 10, eye_y, 2, 2))

        else:
            pygame.draw.rect(surf, (20, 20, 20), (r.x + 1, eye_y, 2, 2))
            pygame.draw.rect(surf, (20, 20, 20), (r.x + 4, eye_y, 2, 2))

class Player:

    def __init__(self, anims, spawn):

        self.anims = anims
        self.state = "idle"
        self.facing = 1
        self.rect = pygame.Rect(spawn[0], spawn[1], 8, 14)
        self.x = float(spawn[0])
        self.y = float(spawn[1])
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.coyote = 0.0
        self.buffer = 0.0
        self.attack_hit = None
        self.invuln = 0.0
        self.hp = 3
        self.spawn = spawn
        self.won = False
        self.dead = False
        self.turn_from = 1
        self.set_state("idle")

    def set_state(self, name):

        if self.state == name and name not in ("attack1", "attack2", "turn"):

            return

        self.state = name

        self.anims[name].reset()

    def current(self):

        return self.anims[self.state]

    def attack_box(self):

        if self.state == "attack1":

            w, h = 22, 16

        elif self.state == "attack2":

            w, h = 28, 20

        else:

            return None

        if self.facing > 0:

            return pygame.Rect(self.rect.right - 2, self.rect.y + 2, w, h)

        return pygame.Rect(self.rect.left - w + 2, self.rect.y + 2, w, h)

    def hurt(self, source_x):

        if self.invuln > 0 or self.dead or self.won:

            return

        self.hp -= 1
        self.invuln = 1.1
        self.vy = -120
        self.vx = 90 if self.rect.centerx < source_x else -90

        if self.hp <= 0:

            self.dead = True

    def respawn(self):

        self.x, self.y = float(self.spawn[0]), float(self.spawn[1])
        self.rect.topleft = (int(self.x), int(self.y))
        self.vx = 0
        self.vy = 0
        self.hp = 3
        self.dead = False
        self.invuln = 1.0
        self.set_state("idle")

    def update(self, dt, keys, world, enemies, attack_clicked=False):

        if self.won:
            self.set_state("idle")
            self.current().update(dt)
            return

        if self.dead:
            return

        self.invuln = max(0.0, self.invuln - dt)
        attacking = self.state in ("attack1", "attack2") and not self.current().done
        turning = self.state == "turn" and not self.current().done

        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        jump = keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]

        if jump:
            self.buffer = JUMP_BUFFER
        else:
            self.buffer = max(0.0, self.buffer - dt)

        if self.on_ground:
            self.coyote = COYOTE
        else:
            self.coyote = max(0.0, self.coyote - dt)

        ax = 0

        if not attacking and not turning:

            if left and not right:
                ax = -1
            elif right and not left:
                ax = 1

            if ax != 0 and ax != self.facing and self.on_ground and abs(self.vx) > 20:
                self.turn_from = self.facing
                self.facing = ax
                self.set_state("turn")
                turning = True

            elif ax != 0:
                self.facing = ax

        if turning:
            self.vx *= 0.2
        elif attacking:
            self.vx *= 0.45
        else:
            target = ax * RUN_SPEED
            self.vx += (target - self.vx) * min(1.0, dt * 14)

        if self.buffer > 0 and self.coyote > 0 and not attacking:
            self.vy = JUMP_VEL
            self.on_ground = False
            self.coyote = 0
            self.buffer = 0
            self.set_state("jump")

        self.vy = min(MAX_FALL, self.vy + GRAVITY * dt)
        self._move(world, dt)

        if attacking:
            self.current().update(dt)
            if self.current().done:
                self.set_state("idle" if abs(self.vx) < 12 else "run")

            return

        if turning:
            self.current().update(dt)
            if self.current().done:
                self.set_state("run" if ax != 0 else "idle")

            return

        if attack_clicked:

            selected_attack = random.choice(("attack1", "attack2"))
            self.set_state(selected_attack)
            self.vx *= 0.3 if selected_attack == "attack1" else 0.2
            return

        if not self.on_ground:

            self.set_state("jump")
            anim = self.current()
            if self.vy < -80:
                anim.index = 0
            elif self.vy < 40:
                anim.index = min(1, len(anim.frames) - 1)
            else:
                anim.index = len(anim.frames) - 1
            return

        if abs(self.vx) > 18:
            self.set_state("run")

        else:
            self.set_state("idle")

        self.current().update(dt)

    def _sync_rect(self):

        self.rect.x = int(round(self.x))
        self.rect.y = int(round(self.y))

    def _move(self, world, dt):
        was_grounded = self.on_ground
        old_bottom = self.y + self.rect.height
        self.x = max(0.0, min(self.x + self.vx * dt,
                              world.pixel_w - self.rect.width))
        self.y += self.vy * dt
        self._sync_rect()
        ground = min(world.ground_y_at(self.rect.left + 2),
                     world.ground_y_at(self.rect.right - 2))
        feet = self.rect.bottom
        if self.vy >= 0 and ((was_grounded and feet >= ground - 6)
                              or (old_bottom <= ground + 8 and feet >= ground)):
            self.y = float(ground - self.rect.height)
            self.rect.y = round(self.y)
            self.vy = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

    def draw_hires(self, window, cam):
        """Render the knight in one pass from the original GIF frame.

        Scaling down to 60% on the tiny game surface and then enlarging it 4x
        discards details. Instead, resize the original once directly to the
        final display size with nearest-neighbor pixel scaling.
        """
        img = self.current().image()
        knight_scale = 0.60
        display_scale = knight_scale * SCALE
        cache_key = (id(img), self.facing)
        if not hasattr(self, "_hires_frame_cache"):
            self._hires_frame_cache = {}
        scaled = self._hires_frame_cache.get(cache_key)
        if scaled is None:
            if self.facing < 0:
                img = pygame.transform.flip(img, True, False)
            scaled = pygame.transform.scale(img, (
                max(1, round(img.get_width() * display_scale)),
                max(1, round(img.get_height() * display_scale)),
            ))
            self._hires_frame_cache[cache_key] = scaled

        draw_x = round((self.rect.centerx - cam.x) * SCALE) - scaled.get_width() // 2
        draw_y = round((self.rect.bottom - cam.y + 1) * SCALE) - scaled.get_height()
        window.blit(scaled, (draw_x, draw_y))

def draw_parallax(surf, layers, cam, world_w):

    max_cam = max(1, world_w - VIEW_W)

    t = cam.x / max_cam

    factors = [0.0, 0.12, 0.28, 0.48, 0.7]

    for layer, factor in zip(layers, factors):

        lw = layer.get_width()

        shift = int(t * factor * (lw))

        x = -shift

        while x > -lw:

            x -= lw

        while x < VIEW_W:

            surf.blit(layer, (x, 0))

            x += lw

def draw_hud(window, font):
    hint = font.render("WASD / SPACE move    CLICK attack", True, (225, 225, 225))
    window.blit(hint, (24, window.get_height() - 40))

INTRO_DIALOGUE = [
    "the forest of flashbacks. only the bravest may traverse.",
    'luckily for you, the gentleman cam, you are "the strongest...like some kind of leaf vegetable..."',
    "at least, that is what the people of your village of burlingamecrest called you.",
    "the meal, still warm in your satchel, awaits its destination, and so do you. better get there quick!",
]

FLASHBACK_MEMORIES = [
    {
        "filename": "dithered-pic1.png",
        "text": "a first kiss? what awkward young souls. you still remember how nervous you were, sitting under the pale glow of the full moon, the autumn night chilly, prompting you to shuffle ever-closer.",
    },
    {
        "filename": "dithered-pic2.png",
        "text": 'your first clandestine meeting with the princess! you remember how you rode on horse-back to watch the play "guillotine-lad", clamming and jamming the whole duration of the night. truly an unforgettable experience.',
    },
    {
        "filename": "dithered-pic3.png",
        "text": '"i love you." the words slipped out of her mouth that day when you were just about to mount your stead, taking the both of you by surprise. but you reciprocated, letting out your bated breath.',
    },
    {
        "filename": "dithered-pic4.png",
        "text": "in the cold winter months, you kept the princess safe from doubt, while she sheltered you from the harsh weather. you went on several escapades, keeping your hearts warm even in dire times. you recall tussling in the snow on the trail near her castle.",
    },
    {
        "filename": "dithered-pic5.png",
        "text": "your travel back home to the village of burlingamecrest. ah, yes... you remember the pure terror on the princess's face when she met your family. she thought the oysters were top tier, though. oh, and your vast chambers of teaching, incomparable to any other the princess had ever seen!",
    },
    {
        "filename": "dithered-pic6.png",
        "text": "the national exhibition! you remember how the tears streamed from your face from the whiplash of the rides. you and the princess pranced around the whole day, carefree and wild.",
    },
]


def wrap_dialogue(text, font, max_width):
    """Wrap text to actual rendered pixel width, not an estimated character count."""
    lines = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and font.size(candidate)[0] > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def load_dialogue_font():
    """Load the font at window resolution, rather than the pixel-art resolution."""
    for filename in ("Tangerine-Regular.ttf", "Tangerine-Bold.ttf"):
        path = asset(filename)
        if os.path.isfile(path):
            return path

    return pygame.font.match_font("tangerine")


def load_dialogue_frame():
    """Load the decorative dialogue frame if frame.png is present."""
    frame_path = asset("frame.png")
    if os.path.isfile(frame_path):
        return load_image(frame_path)
    return None


def build_dialogue_layout(window_size, frame_image):
    """Return a full-resolution frame surface and the inner text rectangle."""
    window_w, window_h = window_size
    if frame_image:
        target_w = int(window_w * 0.66)
        target_h = int(window_h * 0.31)
        scaled_frame = pygame.transform.smoothscale(frame_image, (target_w, target_h))
        frame_rect = scaled_frame.get_rect(midtop=(window_w // 2, 8))
        inner_rect = pygame.Rect(
            frame_rect.x + int(frame_rect.w * 0.115),
            frame_rect.y + int(frame_rect.h * 0.17),
            int(frame_rect.w * 0.77),
            int(frame_rect.h * 0.69),
        )
        text_rect = inner_rect.inflate(-108, -76)
        return scaled_frame, frame_rect, inner_rect, text_rect

    panel = pygame.Rect(8 * SCALE, 8 * SCALE, int(window_w * 0.66), int(window_h * 0.25))
    panel.midtop = (window_w // 2, 8)
    inner_rect = panel.inflate(-24, -18)
    text_rect = inner_rect.inflate(-20, -12)
    return None, panel, inner_rect, text_rect


def make_dialogue_font(font_path, text_rect, messages, max_size=88, min_size=28):
    """Find one readable size that fits every message, avoiding size changes per click."""
    max_width = text_rect.width
    max_height = text_rect.height
    for size in range(max_size, min_size - 1, -2):
        font = (pygame.font.Font(font_path, size) if font_path
                else pygame.font.SysFont("georgia", max(18, size // 2)))
        if all(len(wrap_dialogue(message, font, max_width)) * font.get_linesize() <= max_height
               for message in messages):
            return font
    return (pygame.font.Font(font_path, min_size) if font_path
            else pygame.font.SysFont("georgia", max(18, min_size // 2)))


def draw_intro_dialogue(surf, text, font, frame_surface, frame_rect, inner_rect, text_rect, visible_chars=None):
    """Draw the ornate intro dialogue at full resolution."""
    pygame.draw.rect(surf, (0, 0, 0), inner_rect)
    if frame_surface is not None:
        surf.blit(frame_surface, frame_rect)
    else:
        pygame.draw.rect(surf, (255, 255, 255), frame_rect, 8)

    lines = wrap_dialogue(text, font, text_rect.width)
    total_h = len(lines) * font.get_linesize()
    y = text_rect.y + max(0, (text_rect.height - total_h) // 2)
    remaining = len(text) if visible_chars is None else visible_chars
    for line in lines:
        portion = line[:max(0, remaining)]
        line_x = text_rect.x + max(0, (text_rect.width - font.size(line)[0]) // 2)
        if portion:
            surf.blit(font.render(portion, True, (255, 255, 255)), (line_x, y))
        remaining -= len(line) + 1
        y += font.get_linesize()


class Flashback:
    def __init__(self, image, x, ground_y, description, index):
        self.description = description
        self.index = index
        self.base_x = x
        self.base_y = ground_y
        self.original_image = image
        self.image = self._scale_image(image)
        
        self.display_image = pygame.transform.smoothscale(image, (
            self.image.get_width() * SCALE, self.image.get_height() * SCALE
        ))
        self.w = self.image.get_width()
        self.h = self.image.get_height()
        self.rect = pygame.Rect(x, ground_y - self.h, self.w, self.h)
        self.bob_time = 0.0
        self.state = "idle"  
        self.hit_registered = False
        self.fragments = []

    def _scale_image(self, image):
        target_h = 34
        scale = target_h / max(1, image.get_height())
        target_w = max(16, int(round(image.get_width() * scale)))
        target_h = max(22, int(round(image.get_height() * scale)))
        return pygame.transform.smoothscale(image, (target_w, target_h))

    def current_y(self):
        bob = int(round(math.sin(self.bob_time * 2.5) * 2))
        return self.base_y - self.h + bob

    def barrier_rect(self):
        if self.state in ("gone", "disintegrating"):
            return None
        y = self.current_y()
        return pygame.Rect(self.base_x, y, self.w, self.h)

    def update(self, dt):
        if self.state in ("idle", "hit", "popup"):
            self.bob_time += dt
        elif self.state == "disintegrating":
            alive = []
            for frag in self.fragments:
                frag["x"] += frag["vx"] * dt
                frag["y"] += frag["vy"] * dt
                frag["vy"] += 32 * dt
                frag["life"] -= dt
                if frag["life"] > 0:
                    alive.append(frag)
            self.fragments = alive
            if not self.fragments:
                self.state = "gone"

    def register_hit(self):
        if self.state == "idle":
            self.state = "hit"
            self.hit_registered = True

    def maybe_open_popup(self, player):
        if self.state == "hit" and player.state not in ("attack1", "attack2"):
            self.state = "popup"
            return True
        return False

    def start_disintegration(self):
        if self.state != "popup":
            return
        self.state = "disintegrating"
        piece = 4
        self.fragments = []
        for y in range(0, self.h, piece):
            for x in range(0, self.w, piece):
                sw = min(piece, self.w - x)
                sh = min(piece, self.h - y)
                part = pygame.Surface((sw, sh), pygame.SRCALPHA)
                part.blit(self.image, (0, 0), pygame.Rect(x, y, sw, sh))
                self.fragments.append({
                    "surf": part,
                    "x": self.base_x + x,
                    "y": self.base_y - self.h + y,
                    "vx": random.uniform(-18, 18),
                    "vy": random.uniform(-28, -5),
                    "life": random.uniform(0.35, 0.75),
                })

    def draw(self, surf, cam):
        if self.state == "gone":
            return
        if self.state == "disintegrating":
            for frag in self.fragments:
                piece = frag["surf"].copy()
                alpha = int(255 * max(0.0, min(1.0, frag["life"] / 0.75)))
                piece.set_alpha(alpha)
                surf.blit(piece, (int(frag["x"] - cam.x), int(frag["y"] - cam.y)))
            return

    def draw_hires(self, window, cam):
        if self.state not in ("idle", "hit", "popup"):
            return
        x = round((self.base_x - cam.x) * SCALE)
        y = round((self.current_y() - cam.y) * SCALE)
        window.blit(self.display_image, (x, y))


def load_flashback_images():
    images = []
    fallback = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.rect(fallback, (255, 255, 255), (0, 0, 32, 32), 2)
    pygame.draw.line(fallback, (255, 255, 255), (0, 0), (31, 31), 2)
    pygame.draw.line(fallback, (255, 255, 255), (31, 0), (0, 31), 2)
    for item in FLASHBACK_MEMORIES:
        path = asset(item["filename"])
        if os.path.isfile(path):
            images.append(load_image(path))
        else:
            images.append(fallback.copy())
    return images


def create_flashbacks(images, world):
    positions = [440, 1280, 2120, 2960, 3800, 4640]
    flashbacks = []
    for i, (img, data, x) in enumerate(zip(images, FLASHBACK_MEMORIES, positions), start=1):
        flashbacks.append(Flashback(img, x, round(world.ground_y_at(x)), data["text"], i))
    return flashbacks


def draw_popup(window, image, text, font, sword_image):
    """Compact memory window: native-resolution image and immediately visible text."""
    shade = pygame.Surface(window.get_size(), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 175))
    window.blit(shade, (0, 0))
    iw, ih = image.get_size()
    max_h = 385
    image_scale = min(1.0, max_h / ih, 315 / iw)
    pic = image if image_scale == 1 else pygame.transform.smoothscale(
        image, (round(iw * image_scale), round(ih * image_scale)))
    text_w = 390
    lines = wrap_dialogue(text, font, text_w)
    line_h = font.get_linesize()
    text_h = len(lines) * line_h
    panel_w = pic.get_width() + text_w + 72
    panel_h = max(pic.get_height() + 36, text_h + 90, 205)
    panel_h = min(panel_h, window.get_height() - 34)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = window.get_rect().center
    pygame.draw.rect(window, (0, 0, 0), panel)
    pygame.draw.rect(window, (235, 235, 235), panel, 3)
    window.blit(pic, (panel.x + 16, panel.centery - pic.get_height() // 2))
    tx = panel.x + pic.get_width() + 40
    ty = panel.y + max(20, (panel_h - 56 - text_h) // 2)
    for line in lines:
        window.blit(font.render(line, True, (255, 255, 255)), (tx, ty))
        ty += line_h
    button = pygame.Rect(tx + text_w // 2 - 28, panel.bottom - 63, 56, 49)
    pygame.draw.rect(window, (30, 30, 30), button, border_radius=4)
    pygame.draw.rect(window, (255, 255, 255), button, 2, border_radius=4)
    if sword_image is not None:
        sw, sh = sword_image.get_size()
        scale = min(42 / sw, 39 / sh)
        img = pygame.transform.smoothscale(sword_image,
            (max(1, round(sw * scale)), max(1, round(sh * scale))))
        window.blit(img, img.get_rect(center=button.center))
    return button

MONSTER_SHEETS = {
    "idle": ("monster-Idle.png", 9, 0.12),
    "move": ("monster-Move.png", 10, 0.085),
    "attack1": ("monster-Attack1.png", 13, 0.065),
    "attack2": ("monster-Attack2.png", 15, 0.065),
    "death": ("monster-Death.png", 22, 0.085),
}


def sprite_strip(path, count, trim=True):
    """Slice equal-width sprites. Death frames retain the full canvas so
    shrinking fragments stay tiny instead of being stretched to full height."""
    sheet = load_image(asset(path))
    frames = []
    for i in range(count):
        start = round(sheet.get_width() * i / count)
        end = round(sheet.get_width() * (i + 1) / count)
        frame = sheet.subsurface(pygame.Rect(start, 0, end - start, sheet.get_height())).copy()
        if trim:
            bounds = frame.get_bounding_rect(min_alpha=12)
            if bounds.width and bounds.height:
                frame = frame.subsurface(bounds).copy()
        frames.append(frame)
    return frames


class Tower:
    def __init__(self, x, world):
        source = Image.open(asset("tower.png")).convert("RGBA")
        raw_frames = []
        for i in range(4):
            frame = source.crop((i * 48, 0, (i + 1) * 48, 80))
            raw_frames.append(
                pygame.image.fromstring(frame.tobytes(), frame.size, "RGBA").convert_alpha()
            )
        self.frames = raw_frames
        self.x = x
        self.world = world
        self.elapsed = 0.0
        self.frame_time = 0.20
        self.size = (64 * SCALE, 106 * SCALE)
        self.scaled = [pygame.transform.scale(f, self.size) for f in self.frames]

    def update(self, dt):
        self.elapsed += dt

    def draw(self, window, cam):
        pic = self.scaled[int(self.elapsed / self.frame_time) % len(self.scaled)]
        ground_screen = round((self.world.ground_y_at(self.x + self.size[0] / (2 * SCALE)) - cam.y) * SCALE)
        bounds = pic.get_bounding_rect(min_alpha=1)
        x = round((self.x - cam.x) * SCALE)
        y = ground_screen - bounds.bottom + 6
        window.blit(pic, (x, y))


class Monster:
    def __init__(self, x, target_x, world):
        self.world = world
        self.x = float(x)
        self.target_x = float(target_x)
        self.state = "waiting"
        self.hp = 10
        self.elapsed = 0.0
        self.hit_cooldown = 0.0
        self.swing_registered = False
        self.next_attack = 0.0
        self.warning_shown = False
        self.attack_done = False
        self.attack_hit_applied = False
        self.sheets = {}
        for state, (filename, count, delay) in MONSTER_SHEETS.items():
            originals = sprite_strip(filename, count, trim=(state != "death"))
            scaled = []
            if state == "death":
                death_scale = 180 / 58  
                for frame in originals:
                    scaled.append(pygame.transform.scale(frame, (
                        max(1, round(frame.get_width() * death_scale)),
                        max(1, round(frame.get_height() * death_scale)),
                    )))
            else:
                for frame in originals:
                    scale = min(350 / frame.get_width(), 180 / frame.get_height())
                    scaled.append(pygame.transform.smoothscale(frame, (
                        max(1, round(frame.get_width() * scale)),
                        max(1, round(frame.get_height() * scale)),
                    )))
            self.sheets[state] = (scaled, delay)

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.elapsed = 0.0
            if state in ("attack1", "attack2"):
                self.next_attack = 0.0
                self.attack_hit_applied = False

    @property
    def barrier(self):
        if self.state in ("waiting", "dead", "death"):
            return None
        return pygame.Rect(round(self.x - 18), round(self.world.ground_y_at(self.x) - 64), 48, 64)

    def update(self, dt, player, enabled, can_attack):
        self.hit_cooldown = max(0.0, self.hit_cooldown - dt)
        if self.state == "waiting":
            end_zone_x = self.world.pixel_w - VIEW_W * 0.58
            if enabled and player.rect.centerx >= end_zone_x - 3:
                self.set_state("move")
        elif self.state == "move":
            self.x = max(self.target_x, self.x - 85 * dt)
            if self.x <= self.target_x:
                self.set_state("idle")
                self.warning_shown = True
        elif self.state == "death":
            self.elapsed += dt
            frames, delay = self.sheets["death"]
            if self.elapsed >= len(frames) * delay:
                self.set_state("dead")
            return
        elif self.state in ("attack1", "attack2"):
            self.elapsed += dt
            frames, delay = self.sheets[self.state]
            
            if not self.attack_hit_applied and self.elapsed >= len(frames) * delay * 0.48:
                self.attack_hit_applied = True
                if abs(player.rect.centerx - self.x) <= 62 and abs(player.rect.bottom - self.world.ground_y_at(self.x)) < 35:
                    
                    direction = -1 if player.rect.centerx < self.x else 1
                    player.x = max(0.0, min(self.world.pixel_w - player.rect.width,
                                            player.x + direction * 78))
                    player.y -= 7
                    player.vx = direction * 165
                    player.vy = -145
                    player.on_ground = False
                    player._sync_rect()
            if self.elapsed >= len(frames) * delay:
                self.set_state("idle")
                self.next_attack = 2.0
            return
        elif self.state == "idle" and can_attack:
            self.next_attack -= dt
            if self.next_attack <= 0:
                self.set_state(random.choice(("attack1", "attack2")))
                return
        if self.state not in ("waiting", "dead"):
            self.elapsed += dt

    def register_player_attack(self, player):
        attacking = player.state in ("attack1", "attack2") and not player.current().done
        if not attacking:
            self.swing_registered = False
            return
        if (self.state not in ("idle", "attack1", "attack2") or
                self.swing_registered or self.hit_cooldown > 0):
            return
        hitbox = player.attack_box()
        if hitbox and self.barrier and hitbox.colliderect(self.barrier):
            self.hp -= 1
            self.swing_registered = True
            self.hit_cooldown = 0.20
            if self.hp <= 0:
                self.hp = 0
                self.set_state("death")

    def draw(self, window, cam):
        if self.state in ("waiting", "dead"):
            return
        frames, delay = self.sheets[self.state]
        index = min(len(frames) - 1, int(self.elapsed / delay))
        if self.state in ("idle", "move"):
            index %= len(frames)
       
        img = pygame.transform.flip(frames[index], True, False)
        x = round((self.x - cam.x) * SCALE) - img.get_width() // 2
        ground_screen = round((self.world.ground_y_at(self.x) - cam.y) * SCALE)
        bounds = img.get_bounding_rect(min_alpha=1)
        y = ground_screen - bounds.bottom
        window.blit(img, (x, y))
        if self.state not in ("death",):
            bar = pygame.Rect(x + (img.get_width() - 168) // 2, y - 18, 168, 10)
            pygame.draw.rect(window, (0, 0, 0), bar.inflate(4, 4))
            pygame.draw.rect(window, (240, 240, 240), bar, 2)
            pygame.draw.rect(window, (220, 220, 220),
                             (bar.x + 2, bar.y + 2, round(164 * self.hp / 10), 6))


BOSS_WARNING = "behold! what is that wretched creature?! defeat the monster to restore peace to the land!"

PRINCESS_DIALOGUE = [
    "sir cameron! is that you? why... i can't believe it!",
    "thank you, beloved knight! i was getting hungry. i... have something for you... for your troubles.",
    "sorry, that wasn't it. here it is.",
]


def load_black_to_alpha(path):
    """Load an image and make its black background transparent."""
    if not os.path.isfile(path):
        return None
    source = Image.open(path).convert("RGBA")
    pixels = []
    for r, g, b, a in source.getdata():
        if r <= 8 and g <= 8 and b <= 8:
            pixels.append((0, 0, 0, 0))
        else:
            pixels.append((r, g, b, a))
    source.putdata(pixels)
    bbox = source.getbbox()
    if bbox:
        source = source.crop(bbox)
    return pygame.image.fromstring(source.tobytes(), source.size, "RGBA").convert_alpha()


def load_kiss_mark(path):
    """Load kiss.png and brighten it so the visible mark renders white."""
    if not os.path.isfile(path):
        return None
    source = Image.open(path).convert("RGBA")
    out = Image.new("RGBA", source.size, (0, 0, 0, 0))
    src = source.load()
    dst = out.load()
    for y in range(source.size[1]):
        for x in range(source.size[0]):
            r, g, b, a = src[x, y]
            lum = max(r, g, b)
            
            alpha = max(a, lum)
            if alpha > 0:
                dst[x, y] = (255, 255, 255, alpha)
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return pygame.image.fromstring(out.tobytes(), out.size, "RGBA").convert_alpha()


def draw_speaker_dialogue(surf, text, font, frame_surface, frame_rect, inner_rect, text_rect,
                          portrait, visible_chars=None):
    """Dialogue box with a speaker portrait on the left and text on the right."""
    pygame.draw.rect(surf, (0, 0, 0), inner_rect)
    if frame_surface is not None:
        surf.blit(frame_surface, frame_rect)
    else:
        pygame.draw.rect(surf, (255, 255, 255), frame_rect, 8)

    portrait_size = min(140, inner_rect.height - 48)
    portrait_box = pygame.Rect(inner_rect.x + 26, 0, portrait_size, portrait_size)
    portrait_box.centery = inner_rect.centery
    pygame.draw.rect(surf, (0, 0, 0), portrait_box)
    pygame.draw.rect(surf, (215, 215, 215), portrait_box, 3)
    if portrait is not None:
        scale = min((portrait_box.width - 8) / portrait.get_width(),
                    (portrait_box.height - 8) / portrait.get_height())
        portrait_img = pygame.transform.smoothscale(
            portrait,
            (max(1, round(portrait.get_width() * scale)),
             max(1, round(portrait.get_height() * scale)))
        )
        surf.blit(portrait_img, portrait_img.get_rect(center=portrait_box.center))

    speaker_text_rect = pygame.Rect(
        portrait_box.right + 30,
        inner_rect.y + 36,
        inner_rect.right - (portrait_box.right + 30) - 34,
        inner_rect.height - 72,
    )
    lines = wrap_dialogue(text, font, speaker_text_rect.width)
    total_h = len(lines) * font.get_linesize()
    y = speaker_text_rect.y + max(0, (speaker_text_rect.height - total_h) // 2)
    remaining = len(text) if visible_chars is None else visible_chars
    for line in lines:
        portion = line[:max(0, remaining)]
        line_x = speaker_text_rect.x
        if portion:
            surf.blit(font.render(portion, True, (255, 255, 255)), (line_x, y))
        remaining -= len(line) + 1
        y += font.get_linesize()


def draw_kiss_overlay(window, kiss_image, alpha):
    if kiss_image is None:
        return
    overlay = pygame.Surface(window.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, min(160, alpha // 2)))
    window.blit(overlay, (0, 0))
    scale = min(window.get_width() * 0.28 / kiss_image.get_width(),
                window.get_height() * 0.28 / kiss_image.get_height())
    pic = pygame.transform.smoothscale(
        kiss_image,
        (max(1, round(kiss_image.get_width() * scale)),
         max(1, round(kiss_image.get_height() * scale)))
    )
    pic = pic.copy()
    pic.set_alpha(alpha)
    window.blit(pic, pic.get_rect(center=window.get_rect().center))

END_TEXT = (
    "dear cameron, \n thank you for giving me the world. i love you so much, more than words can say, and i can't wait to spend the future with you. in this past year with you, i have felt more loved and understood than i ever believed possible. when i'm with you, i feel like things are worth doing, and everything feels brand new and perfect. when you put your hands on me, i'm amazed by how tenderly you treat me. i feel beautiful and fragile and precious like a porcelain doll. thank you for always being so patient and caring with me even in my most stressful times. you are truly unlike anyone, so brilliant and full of beauty, and i hope i can return the joy you have given me every day a hundredfold. never would i have thought that this would be the way it turned out for us when we met, but i'm so glad that the invisible string of love tied you to me.\n love,\n\tclare"
)

def draw_end_card(window, title_font, body_font, hint_font, heart_image, scroll_offset):
    """Full-resolution Tangerine ending, with transparent scrolling text inside the heart."""
    window.fill((0, 0, 0))
    ww, wh = window.get_size()
    title = title_font.render("The End", True, (255, 255, 255))
    title_rect = title.get_rect(center=(ww // 2, 65))
    window.blit(title, title_rect)
    heart_top = title_rect.bottom + round(title_font.get_linesize() * 0.25)

    if heart_image is not None:
        max_w, max_h = ww * 0.74, wh * 0.67
        scale = min(max_w / heart_image.get_width(), max_h / heart_image.get_height())
        heart = pygame.transform.smoothscale(
            heart_image,
            (max(1, round(heart_image.get_width() * scale)),
             max(1, round(heart_image.get_height() * scale)))
        )
        heart_rect = heart.get_rect(midtop=(ww // 2, heart_top))
        window.blit(heart, heart_rect)
    else:
        heart_rect = pygame.Rect(0, 0, 500, 500)
        heart_rect.midtop = (ww // 2, heart_top)

    clip_rect = pygame.Rect(0, 0,
                            round(heart_rect.width * 0.53),
                            round(heart_rect.height * 0.37))
    clip_rect.center = (heart_rect.centerx, heart_rect.centery - round(heart_rect.height * 0.02))
    lines = wrap_dialogue(END_TEXT, body_font, clip_rect.width)
    line_h = body_font.get_linesize()
    content_h = len(lines) * line_h
    max_scroll = max(0, content_h - clip_rect.height)
    scroll_offset = max(0, min(scroll_offset, max_scroll))

    old_clip = window.get_clip()
    window.set_clip(clip_rect)
    y = clip_rect.y - scroll_offset
    for line in lines:
        window.blit(body_font.render(line, True, (255, 255, 255)), (clip_rect.x, y))
        y += line_h
    window.set_clip(old_clip)

    hint = hint_font.render("Scroll to read", True, (235, 235, 235))
    window.blit(hint, hint.get_rect(center=(ww // 2, heart_rect.bottom + 22)))
    return max_scroll


async def main():

    pygame.init()

    pygame.display.set_caption("happy 1 year ♡")

    window = pygame.display.set_mode((VIEW_W * SCALE, VIEW_H * SCALE))

    view = pygame.Surface((VIEW_W, VIEW_H)).convert_alpha()

    clock = pygame.time.Clock()

    hud_font = pygame.font.SysFont("consolas", 24)
    dialogue_frame_image = load_dialogue_frame()
    dialogue_frame_surface, dialogue_panel, dialogue_inner_rect, dialogue_text_rect = build_dialogue_layout(
        window.get_size(), dialogue_frame_image
    )
    dialogue_font = make_dialogue_font(load_dialogue_font(), dialogue_text_rect, INTRO_DIALOGUE)
    popup_body_rect = pygame.Rect(0, 0, 390, 220)
    popup_body_font = make_dialogue_font(
        load_dialogue_font(), popup_body_rect,
        [m["text"] for m in FLASHBACK_MEMORIES], max_size=30, min_size=20
    )
    sword_image = load_image(asset("sword.png")) if os.path.isfile(asset("sword.png")) else None
    princess_image = load_black_to_alpha(asset("princess.png")) if os.path.isfile(asset("princess.png")) else None
    kiss_image = load_kiss_mark(asset("kiss.png")) if os.path.isfile(asset("kiss.png")) else None
    heartcard_image = load_heartcard(asset("heartcard.png")) if os.path.isfile(asset("heartcard.png")) else None
    FLASHBACK_TUTORIAL = (
        "hark! a flashback! in order to advance, attack the flashbacks! "
        "this will liberate these memories from this dark place of dwelling."
    )
    tutorial_font = make_dialogue_font(
        load_dialogue_font(), dialogue_text_rect, [FLASHBACK_TUTORIAL],
        max_size=70, min_size=24
    )

    layers = [

        load_image(asset("Layer0.png")),

        load_image(asset("Layer01.png")),

        load_image(asset("Layer02.png")),

        load_tinted_layer(asset("Layer03.png"), (43, 43, 43))  

    ]

    tileset = load_white_tileset(asset("Tileset.png"))

    idle_f, idle_d = load_gif(asset("greyscale_idle.gif"))

    run_f, run_d = load_gif(asset("greyscale_run.gif"))

    jump_f, jump_d = load_gif(asset("greyscale_jump.gif"))

    turn_f, turn_d = load_gif(asset("greyscale_turn.gif"))

    atk1_f, atk1_d = load_gif(asset("grayscale_attack1.gif"))

    atk2_f, atk2_d = load_gif(asset("greyscale_attack2.gif"))

    anims = {

        "idle": Anim(idle_f, idle_d, True),

        "run": Anim(run_f, run_d, True),

        "jump": Anim(jump_f, jump_d, False),

        "turn": Anim(turn_f, turn_d, False),

        "attack1": Anim(atk1_f, atk1_d, False),

        "attack2": Anim(atk2_f, atk2_d, False),

    }

    world = World(tileset)

    player = Player(anims, world.spawn)

    camera = Camera(world.pixel_w, world.pixel_h)
    boss_warning_open = False
    boss_warning_done = False
    boss_reveal = 0.0
    boss_font = make_dialogue_font(load_dialogue_font(), dialogue_text_rect,
                                   [BOSS_WARNING], max_size=70, min_size=24)
    princess_font = make_dialogue_font(load_dialogue_font(), dialogue_text_rect,
                                       PRINCESS_DIALOGUE, max_size=62, min_size=24)
    end_font_path = load_dialogue_font()
    end_title_font = (pygame.font.Font(end_font_path, 88) if end_font_path
                      else pygame.font.SysFont("georgia", 62))
    
    beau_font_path = next((asset(name) for name in (
        "BeauRivage-Regular.ttf", "Beau Rivage Regular.ttf",
        "BeauRivage.ttf", "Beau Rivage.ttf", "beaurivage-regular.ttf"
    ) if os.path.isfile(asset(name))), None)
    if beau_font_path is None:
        beau_font_path = pygame.font.match_font("beau rivage")
    end_body_font = (pygame.font.Font(beau_font_path, 25) if beau_font_path
                     else pygame.font.SysFont("georgia", 30))
    end_hint_font = (pygame.font.Font(end_font_path, 28) if end_font_path
                     else pygame.font.SysFont("georgia", 16))
    flashback_images = load_flashback_images()
    flashbacks = create_flashbacks(flashback_images, world)
   
    last_memory_x = flashbacks[-1].base_x if flashbacks else 4640
    tower = Tower(min(world.pixel_w - 140, last_memory_x + 520), world)
    
    world.pixel_w = round(tower.x + tower.size[0] / SCALE)
    camera.width = world.pixel_w
   
    monster_target_x = tower.x - 52
    monster_spawn_x = world.pixel_w + 35
    monster = Monster(monster_spawn_x, monster_target_x, world)
    current_flashback_index = 0
    active_popup_index = None
    sword_button_rect = None

    dialogue_index = 0  
    tutorial_seen = False
    tutorial_open = False
    dialogue_reveal = 0.0
    tutorial_reveal = 0.0
    princess_index = 0
    princess_open = False
    princess_reveal = 0.0
    princess_started = False
    princess_done = False
    kiss_active = False
    kiss_timer = 0.0
    ending_fade = False
    end_screen = False
    fade_alpha = 0.0
    end_scroll = 0
    end_scroll_max = 0
    LETTERS_PER_SECOND = 44

    running = True

    while running:

        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        attack_clicked = False

        for event in pygame.event.get():

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:

                if dialogue_index < len(INTRO_DIALOGUE):
                    if dialogue_reveal < len(INTRO_DIALOGUE[dialogue_index]):
                        dialogue_reveal = float(len(INTRO_DIALOGUE[dialogue_index]))
                    else:
                        dialogue_index += 1
                        dialogue_reveal = 0.0
                elif tutorial_open:
                    if tutorial_reveal < len(FLASHBACK_TUTORIAL):
                        tutorial_reveal = float(len(FLASHBACK_TUTORIAL))
                    else:
                        tutorial_open = False
                elif boss_warning_open:
                    if boss_reveal < len(BOSS_WARNING):
                        boss_reveal = float(len(BOSS_WARNING))
                    else:
                        boss_warning_open = False
                        boss_warning_done = True
                elif princess_open:
                    if princess_reveal < len(PRINCESS_DIALOGUE[princess_index]):
                        princess_reveal = float(len(PRINCESS_DIALOGUE[princess_index]))
                    else:
                        if princess_index == 1:
                            princess_open = False
                            kiss_active = True
                            kiss_timer = 0.0
                        elif princess_index >= len(PRINCESS_DIALOGUE) - 1:
                            princess_open = False
                            princess_done = True
                            ending_fade = True
                            fade_alpha = 0.0
                        else:
                            princess_index += 1
                            princess_reveal = 0.0
                elif princess_done and not ending_fade and not end_screen:
                    ending_fade = True
                    fade_alpha = 0.0
                elif active_popup_index is not None and sword_button_rect and sword_button_rect.collidepoint(event.pos):
                    flashbacks[active_popup_index].start_disintegration()
                    active_popup_index = None
                    sword_button_rect = None
                elif active_popup_index is None:
                    attack_clicked = True

            if event.type == pygame.MOUSEWHEEL and end_screen:
                end_scroll = max(0, min(end_scroll_max, end_scroll - event.y * 24))

            if event.type == pygame.QUIT:

                running = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:

                running = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_r and dialogue_index >= len(INTRO_DIALOGUE) and active_popup_index is None and not princess_open and not kiss_active and not princess_done and not ending_fade and not end_screen:

                player.respawn()

        keys = pygame.key.get_pressed()

        current_flashback = None
        while current_flashback_index < len(flashbacks) and flashbacks[current_flashback_index].state == "gone":
            current_flashback_index += 1
        if current_flashback_index < len(flashbacks):
            current_flashback = flashbacks[current_flashback_index]

        if dialogue_index >= len(INTRO_DIALOGUE):
            if active_popup_index is None and not tutorial_open and not boss_warning_open and not princess_open and not kiss_active and not princess_done and not ending_fade and not end_screen:
                player.update(dt, keys, world, world.enemies, attack_clicked)
            else:
                
                if player.state in ("attack1", "attack2"):
                    player.current().update(dt)

            if current_flashback is not None:
                if (not tutorial_seen and not tutorial_open and
                    player.rect.right >= current_flashback.base_x - 24):
                    tutorial_open = True
                    tutorial_reveal = 0.0
                    tutorial_seen = True
                barrier = current_flashback.barrier_rect()
                if barrier and player.rect.colliderect(barrier):
                    if player.vx >= 0:
                        player.rect.right = barrier.left
                        player.x = float(player.rect.x)
                        player.vx = 0
                if active_popup_index is None and not tutorial_open and current_flashback.state == "idle" and player.state in ("attack1", "attack2"):
                    hit_box = player.attack_box()
                    if hit_box and hit_box.colliderect(barrier):
                        current_flashback.register_hit()
                if active_popup_index is None and current_flashback.maybe_open_popup(player):
                    active_popup_index = current_flashback_index

            for flashback in flashbacks:
                flashback.update(dt)

            tower.update(dt)
            memories_finished = current_flashback_index >= len(flashbacks)
            monster.update(dt, player, memories_finished, boss_warning_done and not boss_warning_open)
            if monster.warning_shown and not boss_warning_done and not boss_warning_open:
                boss_warning_open = True
                boss_reveal = 0.0
            if (monster.state == "dead" and not princess_started):
                princess_started = True
                princess_open = True
                princess_index = 0
                princess_reveal = 0.0
            if not boss_warning_open and active_popup_index is None and not princess_open and not kiss_active and not princess_done and not ending_fade and not end_screen:
                monster.register_player_attack(player)
           
            wall = monster.barrier
            if wall and player.rect.colliderect(wall):
                if player.rect.centerx < wall.centerx:
                    player.rect.right = wall.left
                else:
                    player.rect.left = wall.right
                player.x = float(player.rect.x)
                player.vx = 0
            camera.follow(player.rect, dt)

        view.fill((0, 0, 0, 255))

        draw_parallax(view, layers, camera, world.pixel_w)

        world.draw(view, camera)

        for flashback in flashbacks:
            flashback.draw(view, camera)

        pygame.transform.scale(view, window.get_size(), window)
        if dialogue_index >= len(INTRO_DIALOGUE) and not end_screen and not ending_fade:
            draw_hud(window, hud_font)
        if dialogue_index < len(INTRO_DIALOGUE):
            dialogue_reveal = min(len(INTRO_DIALOGUE[dialogue_index]),
                                  dialogue_reveal + dt * LETTERS_PER_SECOND)
        elif tutorial_open:
            tutorial_reveal = min(len(FLASHBACK_TUTORIAL),
                                  tutorial_reveal + dt * LETTERS_PER_SECOND)
        elif boss_warning_open:
            boss_reveal = min(len(BOSS_WARNING), boss_reveal + dt * LETTERS_PER_SECOND)
        elif princess_open:
            princess_reveal = min(len(PRINCESS_DIALOGUE[princess_index]), princess_reveal + dt * LETTERS_PER_SECOND)
        elif kiss_active:
            kiss_timer += dt
            if kiss_timer >= 1.0:
                kiss_active = False
                princess_open = True
                princess_index = 2
                princess_reveal = 0.0

        if ending_fade:
            fade_alpha = min(255.0, fade_alpha + dt * 255 / 0.9)
            if fade_alpha >= 255.0:
                ending_fade = False
                end_screen = True
                end_scroll = 0
        for flashback in flashbacks:
            flashback.draw_hires(window, camera)
       
        if monster.x >= tower.x:
            monster.draw(window, camera)
            tower.draw(window, camera)
        else:
            tower.draw(window, camera)
            monster.draw(window, camera)
        player.draw_hires(window, camera)
        if kiss_active:
            alpha = 255 if kiss_timer < 0.55 else max(0, round(255 * (1.0 - (kiss_timer - 0.55) / 0.45)))
            draw_kiss_overlay(window, kiss_image, alpha)

        sword_button_rect = None
        if end_screen:
            end_scroll_max = draw_end_card(window, end_title_font, end_body_font, end_hint_font, heartcard_image, end_scroll)
            end_scroll = max(0, min(end_scroll, end_scroll_max))
        else:
            if dialogue_index < len(INTRO_DIALOGUE):
                draw_intro_dialogue(
                    window,
                    INTRO_DIALOGUE[dialogue_index],
                    dialogue_font,
                    dialogue_frame_surface,
                    dialogue_panel,
                    dialogue_inner_rect,
                    dialogue_text_rect,
                    int(dialogue_reveal),
                )
            elif tutorial_open:
                draw_intro_dialogue(
                    window, FLASHBACK_TUTORIAL, tutorial_font,
                    dialogue_frame_surface, dialogue_panel,
                    dialogue_inner_rect, dialogue_text_rect,
                    int(tutorial_reveal),
                )
            elif boss_warning_open:
                draw_intro_dialogue(
                    window, BOSS_WARNING, boss_font,
                    dialogue_frame_surface, dialogue_panel,
                    dialogue_inner_rect, dialogue_text_rect,
                    int(boss_reveal),
                )
            elif princess_open:
                draw_speaker_dialogue(
                    window, PRINCESS_DIALOGUE[princess_index], princess_font,
                    dialogue_frame_surface, dialogue_panel,
                    dialogue_inner_rect, dialogue_text_rect,
                    princess_image, int(princess_reveal),
                )
            elif active_popup_index is not None:
                sword_button_rect = draw_popup(
                    window,
                    flashbacks[active_popup_index].original_image,
                    flashbacks[active_popup_index].description,
                    popup_body_font,
                    sword_image,
                )

        if ending_fade:
            fade = pygame.Surface(window.get_size(), pygame.SRCALPHA)
            fade.fill((0, 0, 0, round(fade_alpha)))
            window.blit(fade, (0, 0))

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()

if __name__ == "__main__":
    asyncio.run(main())
