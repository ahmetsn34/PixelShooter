# -*- coding: utf-8 -*-
"""
=========================================================================
  PYCS2  --  Counter-Strike 2 esintili, saf Python (pygame) raycast FPS
=========================================================================
  * Texture'lı raycast motoru (DDA), dikey nişan (pitch), zıplama, crouch
  * 7 silah (M4A1, AK-47, AWP, MP9, Deagle, Glock, Bıçak) + zırh + HE bomba
  * Sekme sekme yayılım (spread), geri tepme, şarjör/reload, zoom (AWP)
  * NPC BOT'lar: A* yol bulma, görüş hattı (LOS), FOV, duyma, siper alma,
    ateş etme, bomba kurma/defuse etme, takım arkadaşı botlar
  * Bomba senaryosu (de_pycs), round sistemi, ekonomi, satın alma menüsü
  * HUD, radar/minimap, kill feed, scoreboard, hitmarker, kafa vuruşu
  * Prosedürel texture, sprite ve ses üretimi (harici dosya YOK)
-------------------------------------------------------------------------
  KONTROLLER
    W A S D .......... hareket            Mouse ......... bakış
    Sol tık .......... ateş               Sağ tık ....... AWP dürbün
    R ................ şarjör değiştir    G ............. HE bombası
    Shift ............ sessiz yürü        Ctrl .......... eğil
    Space ............ zıpla              E ............. bombayı defuse et
    B ................ satın alma menüsü (freeze time)
    1-7 .............. silah satın al (menü açıkken)
    TAB .............. skor tablosu       ESC ........... çıkış
=========================================================================
"""
import math
import random
import sys
import os
import heapq
from itertools import islice as _islice

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

try:
    import numpy as np
    HAS_NP = True
except Exception:
    HAS_NP = False

# --------------------------------------------------------------------- #
#  AYARLAR
# --------------------------------------------------------------------- #
WIN_W, WIN_H = 1280, 720          # pencere
RW, RH = 400, 225                 # dahili render çözünürlüğü (hız için)
HALF_RH = RH // 2
BASE_FOV = 72.0                   # yatay görüş açısı (derece)
MAXD = 40                         # maksimum ışın mesafesi
TEX = 64                          # texture boyutu
FPS_CAP = 60
SHADES = 8                        # mesafe gölge kademesi

MW, MH = 40, 32                   # harita boyutu
SOLID = frozenset("#=c")

MAX_SCORE = 8                     # maçı kazanmak için gereken round
FREEZE_TIME = 6.0
ROUND_TIME = 100.0
END_TIME = 4.0
BOMB_TIME = 40.0
PLANT_TIME = 3.2
DEFUSE_TIME = 7.0

PLAYER_R = 0.28                   # çarpışma yarıçapı
BOT_R = 0.30

C_BG = (12, 12, 16)
C_TXT = (232, 228, 216)
C_ACC = (222, 160, 40)
C_CT = (90, 140, 205)
C_T = (206, 160, 80)
C_HP = (90, 200, 120)
C_BAD = (210, 70, 60)


# --------------------------------------------------------------------- #
#  HARİTA (de_pycs)
# --------------------------------------------------------------------- #
def _rect(g, x0, y0, x1, y1, ch, filled=True):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if 0 <= x < MW and 0 <= y < MH:
                if filled or x in (x0, x1) or y in (y0, y1):
                    g[y][x] = ch


def build_map():
    g = [[' '] * MW for _ in range(MH)]
    _rect(g, 0, 0, MW - 1, MH - 1, '#', filled=False)

    # kapak/siper blokları  (x0,y0,x1,y1,karakter)
    blocks = [
        (11, 2, 13, 7, '#'), (16, 4, 18, 10, '='), (22, 2, 24, 6, '#'),
        (5, 11, 9, 13, '#'), (13, 13, 20, 15, '#'), (24, 10, 26, 14, '='),
        (30, 12, 34, 14, '#'), (3, 17, 7, 19, '='), (11, 19, 16, 21, '#'),
        (20, 18, 22, 24, '#'), (26, 20, 30, 22, '='), (8, 25, 13, 27, '#'),
        (17, 27, 22, 29, '#'), (33, 17, 36, 19, 'c'), (2, 22, 4, 24, 'c'),
        (14, 8, 15, 9, 'c'), (27, 7, 28, 8, 'c'), (19, 12, 20, 12, 'c'),
        (7, 15, 8, 16, 'c'), (25, 25, 26, 26, 'c'), (36, 8, 37, 9, 'c'),
        (12, 24, 13, 24, 'c'), (30, 3, 30, 9, '='), (34, 22, 35, 23, 'c'),
    ]
    for (x0, y0, x1, y1, ch) in blocks:
        _rect(g, x0, y0, x1, y1, ch)

    # spawn ve bombasitesi işaretleri (zemin)
    _rect(g, 2, 2, 7, 6, 't')          # T spawn
    _rect(g, 31, 25, 37, 29, 'C')      # CT spawn
    _rect(g, 31, 2, 37, 8, 'A')        # Bombsite A
    _rect(g, 33, 4, 34, 5, 'c')        # site içi sandık
    g[3][30] = ' '
    g[6][30] = ' '                     # siteye giriş kapıları
    return g


MAP = build_map()
T_SPAWNS = [(x + 0.5, y + 0.5) for y in range(MH) for x in range(MW) if MAP[y][x] == 't']
CT_SPAWNS = [(x + 0.5, y + 0.5) for y in range(MH) for x in range(MW) if MAP[y][x] == 'C']
SITE_CELLS = [(x, y) for y in range(MH) for x in range(MW) if MAP[y][x] == 'A']
SITE_CENTER = (34.0, 5.0)
TEX_OF = {'#': 0, '=': 1, 'c': 2}


def solid(x, y):
    if x < 0 or y < 0 or x >= MW or y >= MH:
        return True
    return MAP[int(y)][int(x)] in SOLID


def solid_cell(cx, cy):
    if cx < 0 or cy < 0 or cx >= MW or cy >= MH:
        return True
    return MAP[cy][cx] in SOLID


def los(x0, y0, x1, y1, step=0.18):
    """İki nokta arasında görüş hattı var mı?"""
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return True
    n = int(d / step) + 1
    sx, sy = dx / n, dy / n
    x, y = x0, y0
    for _ in range(n):
        x += sx
        y += sy
        if solid(x, y):
            return False
    return True


_NB = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def astar(start, goal, limit=4000):
    """Izgara üzerinde A*. start/goal = (cx,cy). Hücre listesi döner."""
    if start == goal:
        return [goal]
    if solid_cell(*goal):
        best, bd = None, 1e9
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                c = (goal[0] + dx, goal[1] + dy)
                if not solid_cell(*c):
                    d = dx * dx + dy * dy
                    if d < bd:
                        best, bd = c, d
        if best is None:
            return []
        goal = best
    openh = [(0.0, start)]
    came, gsc = {}, {start: 0.0}
    seen = 0
    while openh:
        _, cur = heapq.heappop(openh)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path
        seen += 1
        if seen > limit:
            break
        cx, cy = cur
        for dx, dy in _NB:
            nx, ny = cx + dx, cy + dy
            if solid_cell(nx, ny):
                continue
            if dx and dy and (solid_cell(cx + dx, cy) or solid_cell(cx, cy + dy)):
                continue          # köşe kesme yok
            cost = 1.414 if (dx and dy) else 1.0
            ng = gsc[cur] + cost
            nxt = (nx, ny)
            if ng < gsc.get(nxt, 1e18):
                gsc[nxt] = ng
                came[nxt] = cur
                h = math.hypot(goal[0] - nx, goal[1] - ny)
                heapq.heappush(openh, (ng + h, nxt))
    return []


def ang_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


# --------------------------------------------------------------------- #
#  PROSEDÜREL TEXTURE / SPRITE ÜRETİMİ
# --------------------------------------------------------------------- #
def _noise_px(surf, n, col, alpha_rng=(10, 40)):
    for _ in range(n):
        x, y = random.randrange(TEX), random.randrange(TEX)
        a = random.randint(*alpha_rng)
        s = pygame.Surface((1, 1), pygame.SRCALPHA)
        s.fill((col[0], col[1], col[2], a))
        surf.blit(s, (x, y))


def gen_tex_wall():
    s = pygame.Surface((TEX, TEX))
    s.fill((172, 150, 114))
    for row in range(0, TEX, 16):
        pygame.draw.line(s, (124, 105, 78), (0, row), (TEX, row))
        off = 0 if (row // 16) % 2 == 0 else 16
        for x in range(off, TEX + 1, 32):
            pygame.draw.line(s, (124, 105, 78), (x, row), (x, row + 15))
    _noise_px(s, 900, (255, 240, 200), (8, 30))
    _noise_px(s, 500, (60, 50, 35), (8, 26))
    return s


def gen_tex_metal():
    s = pygame.Surface((TEX, TEX))
    s.fill((98, 108, 118))
    for x in range(0, TEX, 8):
        c = 118 if (x // 8) % 2 == 0 else 84
        pygame.draw.rect(s, (c - 8, c, c + 10), (x, 0, 4, TEX))
    for y in (6, 30, 54):
        for x in (6, 30, 54):
            pygame.draw.circle(s, (62, 70, 78), (x + 2, y + 2), 3)
            pygame.draw.circle(s, (150, 160, 170), (x + 1, y + 1), 1)
    pygame.draw.line(s, (60, 66, 74), (0, 32), (TEX, 32), 2)
    _noise_px(s, 400, (0, 0, 0), (6, 22))
    return s


def gen_tex_crate():
    s = pygame.Surface((TEX, TEX))
    s.fill((146, 104, 58))
    for y in range(0, TEX, 12):
        pygame.draw.line(s, (108, 74, 40), (0, y), (TEX, y), 2)
    pygame.draw.rect(s, (92, 92, 98), (0, 0, TEX, TEX), 4)
    pygame.draw.line(s, (108, 74, 40), (4, 4), (TEX - 4, TEX - 4), 3)
    pygame.draw.line(s, (108, 74, 40), (TEX - 4, 4), (4, TEX - 4), 3)
    _noise_px(s, 700, (255, 220, 170), (6, 24))
    return s


def shade_surface(src, f):
    s = src.copy()
    dark = pygame.Surface(src.get_size())
    dark.fill((0, 0, 0))
    dark.set_alpha(int(255 * (1.0 - f)))
    s.blit(dark, (0, 0))
    return s


def build_texture_columns():
    """TEXCOLS[tid][shade][texx] -> 1xTEX yüzey"""
    random.seed(7)
    base = [gen_tex_wall(), gen_tex_metal(), gen_tex_crate()]
    out = []
    for t in base:
        per_shade = []
        for s in range(SHADES):
            f = 1.0 - (s / (SHADES - 1)) * 0.78
            sh = shade_surface(t, f).convert()
            cols = [sh.subsurface((x, 0, 1, TEX)).copy() for x in range(TEX)]
            per_shade.append(cols)
        out.append(per_shade)
    random.seed()
    return out


# ---------------------------- sprite'lar ----------------------------- #
def _soldier(team, pose):
    """32x48 asker sprite'ı prosedürel çizilir. pose: 0 dur 1/2 yürü 3 ateş"""
    s = pygame.Surface((32, 48), pygame.SRCALPHA)
    if team == 'CT':
        shirt, pants, helm = (66, 96, 140), (44, 56, 80), (52, 64, 92)
    else:
        shirt, pants, helm = (154, 122, 70), (96, 76, 46), (78, 62, 40)
    skin = (206, 168, 132)
    # bacaklar
    swing = {0: 0, 1: 3, 2: -3, 3: 0}[pose]
    pygame.draw.rect(s, pants, (10 + swing, 30, 5, 17), border_radius=2)
    pygame.draw.rect(s, pants, (17 - swing, 30, 5, 17), border_radius=2)
    pygame.draw.rect(s, (28, 28, 32), (10 + swing, 45, 6, 3))
    pygame.draw.rect(s, (28, 28, 32), (17 - swing, 45, 6, 3))
    # gövde + yelek
    pygame.draw.rect(s, shirt, (9, 15, 14, 16), border_radius=3)
    pygame.draw.rect(s, (max(0, shirt[0] - 26), max(0, shirt[1] - 26),
                         max(0, shirt[2] - 26)), (10, 18, 12, 9))
    # kafa + kask
    pygame.draw.circle(s, skin, (16, 11), 5)
    pygame.draw.circle(s, helm, (16, 9), 6)
    pygame.draw.rect(s, helm, (10, 8, 12, 3))
    # kollar + silah
    if pose == 3:
        pygame.draw.rect(s, shirt, (21, 17, 9, 4), border_radius=2)
        pygame.draw.rect(s, (34, 34, 38), (26, 16, 12, 4))
        pygame.draw.rect(s, (52, 52, 58), (30, 19, 4, 5))
    else:
        pygame.draw.rect(s, shirt, (6, 17, 4, 12), border_radius=2)
        pygame.draw.rect(s, shirt, (22, 17, 4, 12), border_radius=2)
        pygame.draw.rect(s, (40, 40, 45), (22, 24, 11, 3))
    return s


def _corpse(team):
    s = pygame.Surface((48, 22), pygame.SRCALPHA)
    if team == 'CT':
        shirt, pants = (58, 84, 122), (38, 48, 70)
    else:
        shirt, pants = (136, 106, 60), (84, 66, 40)
    pygame.draw.ellipse(s, (110, 20, 18), (2, 12, 44, 9))
    pygame.draw.rect(s, pants, (6, 6, 18, 9), border_radius=3)
    pygame.draw.rect(s, shirt, (22, 5, 18, 10), border_radius=3)
    pygame.draw.circle(s, (198, 160, 126), (43, 9), 5)
    return s


def _bomb_sprite(lit):
    s = pygame.Surface((26, 20), pygame.SRCALPHA)
    pygame.draw.rect(s, (48, 44, 40), (0, 4, 26, 16), border_radius=3)
    pygame.draw.rect(s, (86, 80, 72), (2, 6, 22, 6), border_radius=2)
    pygame.draw.rect(s, (30, 28, 26), (4, 13, 18, 5))
    col = (255, 60, 40) if lit else (70, 24, 20)
    pygame.draw.circle(s, col, (13, 3), 3)
    return s


def _puff(col, r):
    s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    pygame.draw.circle(s, col, (r, r), r)
    return s


class Art:
    def __init__(self):
        self.texcols = build_texture_columns()
        self.soldier = {t: [_soldier(t, p).convert_alpha() for p in range(4)]
                        for t in ('CT', 'T')}
        self.corpse = {t: _corpse(t).convert_alpha() for t in ('CT', 'T')}
        self.bomb = [_bomb_sprite(False).convert_alpha(),
                     _bomb_sprite(True).convert_alpha()]
        self.nade = _puff((70, 90, 60, 255), 6).convert_alpha()
        self.blood = _puff((170, 24, 20, 220), 8).convert_alpha()
        self.spark = _puff((255, 210, 120, 230), 6).convert_alpha()
        self.smoke = _puff((150, 150, 150, 150), 12).convert_alpha()
        # zemin/gökyüzü gradyanı
        self.bg = pygame.Surface((RW, RH)).convert()
        for y in range(RH):
            if y < HALF_RH:
                t = y / max(1, HALF_RH)
                c = (int(28 + 46 * t), int(32 + 50 * t), int(44 + 58 * t))
            else:
                t = (y - HALF_RH) / max(1, HALF_RH)
                c = (int(58 + 74 * t), int(52 + 62 * t), int(40 + 44 * t))
            pygame.draw.line(self.bg, c, (0, y), (RW, y))


# --------------------------------------------------------------------- #
#  SES (numpy ile prosedürel)
# --------------------------------------------------------------------- #
class Audio:
    SR = 44100

    def __init__(self, enabled=True):
        self.ok = False
        self.snd = {}
        if not (enabled and HAS_NP):
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(self.SR, -16, 2, 512)
            pygame.mixer.set_num_channels(24)
            self._build()
            self.ok = True
        except Exception:
            self.ok = False

    def _mk(self, mono, vol=0.9):
        a = np.clip(mono, -1, 1) * vol
        a = (a * 26000).astype(np.int16)
        st = np.repeat(a.reshape(-1, 1), 2, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(st))

    def _shot(self, dur, tone, decay, bright, vol):
        n = int(self.SR * dur)
        t = np.arange(n) / self.SR
        env = np.exp(-t / decay)
        noise = np.random.uniform(-1, 1, n) * bright
        body = np.sin(2 * np.pi * tone * t) * 0.9
        sub = np.sin(2 * np.pi * (tone * 0.5) * t) * 0.6
        crack = np.exp(-t / 0.008) * np.random.uniform(-1, 1, n)
        return self._mk((noise + body + sub + crack) * env * 0.5, vol)

    def _build(self):
        np.random.seed(3)
        self.snd['ak'] = self._shot(0.30, 120, 0.075, 1.0, 0.55)
        self.snd['m4'] = self._shot(0.24, 165, 0.055, 0.9, 0.5)
        self.snd['awp'] = self._shot(0.60, 78, 0.19, 1.1, 0.75)
        self.snd['smg'] = self._shot(0.16, 210, 0.038, 0.8, 0.4)
        self.snd['pistol'] = self._shot(0.22, 190, 0.05, 0.85, 0.45)
        n = int(self.SR * 0.9)
        t = np.arange(n) / self.SR
        self.snd['boom'] = self._mk(
            (np.random.uniform(-1, 1, n) * 1.2 + np.sin(2 * np.pi * 45 * t))
            * np.exp(-t / 0.32) * 0.6, 0.9)
        n = int(self.SR * 0.05)
        t = np.arange(n) / self.SR
        self.snd['click'] = self._mk(np.random.uniform(-1, 1, n) * np.exp(-t / 0.006), 0.35)
        self.snd['step'] = self._mk(np.random.uniform(-1, 1, n) * np.exp(-t / 0.012) * 0.5, 0.22)
        n = int(self.SR * 0.09)
        t = np.arange(n) / self.SR
        self.snd['hit'] = self._mk(np.sin(2 * np.pi * 1400 * t) * np.exp(-t / 0.03), 0.35)
        self.snd['hurt'] = self._mk(
            (np.sin(2 * np.pi * 180 * t) + np.random.uniform(-1, 1, n) * 0.6)
            * np.exp(-t / 0.05), 0.4)
        n = int(self.SR * 0.12)
        t = np.arange(n) / self.SR
        self.snd['beep'] = self._mk(np.sin(2 * np.pi * 900 * t) * np.exp(-t / 0.05), 0.4)
        self.snd['reload'] = self._mk(
            np.random.uniform(-1, 1, n) * np.exp(-t / 0.02) * 0.7, 0.3)
        np.random.seed()

    def play(self, key, dist=0.0, vol=1.0):
        if not self.ok or key not in self.snd:
            return
        v = clamp(vol * (1.0 - dist / 26.0), 0.0, 1.0)
        if v <= 0.02:
            return
        try:
            ch = pygame.mixer.find_channel(True)
            if ch:
                ch.set_volume(v)
                ch.play(self.snd[key])
        except Exception:
            pass


# --------------------------------------------------------------------- #
#  SİLAHLAR
# --------------------------------------------------------------------- #
class Wep:
    def __init__(self, key, name, price, dmg, rpm, mag, reserve, spread,
                 recoil, reload_t, snd, kind, auto=True, pen=0.75, rng=60.0):
        self.key = key; self.name = name; self.price = price
        self.dmg = dmg; self.rpm = rpm; self.mag = mag; self.reserve = reserve
        self.spread = spread; self.recoil = recoil; self.reload_t = reload_t
        self.snd = snd; self.kind = kind; self.auto = auto
        self.pen = pen; self.rng = rng
        self.interval = 60.0 / rpm

    def kill_reward(self):
        return {'knife': 1500, 'pistol': 300, 'smg': 600,
                'rifle': 300, 'sniper': 100}.get(self.kind, 300)


WEAPONS = {
    'knife':  Wep('knife',  'Bıçak',   0,    65,  120, 1,   0,  0.00, 0.0, 0.6, 'click',  'knife',  False, 1.0, 1.6),
    'glock':  Wep('glock',  'Glock-18', 0,    28,  360, 20,  120, 0.020, 0.9, 1.9, 'pistol', 'pistol', False, 0.5, 40),
    'deagle': Wep('deagle', 'Deagle',  700,  63,  267, 7,   35,  0.016, 3.6, 2.2, 'pistol', 'pistol', False, 0.9, 55),
    'mp9':    Wep('mp9',    'MP9',     1250, 26,  857, 30,  120, 0.034, 0.8, 2.1, 'smg',    'smg',    True,  0.5, 35),
    'm4':     Wep('m4',     'M4A1-S',  2900, 33,  666, 30,  90,  0.021, 1.6, 3.1, 'm4',     'rifle',  True,  0.85, 60),
    'ak':     Wep('ak',     'AK-47',   2700, 36,  600, 30,  90,  0.025, 2.2, 2.5, 'ak',     'rifle',  True,  0.9, 60),
    'awp':    Wep('awp',    'AWP',     4750, 115, 41,  10,  30,  0.004, 6.5, 3.7, 'awp',    'sniper', False, 1.0, 90),
}
BUY_LIST = ['glock', 'deagle', 'mp9', 'm4', 'ak', 'awp']
ARMOR_PRICE = 1000
NADE_PRICE = 300


class Slot:
    """Bir silahın oyuncudaki durumu (şarjör/yedek)."""
    def __init__(self, key):
        self.w = WEAPONS[key]
        self.ammo = self.w.mag
        self.reserve = self.w.reserve

    def refill(self):
        self.ammo = self.w.mag
        self.reserve = self.w.reserve


# --------------------------------------------------------------------- #
#  EFEKTLER
# --------------------------------------------------------------------- #
class Particle:
    def __init__(self, x, y, z, vx, vy, vz, life, img, scale=0.25, grav=1.6):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.life = life; self.t0 = life
        self.img = img; self.scale = scale; self.grav = grav

    def update(self, dt):
        self.x += self.vx * dt; self.y += self.vy * dt
        self.z += self.vz * dt
        self.vz -= self.grav * dt
        if self.z < 0.03:
            self.z = 0.03; self.vz = 0; self.vx *= 0.5; self.vy *= 0.5
        self.life -= dt
        return self.life > 0


class Tracer:
    def __init__(self, x0, y0, z0, x1, y1, z1, life=0.055, col=(255, 230, 160)):
        self.a = (x0, y0, z0); self.b = (x1, y1, z1)
        self.life = life; self.col = col

    def update(self, dt):
        self.life -= dt
        return self.life > 0


class Grenade:
    def __init__(self, x, y, z, vx, vy, vz, owner):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.fuse = 1.9
        self.owner = owner

    def update(self, dt, world):
        self.fuse -= dt
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        if solid(nx, self.y):
            self.vx = -self.vx * 0.45
        else:
            self.x = nx
        if solid(self.x, ny):
            self.vy = -self.vy * 0.45
        else:
            self.y = ny
        self.z += self.vz * dt
        self.vz -= 5.5 * dt
        if self.z < 0.06:
            self.z = 0.06
            self.vz = -self.vz * 0.42
            self.vx *= 0.7; self.vy *= 0.7
        return self.fuse > 0


# --------------------------------------------------------------------- #
#  OYUNCU
# --------------------------------------------------------------------- #
class Player:
    def __init__(self, art):
        self.team = 'CT'
        self.art = art
        self.x, self.y = CT_SPAWNS[0] if CT_SPAWNS else (2.5, 2.5)
        self.ang = -math.pi / 2
        self.pitch = 0.0
        self.z = 0.0
        self.vz = 0.0
        self.crouch = 0.0
        self.hp = 100
        self.armor = 0
        self.helmet = False
        self.money = 800
        self.alive = True
        self.slots = {'knife': Slot('knife'), 'glock': Slot('glock')}
        self.cur = 'glock'
        self.nades = 0
        self.cd = 0.0
        self.reloading = 0.0
        self.spread = 0.0
        self.recoil = 0.0
        self.bob = 0.0
        self.step_acc = 0.0
        self.zoom = False
        self.kills = 0
        self.deaths = 0
        self.hitmark = 0.0
        self.hurt_flash = 0.0
        self.hurt_dir = 0.0
        self.shake = 0.0
        self.defusing = 0.0
        self.vel = (0.0, 0.0)

    # ---- yardımcılar
    @property
    def slot(self):
        return self.slots[self.cur]

    @property
    def wep(self):
        return self.slot.w

    def eye(self):
        return 0.5 + self.z - self.crouch * 0.22

    def give(self, key, reset_ammo=True):
        if key not in self.slots:
            self.slots[key] = Slot(key)
        elif reset_ammo:
            self.slots[key].refill()
        self.cur = key

    def reset_round(self):
        self.hp = 100
        self.alive = True
        self.z = 0.0; self.vz = 0.0
        self.pitch = 0.0
        self.spread = 0.0; self.recoil = 0.0
        self.reloading = 0.0; self.cd = 0.0
        self.defusing = 0.0
        for s in self.slots.values():
            s.refill()
        sp = random.choice(CT_SPAWNS) if CT_SPAWNS else (2.5, 2.5)
        self.x, self.y = sp
        self.ang = math.atan2(SITE_CENTER[1] - self.y, SITE_CENTER[0] - self.x)

    def cur_spread(self, moving):
        w = self.wep
        s = w.spread * (1.0 + self.spread)
        if moving:
            s *= 2.4
        if self.crouch > 0.5:
            s *= 0.55
        if self.zoom and w.kind == 'sniper':
            s *= 0.12
        if abs(self.vz) > 0.1:
            s *= 3.2
        return s

    # ---- hareket
    def move(self, inp, dt, world):
        w = self.wep
        speed = 3.5
        if w.kind == 'sniper':
            speed = 2.9
        elif w.kind == 'knife':
            speed = 4.2
        if inp.walk:
            speed *= 0.52
        if self.crouch > 0.5:
            speed *= 0.5
        if self.zoom:
            speed *= 0.45

        tgt = 1.0 if (inp.crouch and self.z <= 0.01) else 0.0
        self.crouch += (tgt - self.crouch) * min(1.0, dt * 12)

        dx = math.cos(self.ang) * inp.fwd + math.cos(self.ang + math.pi / 2) * inp.strafe
        dy = math.sin(self.ang) * inp.fwd + math.sin(self.ang + math.pi / 2) * inp.strafe
        n = math.hypot(dx, dy)
        if n > 1e-6:
            dx, dy = dx / n, dy / n
        vx, vy = dx * speed, dy * speed
        self.vel = (vx, vy)
        self.slide(vx * dt, vy * dt)

        if inp.jump and self.z <= 0.001 and self.crouch < 0.4:
            self.vz = 2.35
        self.z += self.vz * dt
        if self.z > 0:
            self.vz -= 7.5 * dt
        else:
            self.z = 0.0; self.vz = 0.0

        mv = n > 0.05 and self.z <= 0.001
        if mv:
            self.bob += dt * speed * 2.3
            self.step_acc += dt * speed
            if self.step_acc > 1.55:
                self.step_acc = 0.0
                world.audio.play('step', 0, 0.5 if inp.walk else 1.0)
                if not inp.walk:
                    world.noise(self.x, self.y, self, 9.0)
        return mv

    def slide(self, dx, dy):
        r = PLAYER_R
        nx = self.x + dx
        if not (solid(nx + math.copysign(r, dx), self.y + r) or
                solid(nx + math.copysign(r, dx), self.y - r)):
            self.x = nx
        ny = self.y + dy
        if not (solid(self.x + r, ny + math.copysign(r, dy)) or
                solid(self.x - r, ny + math.copysign(r, dy))):
            self.y = ny

    def take_damage(self, dmg, src_x, src_y, world, attacker=None, head=False):
        if not self.alive:
            return
        if self.armor > 0:
            absorbed = dmg * (0.5 if not head or self.helmet else 0.75)
            self.armor = max(0, self.armor - int(dmg * 0.5))
            dmg = dmg - absorbed * 0.72
        self.hp -= int(max(1, dmg))
        self.hurt_flash = 0.55
        self.hurt_dir = ang_diff(math.atan2(src_y - self.y, src_x - self.x), self.ang)
        self.shake = min(0.5, self.shake + 0.16)
        world.audio.play('hurt', 0, 0.8)
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            self.deaths += 1
            world.on_death(self, attacker)


# --------------------------------------------------------------------- #
#  BOT (NPC)
# --------------------------------------------------------------------- #
class Bot:
    ID = 0
    NAMES_T = ["Ivan", "Kemal", "Dragan", "Yusuf", "Marko", "Rashid", "Zoran"]
    NAMES_CT = ["Miller", "Hoyt", "Dax", "Rico", "Lars", "Nadia", "Cole"]

    def __init__(self, x, y, team, skill, wep_key):
        Bot.ID += 1
        self.id = Bot.ID
        self.x, self.y = x, y
        self.team = team
        self.ang = random.uniform(-math.pi, math.pi)
        self.hp = 100
        self.armor = 100 if random.random() < 0.7 else 0
        self.alive = True
        self.skill = skill                       # 0..1
        self.slot = Slot(wep_key)
        self.state = 'roam'
        self.target = None
        self.path = []
        self.path_t = random.uniform(0, 0.5)
        self.goal_cell = None
        self.react = 0.0
        self.cd = 0.0
        self.reload_t = 0.0
        self.burst = 0
        self.burst_pause = 0.0
        self.anim = 0.0
        self.pose = 0
        self.rect = None                         # ekran dikdörtgeni (vuruş testi)
        self.depth = 999.0
        self.last_seen = None
        self.alert = 0.0
        self.strafe_dir = random.choice((-1, 1))
        self.strafe_t = 0.0
        self.has_bomb = False
        self.planting = 0.0
        self.defusing = 0.0
        self.death_t = 0.0
        self.name = (random.choice(self.NAMES_T if team == 'T' else self.NAMES_CT)
                     + " " + str(random.randint(1, 99)))
        self.kills = 0
        self.deaths = 0
        self.speed = 2.6 + skill * 0.9

    # ---------- algı
    def can_see(self, tx, ty, fov=2.1):
        d = math.hypot(tx - self.x, ty - self.y)
        if d > 26:
            return False
        a = math.atan2(ty - self.y, tx - self.x)
        if abs(ang_diff(a, self.ang)) > fov * 0.5 and self.alert <= 0:
            return False
        return los(self.x, self.y, tx, ty)

    def pick_target(self, world):
        best, bd = None, 1e9
        for e in world.enemies_of(self.team):
            if not e.alive:
                continue
            d = math.hypot(e.x - self.x, e.y - self.y)
            if d < bd and self.can_see(e.x, e.y):
                best, bd = e, d
        return best

    # ---------- hareket
    def slide(self, dx, dy):
        r = BOT_R
        nx = self.x + dx
        if not (solid(nx + math.copysign(r, dx), self.y + r) or
                solid(nx + math.copysign(r, dx), self.y - r)):
            self.x = nx
        ny = self.y + dy
        if not (solid(self.x + r, ny + math.copysign(r, dy)) or
                solid(self.x - r, ny + math.copysign(r, dy))):
            self.y = ny

    def face(self, tx, ty, dt, rate=6.5):
        a = math.atan2(ty - self.y, tx - self.x)
        self.ang += clamp(ang_diff(a, self.ang), -rate * dt, rate * dt)

    def repath(self, gx, gy):
        self.goal_cell = (int(gx), int(gy))
        self.path = astar((int(self.x), int(self.y)), self.goal_cell)
        if len(self.path) > 1:
            self.path.pop(0)

    def follow_path(self, dt, speed_mul=1.0):
        if not self.path:
            return False
        cx, cy = self.path[0]
        tx, ty = cx + 0.5, cy + 0.5
        d = math.hypot(tx - self.x, ty - self.y)
        if d < 0.34:
            self.path.pop(0)
            return True
        sp = self.speed * speed_mul
        self.slide((tx - self.x) / d * sp * dt, (ty - self.y) / d * sp * dt)
        self.face(tx, ty, dt, 5.0)
        self.anim += dt * sp
        return True

    # ---------- ana güncelleme
    def update(self, dt, world):
        if not self.alive:
            self.death_t += dt
            return
        self.cd -= dt
        self.alert -= dt
        self.strafe_t -= dt
        self.burst_pause -= dt
        self.path_t -= dt
        if self.reload_t > 0:
            self.reload_t -= dt
            if self.reload_t <= 0:
                need = self.slot.w.mag - self.slot.ammo
                take = min(need, self.slot.reserve)
                self.slot.ammo += take
                self.slot.reserve -= take

        tgt = self.pick_target(world)
        if tgt:
            self.target = tgt
            self.last_seen = (tgt.x, tgt.y)
            self.alert = 5.0
            self.state = 'fight'
        elif self.state == 'fight':
            self.state = 'hunt' if self.last_seen else 'roam'

        if self.state == 'fight':
            self._fight(dt, world)
        elif self.state == 'hunt':
            self._hunt(dt, world)
        else:
            self._objective(dt, world)

        # animasyon poz seçimi
        if self.state == 'fight' and self.cd > self.slot.w.interval * 0.55:
            self.pose = 3
        else:
            self.pose = [0, 1, 0, 2][int(self.anim * 2.2) % 4]

    def _fight(self, dt, world):
        t = self.target
        self.face(t.x, t.y, dt, 7.5)
        d = math.hypot(t.x - self.x, t.y - self.y)
        w = self.slot.w
        # mesafe yönetimi + strafe
        if self.strafe_t <= 0:
            self.strafe_t = random.uniform(0.5, 1.3)
            self.strafe_dir = random.choice((-1, 1))
        ideal = 2.0 if w.kind == 'knife' else (11.0 if w.kind == 'sniper' else 6.0)
        push = clamp((d - ideal) * 0.6, -1.0, 1.0)
        mv = self.speed * (0.55 + 0.3 * self.skill)
        fx = math.cos(self.ang) * push * mv
        fy = math.sin(self.ang) * push * mv
        sx = math.cos(self.ang + math.pi / 2) * self.strafe_dir * mv * 0.6
        sy = math.sin(self.ang + math.pi / 2) * self.strafe_dir * mv * 0.6
        self.slide((fx + sx) * dt, (fy + sy) * dt)
        self.anim += dt * mv

        if self.reload_t > 0:
            return
        if self.slot.ammo <= 0:
            if self.slot.reserve > 0:
                self.reload_t = w.reload_t
                world.audio.play('reload', world.dist_to_player(self))
            return
        # tepki süresi
        if self.react <= 0:
            self.react = random.uniform(0.42, 0.95) * (1.25 - self.skill)
        else:
            self.react -= dt
            return
        if w.kind == 'knife':
            if d < 1.7 and self.cd <= 0:
                self.cd = w.interval
                t.take_damage(w.dmg, self.x, self.y, world, self) if isinstance(t, Player) \
                    else world.hurt_bot(t, w.dmg, self)
            return
        if self.cd > 0 or self.burst_pause > 0:
            return
        # namlu açısına gelmeden ateş etmesin
        if abs(ang_diff(math.atan2(t.y - self.y, t.x - self.x), self.ang)) > 0.16:
            return
        self.shoot(world, t, d)

    def shoot(self, world, t, d):
        w = self.slot.w
        self.cd = w.interval
        self.slot.ammo -= 1
        world.audio.play(w.snd, world.dist_to_player(self))
        world.noise(self.x, self.y, self, 22.0)
        # seri kontrolü
        self.burst += 1
        if (w.auto and self.burst >= random.randint(3, 7)) or not w.auto:
            self.burst = 0
            self.burst_pause = random.uniform(0.14, 0.45) * (1.4 - self.skill)
        # isabet olasılığı
        acc = (0.30 + 0.60 * self.skill) * clamp(1.25 - d / w.rng * 1.15, 0.12, 1.0)
        moving = math.hypot(*getattr(t, 'vel', (0, 0))) > 1.0
        if moving:
            acc *= 0.72
        if w.kind == 'sniper':
            acc *= 1.25
        tz = 0.45
        if random.random() < acc:
            head = random.random() < 0.12 + 0.22 * self.skill
            dmg = w.dmg * (3.6 if head else 1.0)
            dmg *= clamp(1.15 - d / w.rng * 0.55, 0.35, 1.0)
            if isinstance(t, Player):
                t.take_damage(dmg, self.x, self.y, world, self, head)
            else:
                world.hurt_bot(t, dmg, self)
            tz = 0.75 if head else 0.5
            world.particles.append(Particle(t.x, t.y, tz, random.uniform(-.6, .6),
                                            random.uniform(-.6, .6), 1.0, 0.35,
                                            world.art.blood, 0.22))
        else:
            tz = 0.45 + random.uniform(-0.35, 0.55)
        world.tracers.append(Tracer(self.x, self.y, 0.45, t.x, t.y, tz,
                                    col=(255, 200, 110)))
        world.particles.append(Particle(self.x + math.cos(self.ang) * 0.4,
                                        self.y + math.sin(self.ang) * 0.4, 0.5,
                                        0, 0, 0, 0.05, world.art.spark, 0.18, 0))

    def _hunt(self, dt, world):
        if self.path_t <= 0 or not self.path:
            self.path_t = random.uniform(0.5, 0.9)
            if self.last_seen:
                self.repath(*self.last_seen)
        if not self.follow_path(dt, 0.95):
            self.last_seen = None
            self.state = 'roam'

    def _objective(self, dt, world):
        bomb = world.bomb
        # ---- T tarafı: bombayı siteye götür / kur
        if self.team == 'T':
            if bomb.state == 'planted':
                # bombayı koru: site çevresinde bekle
                self._guard(dt, world, SITE_CENTER)
                return
            if self.has_bomb:
                cx, cy = int(self.x), int(self.y)
                if (cx, cy) in SITE_CELLS:
                    self.planting += dt
                    self.anim = 0
                    world.hud_note = f"{self.name} bombayı kuruyor..."
                    if self.planting >= PLANT_TIME:
                        world.plant_bomb(self)
                    return
                if self.path_t <= 0 or not self.path:
                    self.path_t = 0.8
                    self.repath(*SITE_CENTER)
                self.follow_path(dt, 1.0)
            elif bomb.state == 'ground':
                if self.path_t <= 0 or not self.path:
                    self.path_t = 0.7
                    self.repath(bomb.x, bomb.y)
                self.follow_path(dt, 1.1)
            else:
                if self.path_t <= 0 or not self.path:
                    self.path_t = random.uniform(0.9, 1.6)
                    gx, gy = SITE_CENTER
                    self.repath(gx + random.uniform(-3, 3), gy + random.uniform(-2, 3))
                self.follow_path(dt, 1.0)
            return
        # ---- CT tarafı: siteyi tut / defuse et
        if bomb.state == 'planted':
            d = math.hypot(bomb.x - self.x, bomb.y - self.y)
            if d < 0.85:
                self.defusing += dt
                world.hud_note = f"{self.name} bombayı defuse ediyor..."
                if self.defusing >= DEFUSE_TIME:
                    world.defuse_bomb(self)
                return
            self.defusing = 0.0
            if self.path_t <= 0 or not self.path:
                self.path_t = 0.7
                self.repath(bomb.x, bomb.y)
            self.follow_path(dt, 1.1)
            return
        self._guard(dt, world, SITE_CENTER)

    def _guard(self, dt, world, center):
        if self.path_t <= 0 or not self.path:
            self.path_t = random.uniform(1.4, 2.8)
            gx = center[0] + random.uniform(-5, 5)
            gy = center[1] + random.uniform(-4, 6)
            self.repath(clamp(gx, 1, MW - 2), clamp(gy, 1, MH - 2))
        if not self.follow_path(dt, 0.8):
            self.ang += dt * 0.7

    def hear(self, x, y, loud):
        d = math.hypot(x - self.x, y - self.y)
        if d < loud:
            self.alert = 4.0
            self.last_seen = (x, y)
            if self.state == 'roam':
                self.state = 'hunt'
                self.path = []
                self.path_t = 0


# --------------------------------------------------------------------- #
#  RENDERER  (raycast + billboard sprite)
# --------------------------------------------------------------------- #
class Renderer:
    def __init__(self, art):
        self.art = art
        self.rs = pygame.Surface((RW, RH)).convert()
        self.depth = [MAXD] * RW
        self.cache = {}
        self.cam = None

    # ---- kamera matrisini hazırla
    def set_cam(self, x, y, ang, pitch, dz, fov):
        f = math.radians(fov)
        pl = math.tan(f / 2)
        dirx, diry = math.cos(ang), math.sin(ang)
        self.cam = dict(x=x, y=y, ang=ang, pitch=pitch, dz=dz,
                        dirx=dirx, diry=diry,
                        planex=-diry * pl, planey=dirx * pl)

    def project(self, wx, wy, wz):
        """Dünya noktasını ekrana çevir -> (sx, sy, depth) ya da None"""
        c = self.cam
        dx, dy = wx - c['x'], wy - c['y']
        det = c['planex'] * c['diry'] - c['dirx'] * c['planey']
        if abs(det) < 1e-9:
            return None
        inv = 1.0 / det
        tx = inv * (c['diry'] * dx - c['dirx'] * dy)
        ty = inv * (-c['planey'] * dx + c['planex'] * dy)
        if ty < 0.08:
            return None
        unit = RH / ty
        sx = (RW * 0.5) * (1.0 + tx / ty)
        floor_y = HALF_RH + c['pitch'] + c['dz'] * unit + unit * 0.5
        sy = floor_y - wz * unit
        return sx, sy, ty

    # ---- duvarlar
    def cast_walls(self):
        c = self.cam
        surf = self.rs
        surf.blit(self.art.bg, (0, 0))
        px, py = c['x'], c['y']
        mx0, my0 = int(px), int(py)
        texcols = self.art.texcols
        cache = self.cache
        pitch = c['pitch']
        dz = c['dz']
        if len(cache) > 13000:
            for k in list(_islice(cache, 1400)):
                del cache[k]
        for x in range(RW):
            camx = 2.0 * x / RW - 1.0
            rdx = c['dirx'] + c['planex'] * camx
            rdy = c['diry'] + c['planey'] * camx
            mx, my = mx0, my0
            ddx = 1e30 if rdx == 0 else abs(1.0 / rdx)
            ddy = 1e30 if rdy == 0 else abs(1.0 / rdy)
            if rdx < 0:
                stepx = -1; sdx = (px - mx) * ddx
            else:
                stepx = 1; sdx = (mx + 1.0 - px) * ddx
            if rdy < 0:
                stepy = -1; sdy = (py - my) * ddy
            else:
                stepy = 1; sdy = (my + 1.0 - py) * ddy
            side = 0
            hit = False
            for _ in range(96):
                if sdx < sdy:
                    sdx += ddx; mx += stepx; side = 0
                else:
                    sdy += ddy; my += stepy; side = 1
                if mx < 0 or my < 0 or mx >= MW or my >= MH:
                    break
                if MAP[my][mx] in SOLID:
                    hit = True
                    break
            if not hit:
                self.depth[x] = MAXD
                continue
            perp = (sdx - ddx) if side == 0 else (sdy - ddy)
            if perp < 0.06:
                perp = 0.06
            self.depth[x] = perp
            if side == 0:
                wall = py + perp * rdy
            else:
                wall = px + perp * rdx
            wall -= math.floor(wall)
            texx = int(wall * TEX)
            if (side == 0 and rdx > 0) or (side == 1 and rdy < 0):
                texx = TEX - texx - 1
            texx = 0 if texx < 0 else (TEX - 1 if texx > TEX - 1 else texx)
            tid = TEX_OF.get(MAP[my][mx], 0)
            sh = int(perp / 3.4) + (1 if side == 1 else 0)
            if sh > SHADES - 1:
                sh = SHADES - 1
            unit = RH / perp
            lineh = int(unit)
            if lineh < 1:
                lineh = 1
            elif lineh > 40:                      # cache anahtarlarını azalt
                st = lineh >> 5
                lineh -= lineh % st
            floor_y = HALF_RH + pitch + dz * unit + unit * 0.5
            top = int(floor_y - lineh)
            key = (tid, sh, texx, lineh)
            col = cache.get(key)
            if col is None:
                col = pygame.transform.scale(texcols[tid][sh][texx], (1, lineh))
                cache[key] = col
            surf.blit(col, (x, top))

    # ---- billboard
    def billboard(self, img, wx, wy, zoff, height, alpha=255):
        p = self.project(wx, wy, zoff)
        if p is None:
            return None
        sx, _, ty = p
        unit = RH / ty
        h = int(height * unit)
        if h < 1:
            return None
        w = int(h * img.get_width() / img.get_height())
        if w < 1:
            w = 1
        if h > 2600:
            return None
        c = self.cam
        floor_y = HALF_RH + c['pitch'] + c['dz'] * unit + unit * 0.5
        bottom = floor_y - zoff * unit
        top = int(bottom - h)
        x0 = int(sx - w * 0.5)
        if x0 + w < 0 or x0 >= RW:
            return None
        key = (id(img), w, h, alpha)
        sc = self.cache.get(key)
        if sc is None:
            sc = pygame.transform.scale(img, (w, h))
            if alpha < 255:
                sc = sc.copy()
                sc.set_alpha(alpha)
            self.cache[key] = sc
        # z-buffer testli sütun blokları
        surf = self.rs
        dbuf = self.depth
        run = -1
        i = 0
        while i < w:
            sxx = x0 + i
            vis = 0 <= sxx < RW and dbuf[sxx] > ty
            if vis:
                if run < 0:
                    run = i
            elif run >= 0:
                surf.blit(sc, (x0 + run, top), (run, 0, i - run, h))
                run = -1
            i += 1
        if run >= 0:
            surf.blit(sc, (x0 + run, top), (run, 0, w - run, h))
        return (x0, top, w, h, ty)

    def draw_tracer(self, tr):
        a = self.project(*tr.a)
        b = self.project(*tr.b)
        if a is None or b is None:
            return
        try:
            pygame.draw.line(self.rs, tr.col, (int(a[0]), int(a[1])),
                             (int(b[0]), int(b[1])), 1)
        except Exception:
            pass

    # ---- tüm sahne
    def render(self, world):
        p = world.player
        cam_ang = p.ang
        cam_pitch = p.pitch
        sh = 0.0
        if p.shake > 0:
            sh = p.shake
            cam_ang += random.uniform(-0.02, 0.02) * sh
            cam_pitch += random.uniform(-6, 6) * sh
        fov = BASE_FOV * (0.34 if (p.zoom and p.wep.kind == 'sniper') else 1.0)
        bob = math.sin(p.bob * 2.0) * 0.012 if p.alive else 0.0
        self.set_cam(p.x, p.y, cam_ang, cam_pitch, p.eye() - 0.5 + bob, fov)
        self.cast_walls()

        # sıralanacak nesneler
        items = []
        for b in world.bots:
            d = (b.x - p.x) ** 2 + (b.y - p.y) ** 2
            items.append((d, 'bot', b))
        if world.bomb.state in ('planted', 'ground'):
            d = (world.bomb.x - p.x) ** 2 + (world.bomb.y - p.y) ** 2
            items.append((d, 'bomb', world.bomb))
        for g in world.grenades:
            items.append(((g.x - p.x) ** 2 + (g.y - p.y) ** 2, 'nade', g))
        for pa in world.particles:
            items.append(((pa.x - p.x) ** 2 + (pa.y - p.y) ** 2, 'part', pa))
        items.sort(key=lambda i: -i[0])

        for _, kind, o in items:
            if kind == 'bot':
                if o.alive:
                    img = self.art.soldier[o.team][o.pose]
                    r = self.billboard(img, o.x, o.y, 0.0, 1.05)
                    o.rect = r
                    o.depth = r[4] if r else 999.0
                else:
                    o.rect = None
                    fall = min(1.0, o.death_t * 3.0)
                    self.billboard(self.art.corpse[o.team], o.x, o.y, 0.0,
                                   0.16 + 0.06 * (1 - fall))
            elif kind == 'bomb':
                lit = int(world.time * 4) % 2 == 0 if o.state == 'planted' else 0
                self.billboard(self.art.bomb[1 if lit else 0], o.x, o.y, 0.02, 0.22)
            elif kind == 'nade':
                self.billboard(self.art.nade, o.x, o.y, o.z, 0.12)
            else:
                a = int(255 * clamp(o.life / max(0.01, o.t0), 0, 1))
                self.billboard(o.img, o.x, o.y, o.z, o.scale, a)

        for tr in world.tracers:
            self.draw_tracer(tr)
        return self.rs


# --------------------------------------------------------------------- #
#  HUD
# --------------------------------------------------------------------- #
class Hud:
    def __init__(self):
        self.f_s = pygame.font.Font(None, 20)
        self.f_m = pygame.font.Font(None, 26)
        self.f_l = pygame.font.Font(None, 40)
        self.f_xl = pygame.font.Font(None, 70)

    def txt(self, s, t, x, y, col=C_TXT, font=None, center=False, shadow=True):
        f = font or self.f_m
        img = f.render(t, True, col)
        r = img.get_rect()
        if center:
            r.center = (x, y)
        else:
            r.topleft = (x, y)
        if shadow:
            sh = f.render(t, True, (0, 0, 0))
            s.blit(sh, (r.x + 2, r.y + 2))
        s.blit(img, r)
        return r

    # ---------------- silah modeli (viewmodel)
    def viewmodel(self, s, p, t):
        if not p.alive:
            return
        w = p.wep
        if p.zoom and w.kind == 'sniper':
            return
        sway_x = math.sin(p.bob) * 14
        sway_y = abs(math.cos(p.bob)) * 9
        kick = clamp((p.cd / max(0.001, w.interval)), 0, 1)
        rec = kick * (10 + w.recoil * 6)
        bx = WIN_W * 0.56 + sway_x
        by = WIN_H + 30 + sway_y + rec
        if p.reloading > 0:
            by += 130 * math.sin(math.pi * clamp(1 - p.reloading / w.reload_t, 0, 1)) ** 0.5
        dk = (34, 34, 38); md = (58, 58, 64); lt = (92, 92, 100)
        wood = (96, 64, 38)
        if w.kind == 'knife':
            pts = [(bx, by - 40), (bx + 30, by - 170), (bx + 52, by - 158),
                   (bx + 34, by - 30), (bx + 10, by - 20)]
            pygame.draw.polygon(s, (176, 180, 190), pts)
            pygame.draw.polygon(s, dk, pts, 3)
            pygame.draw.rect(s, dk, (bx - 6, by - 46, 44, 46), border_radius=6)
        elif w.kind == 'pistol':
            pygame.draw.rect(s, dk, (bx, by - 120, 46, 96), border_radius=6)
            pygame.draw.rect(s, md, (bx + 10, by - 190, 30, 78), border_radius=4)
            pygame.draw.rect(s, lt, (bx + 16, by - 205, 12, 20))
        elif w.kind == 'sniper':
            pygame.draw.rect(s, wood, (bx - 30, by - 130, 120, 54), border_radius=8)
            pygame.draw.rect(s, dk, (bx + 60, by - 122, 190, 22), border_radius=6)
            pygame.draw.rect(s, md, (bx + 6, by - 176, 96, 26), border_radius=6)
            pygame.draw.circle(s, (20, 20, 24), (int(bx + 40), int(by - 188)), 15)
            pygame.draw.rect(s, dk, (bx + 20, by - 78, 26, 60), border_radius=4)
        elif w.kind == 'smg':
            pygame.draw.rect(s, dk, (bx, by - 118, 150, 44), border_radius=6)
            pygame.draw.rect(s, md, (bx + 130, by - 110, 90, 16), border_radius=4)
            pygame.draw.rect(s, dk, (bx + 26, by - 80, 24, 76), border_radius=3)
        else:  # rifle
            body = wood if w.key == 'ak' else (44, 46, 50)
            pygame.draw.rect(s, body, (bx - 40, by - 126, 210, 50), border_radius=7)
            pygame.draw.rect(s, dk, (bx + 150, by - 118, 150, 20), border_radius=5)
            pygame.draw.rect(s, md, (bx + 40, by - 84, 34, 84), border_radius=4)
            pygame.draw.rect(s, dk, (bx + 96, by - 150, 40, 28), border_radius=4)
            pygame.draw.rect(s, lt, (bx + 250, by - 122, 22, 24), border_radius=3)
        # namlu alevi
        if kick > 0.62 and w.kind != 'knife':
            mx = bx + (300 if w.kind == 'rifle' else 230)
            my = by - (112 if w.kind != 'pistol' else 200)
            r = 26 + 18 * random.random()
            fl = pygame.Surface((int(r * 4), int(r * 4)), pygame.SRCALPHA)
            pygame.draw.circle(fl, (255, 220, 130, 190), (int(r * 2), int(r * 2)), int(r))
            pygame.draw.circle(fl, (255, 150, 60, 120), (int(r * 2), int(r * 2)), int(r * 1.7))
            s.blit(fl, (mx - r * 2, my - r * 2))

    # ---------------- nişangah
    def crosshair(self, s, p, spread_rad, fov):
        cx, cy = WIN_W // 2, WIN_H // 2
        if p.zoom and p.wep.kind == 'sniper':
            pygame.draw.line(s, (0, 0, 0), (0, cy), (WIN_W, cy), 2)
            pygame.draw.line(s, (0, 0, 0), (cx, 0), (cx, WIN_H), 2)
            pygame.draw.circle(s, (0, 0, 0), (cx, cy), 240, 6)
            ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            pygame.draw.rect(ov, (0, 0, 0, 235), (0, 0, WIN_W, WIN_H))
            pygame.draw.circle(ov, (0, 0, 0, 0), (cx, cy), 238)
            s.blit(ov, (0, 0))
            return
        px_per_rad = (WIN_W * 0.5) / math.tan(math.radians(fov) / 2)
        gap = int(6 + spread_rad * px_per_rad * 0.5)
        gap = min(gap, 120)
        col = (60, 240, 120) if p.alive else (200, 200, 200)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            x0 = cx + dx * gap; y0 = cy + dy * gap
            pygame.draw.line(s, (0, 0, 0), (x0 + dx, y0 + dy),
                             (x0 + dx * 10, y0 + dy * 10), 4)
            pygame.draw.line(s, col, (x0, y0), (x0 + dx * 9, y0 + dy * 9), 2)
        pygame.draw.circle(s, col, (cx, cy), 1)
        if p.hitmark > 0:
            for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
                pygame.draw.line(s, (255, 90, 80), (cx + dx * 7, cy + dy * 7),
                                 (cx + dx * 16, cy + dy * 16), 3)

    # ---------------- radar
    def _radar_bg(self, S, sc):
        if getattr(self, '_rbg', None) is not None:
            return self._rbg
        pan = pygame.Surface((S, S), pygame.SRCALPHA)
        pan.fill((8, 12, 16, 165))
        for y in range(MH):
            for x in range(MW):
                ch = MAP[y][x]
                if ch in SOLID:
                    c = (74, 80, 88) if ch != 'c' else (110, 80, 46)
                    pygame.draw.rect(pan, c, (x * sc, y * sc, sc + 1, sc + 1))
                elif ch == 'A':
                    pygame.draw.rect(pan, (170, 60, 50, 130), (x * sc, y * sc, sc + 1, sc + 1))
        self._rbg = pan
        return pan

    def radar(self, s, world):
        S = 190
        ox, oy = WIN_W - S - 18, 18
        sc = S / max(MW, MH)
        pan = self._radar_bg(S, sc).copy()
        p = world.player
        for b in world.bots:
            if not b.alive:
                continue
            vis = b.team == p.team or (los(p.x, p.y, b.x, b.y) and p.alive)
            if not vis:
                continue
            col = C_CT if b.team == 'CT' else C_BAD
            pygame.draw.circle(pan, col, (int(b.x * sc), int(b.y * sc)), 3)
        bm = world.bomb
        if bm.state in ('planted', 'ground'):
            fl = (255, 70, 50) if int(world.time * 4) % 2 == 0 else (140, 40, 30)
            pygame.draw.circle(pan, fl, (int(bm.x * sc), int(bm.y * sc)), 4)
        pygame.draw.circle(pan, (250, 250, 250), (int(p.x * sc), int(p.y * sc)), 4)
        tip = (p.x + math.cos(p.ang) * 1.6, p.y + math.sin(p.ang) * 1.6)
        pygame.draw.line(pan, (250, 250, 250), (p.x * sc, p.y * sc),
                         (tip[0] * sc, tip[1] * sc), 2)
        pygame.draw.rect(pan, (150, 150, 160, 200), (0, 0, S, S), 2)
        s.blit(pan, (ox, oy))
        return oy + S

    # ---------------- ana HUD
    def draw(self, s, world, fps):
        p = world.player
        # hasar / kan efektleri
        if p.hurt_flash > 0:
            ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            a = int(140 * clamp(p.hurt_flash, 0, 1))
            pygame.draw.rect(ov, (160, 20, 16, a), (0, 0, WIN_W, WIN_H), 90)
            s.blit(ov, (0, 0))
        if p.hp < 40 and p.alive:
            ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            a = int(90 * (1 - p.hp / 40.0))
            pygame.draw.rect(ov, (120, 10, 10, a), (0, 0, WIN_W, WIN_H), 140)
            s.blit(ov, (0, 0))

        self.viewmodel(s, p, world.time)
        fov = BASE_FOV * (0.34 if (p.zoom and p.wep.kind == 'sniper') else 1.0)
        self.crosshair(s, p, world.player_spread(), fov)
        bottom_radar = self.radar(s, world)

        # sağlık / zırh
        pygame.draw.rect(s, (0, 0, 0, 120), (24, WIN_H - 92, 300, 68))
        col = C_HP if p.hp > 40 else C_BAD
        self.txt(s, f"{p.hp}", 34, WIN_H - 88, col, self.f_xl)
        self.txt(s, "HP", 112, WIN_H - 56, (150, 150, 150), self.f_s)
        self.txt(s, f"{p.armor}", 150, WIN_H - 84, C_CT, self.f_l)
        self.txt(s, "KEVLAR" + ("+H" if p.helmet else ""), 150, WIN_H - 48,
                 (150, 150, 150), self.f_s)
        self.txt(s, f"${p.money}", 34, WIN_H - 122, (120, 220, 130), self.f_l)

        # cephane
        sl = p.slot
        amm = "-" if sl.w.kind == 'knife' else f"{sl.ammo}"
        self.txt(s, amm, WIN_W - 210, WIN_H - 92, C_TXT, self.f_xl)
        if sl.w.kind != 'knife':
            self.txt(s, f"/ {sl.reserve}", WIN_W - 120, WIN_H - 62, (170, 170, 170), self.f_m)
        self.txt(s, sl.w.name, WIN_W - 210, WIN_H - 122, C_ACC, self.f_m)
        if p.nades:
            self.txt(s, f"HE x{p.nades}  [G]", WIN_W - 210, WIN_H - 26,
                     (170, 200, 170), self.f_s)
        if p.reloading > 0:
            self.txt(s, "ŞARJÖR DEĞİŞTİRİLİYOR", WIN_W // 2, WIN_H - 150,
                     C_ACC, self.f_m, center=True)
        elif sl.ammo == 0 and sl.w.kind != 'knife':
            self.txt(s, "[R] ŞARJÖR", WIN_W // 2, WIN_H - 150, C_BAD, self.f_m, center=True)

        # üst bar: skor + süre
        pygame.draw.rect(s, (10, 12, 16), (WIN_W // 2 - 190, 0, 380, 52))
        pygame.draw.rect(s, (60, 64, 72), (WIN_W // 2 - 190, 0, 380, 52), 2)
        self.txt(s, f"{world.score['CT']}", WIN_W // 2 - 150, 8, C_CT, self.f_l, center=True)
        self.txt(s, f"{world.score['T']}", WIN_W // 2 + 150, 8, C_T, self.f_l, center=True)
        if world.bomb.state == 'planted':
            tl = max(0.0, world.bomb.timer)
            self.txt(s, f"{tl:04.1f}", WIN_W // 2, 20, (255, 70, 50), self.f_l, center=True)
            self.txt(s, "BOMBA KURULDU", WIN_W // 2, 66, (255, 90, 60), self.f_m, center=True)
        else:
            tl = max(0.0, world.phase_t)
            self.txt(s, f"{int(tl)//60}:{int(tl)%60:02d}", WIN_W // 2, 20,
                     C_TXT, self.f_l, center=True)
        self.txt(s, f"Round {world.round_no}", WIN_W // 2, 60, (150, 150, 160),
                 self.f_s, center=True)

        # kill feed
        y = bottom_radar + 8
        for (txt, col, _) in world.feed[-6:]:
            img = self.f_s.render(txt, True, col)
            s.blit(img, (WIN_W - 24 - img.get_width(), y))
            y += 22

        # notlar
        if world.hud_note:
            self.txt(s, world.hud_note, WIN_W // 2, WIN_H - 210, C_ACC,
                     self.f_m, center=True)
        if p.defusing > 0:
            f = clamp(p.defusing / DEFUSE_TIME, 0, 1)
            pygame.draw.rect(s, (30, 30, 34), (WIN_W // 2 - 160, WIN_H - 260, 320, 24))
            pygame.draw.rect(s, (70, 200, 240), (WIN_W // 2 - 158, WIN_H - 258,
                                                 int(316 * f), 20))
            self.txt(s, "DEFUSE EDİLİYOR", WIN_W // 2, WIN_H - 288, (70, 200, 240),
                     self.f_m, center=True)
        elif world.bomb.state == 'planted' and p.alive and \
                math.hypot(world.bomb.x - p.x, world.bomb.y - p.y) < 1.0:
            self.txt(s, "[E] BASILI TUT — DEFUSE", WIN_W // 2, WIN_H - 260,
                     (70, 200, 240), self.f_m, center=True)

        if not p.alive and world.phase == 'live':
            self.txt(s, "ÖLDÜN — izliyorsun", WIN_W // 2, 120, C_BAD, self.f_l, center=True)

        # freeze / round sonu / satın alma
        if world.phase == 'freeze':
            self.txt(s, f"HAZIRLIK  {world.phase_t:0.0f}", WIN_W // 2, 150,
                     C_ACC, self.f_l, center=True)
            if not world.buy_open:
                self.txt(s, "[B] SATIN ALMA MENÜSÜ", WIN_W // 2, 195,
                         (200, 200, 200), self.f_m, center=True)
        if world.phase == 'end':
            col = C_CT if world.last_winner == 'CT' else C_T
            self.txt(s, world.end_msg, WIN_W // 2, WIN_H // 2 - 60, col,
                     self.f_xl, center=True)
        if world.buy_open:
            self.buy_menu(s, world)
        if world.show_score:
            self.scoreboard(s, world)
        self.txt(s, f"{fps:0.0f} FPS", 24, 18, (120, 130, 140), self.f_s)

    def buy_menu(self, s, world):
        p = world.player
        W, H = 520, 420
        x, y = WIN_W // 2 - W // 2, WIN_H // 2 - H // 2
        pan = pygame.Surface((W, H), pygame.SRCALPHA)
        pan.fill((10, 14, 20, 235))
        pygame.draw.rect(pan, (90, 100, 115), (0, 0, W, H), 2)
        s.blit(pan, (x, y))
        self.txt(s, "SATIN ALMA", x + W // 2, y + 26, C_ACC, self.f_l, center=True)
        self.txt(s, f"Para: ${p.money}", x + W // 2, y + 62, (120, 220, 130),
                 self.f_m, center=True)
        yy = y + 96
        for i, key in enumerate(BUY_LIST):
            w = WEAPONS[key]
            afford = p.money >= w.price
            col = C_TXT if afford else (110, 110, 110)
            own = " (var)" if key in p.slots else ""
            self.txt(s, f"[{i+1}] {w.name}{own}", x + 30, yy, col, self.f_m)
            self.txt(s, f"${w.price}", x + W - 130, yy, (120, 200, 130) if afford
                     else (140, 90, 90), self.f_m)
            yy += 34
        afford = p.money >= ARMOR_PRICE
        self.txt(s, f"[7] Kevlar + Kask", x + 30, yy, C_TXT if afford else (110, 110, 110),
                 self.f_m)
        self.txt(s, f"${ARMOR_PRICE}", x + W - 130, yy, (120, 200, 130), self.f_m)
        yy += 34
        self.txt(s, f"[8] HE Bombası", x + 30, yy, C_TXT, self.f_m)
        self.txt(s, f"${NADE_PRICE}", x + W - 130, yy, (120, 200, 130), self.f_m)
        self.txt(s, "[B] kapat", x + W // 2, y + H - 30, (170, 170, 170),
                 self.f_s, center=True)

    def scoreboard(self, s, world):
        W, H = 720, 440
        x, y = WIN_W // 2 - W // 2, WIN_H // 2 - H // 2
        pan = pygame.Surface((W, H), pygame.SRCALPHA)
        pan.fill((8, 10, 14, 232))
        pygame.draw.rect(pan, (90, 100, 115), (0, 0, W, H), 2)
        s.blit(pan, (x, y))
        self.txt(s, f"CT {world.score['CT']}  -  {world.score['T']} T",
                 x + W // 2, y + 20, C_ACC, self.f_l, center=True)
        rows = [('CT', 'SEN', world.player.kills, world.player.deaths,
                 world.player.alive)]
        for b in world.bots:
            rows.append((b.team, b.name, b.kills, b.deaths, b.alive))
        yy = y + 70
        for team in ('CT', 'T'):
            self.txt(s, f"--- {team} ---", x + 30, yy,
                     C_CT if team == 'CT' else C_T, self.f_m)
            yy += 28
            for (t, nm, k, d, al) in rows:
                if t != team:
                    continue
                col = C_TXT if al else (110, 110, 110)
                self.txt(s, nm, x + 50, yy, col, self.f_s)
                self.txt(s, f"{k}", x + 420, yy, col, self.f_s)
                self.txt(s, f"{d}", x + 500, yy, col, self.f_s)
                yy += 22
            yy += 10


# --------------------------------------------------------------------- #
#  BOMBA + GİRDİ
# --------------------------------------------------------------------- #
class Bomb:
    def __init__(self):
        self.state = 'carried'      # carried | ground | planted | defused | exploded
        self.x = self.y = 0.0
        self.timer = BOMB_TIME
        self.carrier = None
        self.beep_t = 0.0

    def reset(self):
        self.state = 'carried'
        self.timer = BOMB_TIME
        self.carrier = None
        self.beep_t = 0.0


class Inp:
    __slots__ = ('fwd', 'strafe', 'mdx', 'mdy', 'fire', 'click', 'alt', 'walk',
                 'crouch', 'jump', 'use', 'reload', 'nade', 'keys', 'tab')

    def __init__(self):
        self.fwd = self.strafe = 0.0
        self.mdx = self.mdy = 0.0
        self.fire = self.click = self.alt = False
        self.walk = self.crouch = self.jump = self.use = False
        self.reload = self.nade = self.tab = False
        self.keys = []


# --------------------------------------------------------------------- #
#  OYUN / DÜNYA
# --------------------------------------------------------------------- #
class Game:
    def __init__(self, screen, test=False, sens=0.0035):
        self.screen = screen
        self.test = test
        self.sens = sens
        self.art = Art()
        self.audio = Audio(enabled=not test)
        self.renderer = Renderer(self.art)
        self.hud = Hud()
        self.clock = pygame.time.Clock()
        self.player = Player(self.art)
        self.bots = []
        self.particles = []
        self.tracers = []
        self.grenades = []
        self.feed = []
        self.bomb = Bomb()
        self.time = 0.0
        self.phase = 'menu'
        self.phase_t = 0.0
        self.round_no = 0
        self.score = {'CT': 0, 'T': 0}
        self.buy_open = False
        self.show_score = False
        self.hud_note = ''
        self.end_msg = ''
        self.last_winner = 'CT'
        self.running = True
        self.frames = 0

    # ----------------------------------------------------------------- #
    #  yardımcılar
    # ----------------------------------------------------------------- #
    def enemies_of(self, team):
        out = []
        if team != self.player.team and self.player.alive:
            out.append(self.player)
        for b in self.bots:
            if b.alive and b.team != team:
                out.append(b)
        return out

    def allies_of(self, team):
        return [b for b in self.bots if b.alive and b.team == team]

    def dist_to_player(self, e):
        return math.hypot(e.x - self.player.x, e.y - self.player.y)

    def noise(self, x, y, src, loud):
        for b in self.bots:
            if b.alive and b is not src:
                b.hear(x, y, loud * (1.0 if b.team != getattr(src, 'team', '') else 0.35))

    def add_feed(self, killer, victim, wname, head):
        txt = f"{killer}  «{wname}»{' HS' if head else ''}  {victim}"
        self.feed.append((txt, C_ACC if killer == 'SEN' else (200, 200, 205), self.time))
        if len(self.feed) > 12:
            self.feed.pop(0)

    def player_spread(self):
        p = self.player
        moving = math.hypot(*p.vel) > 1.2
        return p.cur_spread(moving)

    # ----------------------------------------------------------------- #
    #  maç / round akışı
    # ----------------------------------------------------------------- #
    def start_match(self):
        self.score = {'CT': 0, 'T': 0}
        self.round_no = 0
        self.player = Player(self.art)
        self.feed = []
        self.start_round()

    def start_round(self):
        self.round_no += 1
        self.particles.clear(); self.tracers.clear(); self.grenades.clear()
        self.player.reset_round()
        self.bomb.reset()
        self.spawn_bots()
        self.phase = 'freeze'
        self.phase_t = FREEZE_TIME if not self.test else 0.6
        self.buy_open = False
        self.end_msg = ''

    def spawn_bots(self):
        self.bots = []
        pool_t = ['ak', 'ak', 'm4', 'mp9', 'deagle', 'awp']
        pool_ct = ['m4', 'm4', 'mp9', 'ak', 'awp']
        diff = clamp(0.42 + self.round_no * 0.035, 0.42, 0.9)
        for i in range(4):
            sp = T_SPAWNS[i % len(T_SPAWNS)] if T_SPAWNS else (2.5, 2.5)
            b = Bot(sp[0] + random.uniform(-.3, .3), sp[1] + random.uniform(-.3, .3),
                    'T', clamp(diff + random.uniform(-.12, .12), 0.15, 0.95),
                    random.choice(pool_t))
            self.bots.append(b)
        for i in range(2):
            sp = CT_SPAWNS[i % len(CT_SPAWNS)] if CT_SPAWNS else (30.5, 26.5)
            b = Bot(sp[0] + random.uniform(-.3, .3), sp[1] + random.uniform(-.3, .3),
                    'CT', clamp(diff + random.uniform(-.12, .12), 0.15, 0.95),
                    random.choice(pool_ct))
            self.bots.append(b)
        carrier = random.choice([b for b in self.bots if b.team == 'T'])
        carrier.has_bomb = True
        self.bomb.carrier = carrier
        self.bomb.x, self.bomb.y = carrier.x, carrier.y

    def end_round(self, winner, msg):
        if self.phase != 'live':
            return
        self.score[winner] += 1
        self.last_winner = winner
        self.end_msg = msg
        self.phase = 'end'
        self.phase_t = END_TIME if not self.test else 0.4
        p = self.player
        p.money = min(16000, p.money + (3250 if winner == 'CT' else 1400))

    def next_phase_after_end(self):
        if max(self.score.values()) >= MAX_SCORE:
            self.phase = 'gameover'
            self.end_msg = ("MAÇI KAZANDIN!" if self.score['CT'] > self.score['T']
                            else "MAÇI KAYBETTİN")
        else:
            self.start_round()

    # ----------------------------------------------------------------- #
    #  bomba olayları
    # ----------------------------------------------------------------- #
    def plant_bomb(self, bot):
        self.bomb.state = 'planted'
        self.bomb.x, self.bomb.y = bot.x, bot.y
        self.bomb.timer = BOMB_TIME
        bot.has_bomb = False
        bot.planting = 0.0
        self.feed.append(("BOMBA KURULDU!", (255, 90, 60), self.time))
        self.audio.play('beep', 0, 1.0)
        for b in self.bots:
            b.path = []; b.path_t = 0

    def defuse_bomb(self, who):
        self.bomb.state = 'defused'
        if isinstance(who, Player):
            who.money = min(16000, who.money + 300)
        self.end_round('CT', "BOMBA DEFUSE EDİLDİ")

    def explode_bomb(self):
        self.bomb.state = 'exploded'
        self.audio.play('boom', 0, 1.0)
        bx, by = self.bomb.x, self.bomb.y
        for _ in range(46):
            a = random.uniform(0, 6.28)
            self.particles.append(Particle(bx, by, 0.3, math.cos(a) * random.uniform(1, 7),
                                           math.sin(a) * random.uniform(1, 7),
                                           random.uniform(1, 5), random.uniform(0.5, 1.4),
                                           self.art.smoke, random.uniform(0.5, 1.6), 1.2))
        p = self.player
        if p.alive:
            p.shake = 0.9
            if math.hypot(bx - p.x, by - p.y) < 9:
                p.take_damage(500, bx, by, self)
        self.end_round('T', "BOMBA PATLADI")

    # ----------------------------------------------------------------- #
    #  hasar
    # ----------------------------------------------------------------- #
    def hurt_bot(self, bot, dmg, attacker, head=False):
        if not bot.alive:
            return
        if bot.armor > 0:
            bot.armor = max(0, bot.armor - int(dmg * 0.5))
            dmg *= 0.62
        bot.hp -= int(max(1, dmg))
        bot.alert = 5.0
        bot.last_seen = (attacker.x, attacker.y)
        if bot.state == 'roam':
            bot.state = 'hunt'
            bot.path = []; bot.path_t = 0
        if bot.hp <= 0:
            bot.alive = False
            bot.hp = 0
            bot.deaths += 1
            bot.death_t = 0.0
            self.audio.play('hurt', self.dist_to_player(bot), 0.6)
            for _ in range(8):
                a = random.uniform(0, 6.28)
                self.particles.append(Particle(bot.x, bot.y, 0.6,
                                               math.cos(a) * 1.5, math.sin(a) * 1.5,
                                               random.uniform(0.5, 2), 0.5,
                                               self.art.blood, 0.3))
            if bot.has_bomb:
                bot.has_bomb = False
                self.bomb.state = 'ground'
                self.bomb.x, self.bomb.y = bot.x, bot.y
                self.bomb.carrier = None
            self.on_death(bot, attacker)

    def on_death(self, victim, attacker):
        vn = 'SEN' if isinstance(victim, Player) else victim.name
        if attacker is None:
            self.add_feed("dünya", vn, "hasar", False)
            return
        if isinstance(attacker, Player):
            attacker.kills += 1
            attacker.money = min(16000, attacker.money +
                                 attacker.wep.kill_reward())
            self.add_feed('SEN', vn, attacker.wep.name, False)
            self.player.hitmark = 0.14
        else:
            attacker.kills += 1
            self.add_feed(attacker.name, vn, attacker.slot.w.name, False)

    # ----------------------------------------------------------------- #
    #  oyuncu ateşi
    # ----------------------------------------------------------------- #
    def start_reload(self):
        p = self.player
        s = p.slot
        if s.w.kind == 'knife' or p.reloading > 0:
            return
        if s.ammo >= s.w.mag or s.reserve <= 0:
            return
        p.reloading = s.w.reload_t
        p.zoom = False
        self.audio.play('reload', 0, 0.7)

    def try_fire(self, click):
        p = self.player
        if not p.alive or self.phase != 'live':
            return
        w = p.wep
        if p.reloading > 0 or p.cd > 0:
            return
        if w.kind == 'knife':
            if not click:
                return
            p.cd = w.interval
            self.audio.play('click', 0, 0.6)
            best, bd = None, 99
            for e in self.enemies_of(p.team):
                d = math.hypot(e.x - p.x, e.y - p.y)
                if d < 1.8 and abs(ang_diff(math.atan2(e.y - p.y, e.x - p.x), p.ang)) < 0.7:
                    if d < bd and los(p.x, p.y, e.x, e.y):
                        best, bd = e, d
            if best is not None:
                self.hurt_bot(best, w.dmg, p)
                p.hitmark = 0.12
                self.audio.play('hit', 0, 0.8)
            return
        if p.slot.ammo <= 0:
            if click:
                self.audio.play('click', 0, 0.5)
                self.start_reload()
            return
        if not w.auto and not click:
            return
        # --- ateş
        p.cd = w.interval
        p.slot.ammo -= 1
        self.audio.play(w.snd, 0, 1.0)
        self.noise(p.x, p.y, p, 24.0)
        kick = w.recoil * 2.4
        p.pitch += kick
        p.recoil += kick
        p.spread = min(3.2, p.spread + (0.85 if w.auto else 1.6))
        p.shake = min(0.35, p.shake + w.recoil * 0.02)
        self.hitscan()

    def hitscan(self):
        p = self.player
        w = p.wep
        fov = BASE_FOV * (0.34 if (p.zoom and w.kind == 'sniper') else 1.0)
        px_per_rad = (RW * 0.5) / math.tan(math.radians(fov) / 2)
        sp = self.player_spread()
        ax = RW * 0.5 + random.gauss(0, 0.6) * sp * px_per_rad
        ay = HALF_RH + random.gauss(0, 0.6) * sp * px_per_rad
        col = int(clamp(ax, 0, RW - 1))
        wall_d = self.renderer.depth[col]

        cands = [b for b in self.bots
                 if b.alive and b.team != p.team and b.rect is not None]
        cands.sort(key=lambda b: b.depth)
        for b in cands:
            x0, top, bw, bh, depth = b.rect
            if depth > wall_d + 0.05 or depth > w.rng * 1.5:
                continue
            if x0 <= ax <= x0 + bw and top <= ay <= top + bh:
                rel = (ay - top) / max(1.0, bh)
                if rel < 0.26:
                    mult, head = 4.0, True
                elif rel > 0.78:
                    mult, head = 0.78, False
                else:
                    mult, head = 1.0, False
                fall = clamp(1.12 - depth / w.rng * 0.6, 0.4, 1.0)
                dmg = w.dmg * mult * fall
                z = self.screen_z(ay, depth)
                self.tracers.append(Tracer(p.x + math.cos(p.ang) * 0.4,
                                           p.y + math.sin(p.ang) * 0.4,
                                           p.eye() - 0.08, b.x, b.y, z))
                self.particles.append(Particle(b.x, b.y, max(0.15, z),
                                               random.uniform(-.8, .8),
                                               random.uniform(-.8, .8), 1.2, 0.4,
                                               self.art.blood, 0.26))
                self.hurt_bot(b, dmg, p, head)
                p.hitmark = 0.12
                self.audio.play('hit', 0, 0.9)
                return
        # duvar
        d = min(wall_d, w.rng)
        ang = p.ang + (ax - RW * 0.5) / px_per_rad
        ix, iy = p.x + math.cos(ang) * d, p.y + math.sin(ang) * d
        z = self.screen_z(ay, max(0.2, d))
        self.tracers.append(Tracer(p.x + math.cos(p.ang) * 0.4,
                                   p.y + math.sin(p.ang) * 0.4,
                                   p.eye() - 0.08, ix, iy, z))
        for _ in range(3):
            self.particles.append(Particle(ix, iy, max(0.05, z),
                                           random.uniform(-1, 1), random.uniform(-1, 1),
                                           random.uniform(0.5, 2), 0.22,
                                           self.art.spark, 0.1))

    def screen_z(self, sy, depth):
        c = self.renderer.cam
        if c is None:
            return 0.5
        unit = RH / max(0.1, depth)
        floor_y = HALF_RH + c['pitch'] + c['dz'] * unit + unit * 0.5
        return (floor_y - sy) / unit

    def throw_nade(self):
        p = self.player
        if p.nades <= 0 or not p.alive or self.phase != 'live':
            return
        p.nades -= 1
        vz = 2.2 - p.pitch / 90.0
        self.grenades.append(Grenade(p.x + math.cos(p.ang) * 0.4,
                                     p.y + math.sin(p.ang) * 0.4, p.eye(),
                                     math.cos(p.ang) * 8.5, math.sin(p.ang) * 8.5,
                                     vz, p))

    def explode_nade(self, g):
        self.audio.play('boom', self.dist_to_player(g), 0.8)
        for _ in range(22):
            a = random.uniform(0, 6.28)
            self.particles.append(Particle(g.x, g.y, g.z + 0.1,
                                           math.cos(a) * random.uniform(1, 5),
                                           math.sin(a) * random.uniform(1, 5),
                                           random.uniform(1, 4), random.uniform(0.3, 0.8),
                                           self.art.smoke, random.uniform(0.3, 0.9), 1.4))
        R = 5.0
        targets = list(self.bots) + [self.player]
        for t in targets:
            if not t.alive:
                continue
            d = math.hypot(t.x - g.x, t.y - g.y)
            if d < R and los(g.x, g.y, t.x, t.y):
                dmg = 108 * (1 - d / R) ** 1.4
                if isinstance(t, Player):
                    t.take_damage(dmg, g.x, g.y, self, g.owner if g.owner is not t else None)
                else:
                    self.hurt_bot(t, dmg, g.owner if g.owner else self.player)
        if self.player.alive and math.hypot(self.player.x - g.x, self.player.y - g.y) < 9:
            self.player.shake = max(self.player.shake, 0.5)

    # ----------------------------------------------------------------- #
    #  satın alma
    # ----------------------------------------------------------------- #
    def buy(self, idx):
        p = self.player
        if self.phase != 'freeze':
            self.hud_note = "Sadece hazırlık süresinde alışveriş yapılabilir"
            return
        if 1 <= idx <= len(BUY_LIST):
            key = BUY_LIST[idx - 1]
            w = WEAPONS[key]
            if p.money >= w.price:
                p.money -= w.price
                p.give(key)
                self.audio.play('click', 0, 0.6)
            else:
                self.hud_note = "Yetersiz para"
        elif idx == 7:
            if p.money >= ARMOR_PRICE:
                p.money -= ARMOR_PRICE
                p.armor = 100; p.helmet = True
                self.audio.play('click', 0, 0.6)
            else:
                self.hud_note = "Yetersiz para"
        elif idx == 8:
            if p.money >= NADE_PRICE and p.nades < 2:
                p.money -= NADE_PRICE
                p.nades += 1
                self.audio.play('click', 0, 0.6)

    def cycle_weapon(self, key):
        p = self.player
        if key in p.slots:
            p.cur = key
            p.zoom = False
            p.reloading = 0.0

    # ----------------------------------------------------------------- #
    #  girdi
    # ----------------------------------------------------------------- #
    def read_input(self):
        inp = Inp()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                inp.keys.append(ev.key)
                if ev.key == pygame.K_ESCAPE:
                    if self.buy_open:
                        self.buy_open = False
                    else:
                        self.running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    inp.click = True
                elif ev.button == 3:
                    inp.alt = True
            elif ev.type == pygame.MOUSEMOTION:
                inp.mdx += ev.rel[0]
                inp.mdy += ev.rel[1]
        k = pygame.key.get_pressed()
        inp.fwd = (1 if k[pygame.K_w] else 0) - (1 if k[pygame.K_s] else 0)
        inp.strafe = (1 if k[pygame.K_d] else 0) - (1 if k[pygame.K_a] else 0)
        inp.walk = k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]
        inp.crouch = k[pygame.K_LCTRL] or k[pygame.K_RCTRL]
        inp.jump = k[pygame.K_SPACE]
        inp.use = k[pygame.K_e]
        inp.tab = k[pygame.K_TAB]
        inp.fire = pygame.mouse.get_pressed()[0]
        return inp

    def fake_input(self):
        """--test modunda otomatik oynayan sahte girdi"""
        for ev in pygame.event.get():
            pass
        inp = Inp()
        inp.fwd = random.choice((0, 1, 1, -1))
        inp.strafe = random.choice((0, 1, -1))
        inp.mdx = random.uniform(-25, 25)
        inp.mdy = random.uniform(-8, 8)
        inp.fire = random.random() < 0.45
        inp.click = random.random() < 0.25
        inp.alt = random.random() < 0.02
        inp.jump = random.random() < 0.02
        inp.crouch = random.random() < 0.06
        inp.use = True
        if random.random() < 0.02:
            inp.keys.append(pygame.K_r)
        if random.random() < 0.01:
            inp.keys.append(pygame.K_g)
        if random.random() < 0.01:
            inp.keys.append(random.choice([pygame.K_1, pygame.K_2, pygame.K_3,
                                           pygame.K_4, pygame.K_5, pygame.K_6,
                                           pygame.K_7, pygame.K_8]))
        if self.frames == 4:
            inp.keys.append(pygame.K_RETURN)
        if self.frames % 137 == 0:
            inp.keys.append(pygame.K_b)
        return inp

    # ----------------------------------------------------------------- #
    #  güncelleme
    # ----------------------------------------------------------------- #
    def update(self, dt, inp):
        self.time += dt
        self.hud_note = ''
        self.show_score = inp.tab
        p = self.player

        # --- menüler
        if self.phase in ('menu', 'gameover'):
            if pygame.K_RETURN in inp.keys or pygame.K_SPACE in inp.keys \
                    or pygame.K_r in inp.keys:
                self.start_match()
            return

        # --- kısayollar
        for key in inp.keys:
            if key == pygame.K_b:
                if self.phase == 'freeze':
                    self.buy_open = not self.buy_open
            elif key == pygame.K_r:
                self.start_reload()
            elif key == pygame.K_g:
                self.throw_nade()
            elif key == pygame.K_q:
                self.cycle_weapon('knife')
            elif pygame.K_1 <= key <= pygame.K_8:
                idx = key - pygame.K_0
                if self.buy_open:
                    self.buy(idx)
                elif idx <= len(BUY_LIST):
                    self.cycle_weapon(BUY_LIST[idx - 1])

        # --- bakış
        if p.alive or self.phase in ('live', 'end'):
            p.ang = (p.ang + inp.mdx * self.sens *
                     (0.34 if (p.zoom and p.wep.kind == 'sniper') else 1.0)) % (2 * math.pi)
            p.pitch = clamp(p.pitch - inp.mdy * self.sens * 120, -150, 150)

        # --- silah zamanlayıcıları
        p.cd = max(0.0, p.cd - dt)
        p.hitmark = max(0.0, p.hitmark - dt)
        p.hurt_flash = max(0.0, p.hurt_flash - dt * 1.6)
        p.shake = max(0.0, p.shake - dt * 1.8)
        p.spread = max(0.0, p.spread - dt * 2.6)
        if p.reloading > 0:
            p.reloading -= dt
            if p.reloading <= 0:
                s = p.slot
                need = s.w.mag - s.ammo
                take = min(need, s.reserve)
                s.ammo += take
                s.reserve -= take
        if p.recoil > 0 and p.cd < p.wep.interval * 0.35:
            rec = min(p.recoil, dt * 90)
            p.pitch -= rec
            p.recoil -= rec

        if inp.alt:
            if p.wep.kind == 'sniper':
                p.zoom = not p.zoom
            else:
                p.zoom = False

        # --- faz zamanlayıcıları
        if self.phase == 'freeze':
            self.phase_t -= dt
            if self.phase_t <= 0:
                self.phase = 'live'
                self.phase_t = ROUND_TIME if not self.test else 18.0
                self.buy_open = False
        elif self.phase == 'live':
            self.phase_t -= dt
        elif self.phase == 'end':
            self.phase_t -= dt
            if self.phase_t <= 0:
                self.next_phase_after_end()
                return

        moving = False
        if self.phase == 'live' and p.alive and not self.buy_open:
            moving = p.move(inp, dt, self)
            if inp.fire or inp.click:
                self.try_fire(inp.click)
        elif p.alive:
            p.vel = (0.0, 0.0)
            tgt = 1.0 if inp.crouch else 0.0
            p.crouch += (tgt - p.crouch) * min(1.0, dt * 10)

        # --- defuse (oyuncu)
        b = self.bomb
        if self.phase == 'live' and p.alive and b.state == 'planted' and inp.use \
                and math.hypot(b.x - p.x, b.y - p.y) < 1.0:
            p.defusing += dt
            p.vel = (0, 0)
            if p.defusing >= DEFUSE_TIME:
                p.defusing = 0.0
                self.defuse_bomb(p)
                return
        else:
            p.defusing = 0.0

        # --- botlar
        if self.phase in ('live', 'end'):
            for bot in self.bots:
                if self.phase == 'live':
                    bot.update(dt, self)
                else:
                    if not bot.alive:
                        bot.death_t += dt

        # --- yerdeki bombayı alma
        if b.state == 'ground':
            for bot in self.bots:
                if bot.alive and bot.team == 'T' and \
                        math.hypot(bot.x - b.x, bot.y - b.y) < 0.7:
                    bot.has_bomb = True
                    b.state = 'carried'
                    b.carrier = bot
                    bot.path = []; bot.path_t = 0
                    break
        elif b.state == 'carried' and b.carrier and b.carrier.alive:
            b.x, b.y = b.carrier.x, b.carrier.y

        # --- bomba sayacı
        if b.state == 'planted':
            b.timer -= dt
            b.beep_t -= dt
            if b.beep_t <= 0:
                per = clamp(b.timer / BOMB_TIME, 0.06, 1.0)
                b.beep_t = 0.15 + per * 1.0
                self.audio.play('beep', math.hypot(b.x - p.x, b.y - p.y), 0.7)
            if b.timer <= 0 and self.phase == 'live':
                self.explode_bomb()

        # --- efektler
        self.particles = [q for q in self.particles if q.update(dt)]
        self.tracers = [t for t in self.tracers if t.update(dt)]
        alive_n = []
        for g in self.grenades:
            if g.update(dt, self):
                alive_n.append(g)
            else:
                self.explode_nade(g)
        self.grenades = alive_n
        if len(self.particles) > 260:
            self.particles = self.particles[-260:]

        # --- kazanma koşulları
        if self.phase == 'live':
            t_alive = any(x.alive for x in self.bots if x.team == 'T')
            ct_alive = p.alive or any(x.alive for x in self.bots if x.team == 'CT')
            if not ct_alive:
                self.end_round('T', "TERÖRİSTLER KAZANDI")
            elif not t_alive and b.state != 'planted':
                self.end_round('CT', "TERÖRİSTLER ETKİSİZLEŞTİRİLDİ")
            elif self.phase_t <= 0 and b.state != 'planted':
                self.end_round('CT', "SÜRE DOLDU — CT KAZANDI")

    # ----------------------------------------------------------------- #
    #  çizim
    # ----------------------------------------------------------------- #
    def draw_menu(self):
        s = self.screen
        s.fill((10, 12, 16))
        h = self.hud
        h.txt(s, "P Y C S 2", WIN_W // 2, 130, C_ACC, h.f_xl, center=True)
        h.txt(s, "Python + pygame ile yazılmış raycast FPS  —  de_pycs",
              WIN_W // 2, 190, (180, 180, 190), h.f_m, center=True)
        lines = [
            "WASD hareket   •   Mouse bakış   •   Sol tık ateş   •   Sağ tık AWP dürbün",
            "R şarjör   •   G HE bombası   •   Shift sessiz yürü   •   Ctrl eğil   •   Space zıpla",
            "B satın alma (hazırlık süresinde)   •   1-8 satın al / silah seç   •   E bombayı defuse et",
            "TAB skor tablosu   •   ESC çıkış",
            "",
            "Sen CT'sin. 4 terörist botu durdur ya da bombayı defuse et.",
            f"İlk {MAX_SCORE} roundu kazanan maçı alır.",
        ]
        y = 280
        for ln in lines:
            h.txt(s, ln, WIN_W // 2, y, (205, 205, 210), h.f_s, center=True)
            y += 30
        if self.phase == 'gameover':
            h.txt(s, self.end_msg, WIN_W // 2, 520, C_ACC, h.f_l, center=True)
            h.txt(s, f"Skor  CT {self.score['CT']} - {self.score['T']} T",
                  WIN_W // 2, 560, C_TXT, h.f_m, center=True)
        h.txt(s, "BAŞLAMAK İÇİN ENTER", WIN_W // 2, 640,
              C_HP if int(self.time * 2) % 2 == 0 else (60, 120, 80),
              h.f_l, center=True)

    def draw(self):
        if self.phase in ('menu', 'gameover'):
            self.draw_menu()
            return
        frame = self.renderer.render(self)
        pygame.transform.scale(frame, (WIN_W, WIN_H), self.screen)
        self.hud.draw(self.screen, self, self.clock.get_fps())

    # ----------------------------------------------------------------- #
    def run(self, max_frames=None):
        while self.running:
            dt = self.clock.tick(FPS_CAP) / 1000.0
            if self.test:
                dt = 1.0 / 60.0
            dt = min(dt, 0.05)
            inp = self.fake_input() if self.test else self.read_input()
            self.update(dt, inp)
            self.draw()
            pygame.display.flip()
            self.frames += 1
            if max_frames and self.frames >= max_frames:
                break


# --------------------------------------------------------------------- #
#  GİRİŞ NOKTASI
# --------------------------------------------------------------------- #
def main():
    test = '--test' in sys.argv
    if test:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    else:
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
        except Exception:
            pass
    pygame.init()
    pygame.display.set_caption("PYCS2 — Python Raycast FPS")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    if not test:
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(True)
        pygame.mouse.get_rel()
    g = Game(screen, test=test)
    if test:
        g.run(max_frames=int(os.environ.get('PYCS2_FRAMES', '900')))
        print("TEST OK | frames=%d round=%d skor=%s bot_alive=%d parts=%d" %
              (g.frames, g.round_no, g.score,
               sum(1 for b in g.bots if b.alive), len(g.particles)))
    else:
        g.run()
    pygame.quit()


if __name__ == '__main__':
    main()
