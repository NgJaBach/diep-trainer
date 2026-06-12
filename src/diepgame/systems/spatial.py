"""Uniform spatial hash grid for broad-phase collision queries."""
from __future__ import annotations
from collections import defaultdict


class SpatialHash:
    def __init__(self, cell: float = 120.0):
        self.cell = cell
        self.grid: dict[tuple[int, int], list] = defaultdict(list)

    def rebuild(self, entities):
        self.grid.clear()
        c = self.cell
        for e in entities:
            if not e.alive:
                continue
            x0 = int((e.pos.x - e.radius) // c)
            x1 = int((e.pos.x + e.radius) // c)
            y0 = int((e.pos.y - e.radius) // c)
            y1 = int((e.pos.y + e.radius) // c)
            for gx in range(x0, x1 + 1):
                for gy in range(y0, y1 + 1):
                    self.grid[(gx, gy)].append(e)

    def candidate_pairs(self):
        seen = set()
        for bucket in self.grid.values():
            n = len(bucket)
            if n < 2:
                continue
            for i in range(n):
                a = bucket[i]
                for j in range(i + 1, n):
                    b = bucket[j]
                    key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield a, b

    def query_circle(self, pos, radius):
        c = self.cell
        x0 = int((pos.x - radius) // c)
        x1 = int((pos.x + radius) // c)
        y0 = int((pos.y - radius) // c)
        y1 = int((pos.y + radius) // c)
        out = set()
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                for e in self.grid.get((gx, gy), ()):
                    out.add(e)
        return out
