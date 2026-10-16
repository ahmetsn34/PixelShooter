# PixelShooter

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Pygame](https://img.shields.io/badge/Pygame-2D%20%26%20Raycasting-5B8C32?style=flat-square)

A single-player FPS experiment built with Python and Pygame, inspired by round-based tactical shooters. A textured raycasting renderer, pathfinding bots, and a bomb-defusal scenario run from one Python file.

## Features

- DDA raycasting with textured walls, sprite rendering, vertical aiming, jumping, and crouching.
- Bots with A* pathfinding, line-of-sight checks, combat, and bomb objectives.
- Six firearms and a knife, with recoil, ammunition, reloading, and an AWP scope.
- Round economy, a buy menu, armor, and HE grenades.
- HUD, minimap, scoreboard, kill feed, and procedurally generated graphics.

## Quick start

Install Python 3, then clone the repository and create a virtual environment:

```bash
git clone https://github.com/ahmetsn34/PixelShooter.git
cd PixelShooter
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS / Linux:

```bash
source .venv/bin/activate
```

Install Pygame and launch the game:

```bash
python -m pip install pygame
python "cs2çakması.py"
```

Optional: install NumPy to enable the synthesized sound effects:

```bash
python -m pip install numpy
```

No external image or sound assets are required. The game opens a 1280 × 720 window and captures the mouse during play.

## Controls

| Input | Action |
|---|---|
| Enter | Start a match / restart after game over |
| W / A / S / D | Move |
| Mouse | Look / aim |
| Left mouse button | Fire |
| Right mouse button | Toggle AWP scope |
| R | Reload |
| Shift | Walk quietly |
| Ctrl | Crouch |
| Space | Jump |
| G | Throw an HE grenade |
| Q | Equip the knife |
| 1–6 | Select an owned firearm; buy one while the buy menu is open |
| 7 / 8 | Buy armor / an HE grenade while the buy menu is open |
| B | Toggle the buy menu during the round's freeze phase |
| Hold E near the bomb | Defuse |
| Hold Tab | Show scoreboard |
| Esc | Quit |

## Project structure

[`cs2çakması.py`](cs2%C3%A7akmas%C4%B1.py) contains the map, procedural assets, audio synthesis, renderer, bot logic, UI, and game loop.

