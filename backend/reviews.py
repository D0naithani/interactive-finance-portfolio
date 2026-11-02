"""Demo-only exception review state, isolated per visitor session.

State lives in process memory: it is bounded, expires after inactivity and is lost on
restart or across multiple workers. It never alters reconciliation amounts or statuses.
"""
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
import time

RESOLUTIONS = ('reviewed', 'resolved')


class ReviewStore:
    def __init__(self, ttl_seconds=2 * 60 * 60, max_sessions=1000, max_reviews=200, clock=time.monotonic):
        self.ttl_seconds, self.max_sessions, self.max_reviews, self.clock = ttl_seconds, max_sessions, max_reviews, clock
        self._sessions = OrderedDict()  # session_id -> (last_seen, {transaction_id: record}); oldest first
        self._lock = Lock()

    def _prune(self, now):
        while self._sessions:
            key, (seen, _) = next(iter(self._sessions.items()))
            if now - seen < self.ttl_seconds:
                break
            del self._sessions[key]

    def _live(self, session_id, now):
        # Expired sessions are pruned first, so anything still present is live.
        self._prune(now)
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        self._sessions[session_id] = (now, entry[1])
        self._sessions.move_to_end(session_id)
        return entry[1]

    def get(self, session_id):
        """Return a copy of a session's reviews; reading refreshes but never creates a session."""
        with self._lock:
            reviews = self._live(session_id, self.clock())
            return {k: dict(v) for k, v in (reviews or {}).items()}

    def set(self, session_id, transaction_id, status, note=''):
        if status not in RESOLUTIONS:
            raise ValueError(f'status must be one of {RESOLUTIONS}')
        with self._lock:
            now = self.clock()
            reviews = self._live(session_id, now)
            if reviews is None:
                while len(self._sessions) >= self.max_sessions:
                    self._sessions.popitem(last=False)  # evict least recently used
                reviews = {}
                self._sessions[session_id] = (now, reviews)
            if transaction_id not in reviews and len(reviews) >= self.max_reviews:
                raise OverflowError('Review limit reached for this demo session')
            record = dict(status=status, note=note, updated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
            reviews[transaction_id] = record
            return dict(record)

    def reopen(self, session_id, transaction_id):
        """Remove a decision. Returns True if one existed; idempotent otherwise."""
        with self._lock:
            reviews = self._live(session_id, self.clock())
            return bool(reviews) and reviews.pop(transaction_id, None) is not None

    def reset(self, session_id):
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def __len__(self):
        with self._lock:
            self._prune(self.clock())
            return len(self._sessions)


store = ReviewStore()
