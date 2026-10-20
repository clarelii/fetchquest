import os

import random

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

LEVEL_WIDTH = 125
LEVEL = (
    ["." * LEVEL_WIDTH for _ in range(11)]
    + ["S" + "." * (LEVEL_WIDTH - 1)]
    + ["#" * LEVEL_WIDTH for _ in range(2)]
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

        # Fixed vertical framing: ground at world y=192 must remain visible.
        self.y = float(max(0, height - VIEW_H))

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
                spec = self.autotile(x, y)

                if not spec:
                    continue

                img = self.tile_image(*spec)

                surf.blit(img, (x * TILE - int(cam.x), y * TILE - int(cam.y)))

                if self.at(x, y) == "." and self.at(x, y + 1) == "#" and (x + y) % 5 == 0:

                    tuft = self.tile_image(x % 4, 3)

                    surf.blit(tuft, (x * TILE - int(cam.x), y * TILE - int(cam.y)))

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

        self.x += self.vx * dt
        self._sync_rect()

        for solid, ch in world.solid_rects_near(self.rect):

            if ch == "=":
                continue

            if self.rect.colliderect(solid):

                if self.vx > 0:
                    self.rect.right = solid.left
                elif self.vx < 0:
                    self.rect.left = solid.right

                self.x = float(self.rect.x)
                self.vx = 0

        self.y += self.vy * dt

        self._sync_rect()

        self.on_ground = False

        for solid, ch in world.solid_rects_near(self.rect):

            if not self.rect.colliderect(solid):
                continue

            if ch == "=":
                prev_bottom = self.y - self.vy * dt + self.rect.h

                if self.vy >= 0 and prev_bottom <= solid.top + 3:
                    self.rect.bottom = solid.top
                    self.y = float(self.rect.y)
                    self.vy = 0
                    self.on_ground = True

                continue

            if self.vy > 0:
                self.rect.bottom = solid.top
                self.y = float(self.rect.y)
                self.vy = 0
                self.on_ground = True

            elif self.vy < 0:
                self.rect.top = solid.bottom
                self.y = float(self.rect.y)
                self.vy = 0

        if self.rect.left < 0:
            self.rect.left = 0
            self.x = 0
            self.vx = 0

        if self.rect.right > world.pixel_w:
            self.rect.right = world.pixel_w
            self.x = float(self.rect.x)
            self.vx = 0

        if self.vy >= 0:

            foot = pygame.Rect(self.rect.x + 1, self.rect.bottom, self.rect.w - 2, 1)

            for solid, ch in world.solid_rects_near(foot):

                if not (foot.left < solid.right and foot.right > solid.left):
                    continue

                top = solid.top

                if ch == "=":

                    top = solid.top

                if top <= foot.bottom and top >= self.rect.bottom - 2:
                    self.rect.bottom = solid.top if ch != "=" else top
                    self.y = float(self.rect.y)
                    self.vy = 0
                    self.on_ground = True
                    break

    def draw(self, surf, cam):

        img = self.current().image()

        if self.facing < 0:

            img = pygame.transform.flip(img, True, False)

        #change scaling if need
        knight_scale = 0.60
        img = pygame.transform.scale(img, (
            max(1, round(img.get_width() * knight_scale)),
            max(1, round(img.get_height() * knight_scale)),
        ))
        draw_x = self.rect.centerx - img.get_width() // 2 - int(cam.x)
        draw_y = self.rect.bottom - img.get_height() - int(cam.y) + 1

        surf.blit(img, (draw_x, draw_y))

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

def draw_hud(surf, player, font):
    # No health, lives, game-over or victory overlays in peaceful mode.
    hint = font.render("WASD/space move  CLICK atk", True, (200, 200, 200))
    surf.blit(hint, (8, VIEW_H - 14))

def main():

    pygame.init()

    pygame.display.set_caption("happy 1 year ♡")

    window = pygame.display.set_mode((VIEW_W * SCALE, VIEW_H * SCALE))

    view = pygame.Surface((VIEW_W, VIEW_H)).convert_alpha()

    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 10)

    layers = [

        load_image(asset("Layer0.png")),

        load_image(asset("Layer01.png")),

        load_image(asset("Layer02.png")),

        load_tinted_layer(asset("Layer03.png"), (43, 43, 43))  # #2b2b2b,

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

    running = True

    while running:

        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        attack_clicked = False

        for event in pygame.event.get():

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:

                attack_clicked = True

            if event.type == pygame.QUIT:

                running = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:

                running = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:

                player.respawn()

        keys = pygame.key.get_pressed()

        player.update(dt, keys, world, world.enemies, attack_clicked)

        camera.follow(player.rect, dt)

        view.fill((0, 0, 0, 255))

        draw_parallax(view, layers, camera, world.pixel_w)

        world.draw(view, camera)

        player.draw(view, camera)

        draw_hud(view, player, font)

        pygame.transform.scale(view, window.get_size(), window)

        pygame.display.flip()

    pygame.quit()

    sys.exit()

if __name__ == "__main__":

    main()
