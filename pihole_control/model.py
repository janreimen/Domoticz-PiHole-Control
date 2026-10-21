"""Plain data objects handed from the API client to the device layer."""
from typing import List, NamedTuple, Optional


class Stats(NamedTuple):
    """GET /api/stats/summary. A value the Pi-hole did not report is None (its device is left alone)."""
    total_queries: Optional[int]
    blocked_queries: Optional[int]
    percent_blocked: Optional[float]
    unique_domains: Optional[int]
    forwarded: Optional[int]
    cached: Optional[int]
    clients_active: Optional[int]
    clients_total: Optional[int]
    domains_blocked: Optional[int]


class BlockList(NamedTuple):
    """One entry of GET /api/lists (allow and block lists)."""
    id: int
    address: str
    comment: str
    groups: List[int]
    enabled: bool
    type: str


class Group(NamedTuple):
    """One entry of GET /api/groups."""
    id: int
    name: str
    comment: str
    enabled: bool
