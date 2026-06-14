"""LAN multiplayer: authoritative host + thin pygame clients.

The host runs the real ``World`` (bots, boss, shapes, scoring) and is the
single source of truth. Clients send input and render interpolated world
snapshots through the existing renderer/HUD. See ``server.py`` / ``client.py``.
"""
