# E-Ink UI

A simple Spotify now playing UI for a 7.3" 6-colour e-ink display.

Features
- Spotify now playing info
- Album art
- Dynamic colour scheme based on album art
- Media control (play/pause, next track, previous track, save to favourites)

## Setup

```bash
sudo adduser einkui
sudo usermod -aG sudo einkui
sudo usermod -aG gpio einkui
sudo usermod -aG spi einkui
```