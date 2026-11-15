<img src="assets/icon.png" width="64" align="right">

# realrap

**real random password** – a password generator where every character is a 3D cube.

Draw cubes, spin them, copy the password. One cube = one character, so the more cubes, the longer and stronger the password.

## How it works

Each cube gets a secret 32-bit seed from the OS's cryptographic random generator. Its character is a SHA-256 hash of that seed plus the cube's rotation, size and position, so spinning a cube rerolls its character. The geometry is visible on screen, which is why it only shapes the characters: the security comes entirely from the seed.

- ~6.4 bits per cube: **12 cubes ≈ 77 bits (good), 16 ≈ 103 bits (strong)**. A meter shows the current strength.
- The password is masked by default (`*`, still colored per cube).
- Copied passwords are wiped from the clipboard after 30 s or on exit, and kept out of the Windows clipboard history (Win+V) and cloud sync.

## Run

```
pip install -r requirements.txt
python main.py
```

Built for Windows (the classic window frame, transparency and clipboard protection use the Win32 API).

## Controls

| Input | Action |
|---|---|
| Right-drag | create a cube (drag sets its size) |
| Left-drag | rotate a cube, or sweep across several |
| Left-click | delete a cube |
| Arrow keys | rotate the cube under the mouse |
| Mouse wheel | zoom |
| `N` / `C` | random cube / clear all |
| `T` | toggle window transparency |
| `Esc` | quit |

## Build an .exe

```
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name realrap --icon assets/icon.ico --add-data "assets/icon.png;assets" main.py
```

The result is `dist/realrap.exe`. To change the icon, edit and run `make_icon.py`.
