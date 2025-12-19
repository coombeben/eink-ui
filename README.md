# E-Ink UI

A simple Spotify "now playing" UI for a 7.3" 6-colour e-ink display.

Features
- Spotify now playing info
- Album art
- Dynamic colour scheme based on album art
- Media control (play/pause, next track, previous track, save to favourites)

## Installation

Create a `.env` file with the following variables:

```dotenv
SPOTIPY_CLIENT_ID=
SPOTIPY_CLIENT_SECRET=
```

## Setup

For setup on a fresh Raspberry Pi Lite OS installation, use the following commands:

### Add non-root user

```bash
sudo adduser einkui
sudo usermod -aG sudo einkui
sudo usermod -aG gpio einkui
sudo usermod -aG spi einkui
su einkui
```

### Clone and install

```bash
apt install python3-dev
git clone https://git.coombe.xyz/coomb/eink-ui.git
cd eink-ui
source venv/bin/activate
pip3 install -r requirements.txt
python3 main.py
```
