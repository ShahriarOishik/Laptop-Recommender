from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock

from app.models import ChatIntent, IndexType, LaptopRecommendation, SearchFilters


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant"
    text: str
    intent: ChatIntent | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationState:
    conversation_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    last_recommendations: list[LaptopRecommendation] = field(default_factory=list)
    last_filters: SearchFilters = field(default_factory=SearchFilters)
    last_index_type: IndexType | None = None
    last_effective_message: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    MAX_TURNS: int = field(default=20, repr=False)

    def add_turn(self, role: str, text: str, intent: ChatIntent | None = None) -> None:
        self.turns.append(ConversationTurn(role=role, text=text, intent=intent))
        if len(self.turns) > self.MAX_TURNS:
            self.turns = self.turns[-self.MAX_TURNS :]
        self.updated_at = time.time()


class ConversationStore:
    """Bounded, thread-safe in-memory conversation state.

    Mirrors the eviction pattern used by ``SemanticCache`` in ``cache.py``.
    No external persistence is used, matching the project's explicit
    constraint against adding Redis/database infrastructure just for chat
    history.
    """

    def __init__(self, max_conversations: int = 256, idle_expiry_seconds: float = 7200.0) -> None:
        self.max_conversations = max_conversations
        self.idle_expiry_seconds = idle_expiry_seconds
        self._conversations: OrderedDict[str, ConversationState] = OrderedDict()
        self._lock = RLock()
        # One asyncio.Lock per conversation, held by RagService for the
        # *entire* request (not just the get_or_create/save calls) so two
        # concurrent requests on the same conversation_id — a double-click,
        # a client retry, two tabs on the same chat — can't interleave their
        # unprotected mutations of the shared ConversationState and corrupt
        # it with a "last write wins" race. Different conversation_ids never
        # block each other; only same-conversation requests serialize.
        self._conversation_locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, conversation_id: str) -> asyncio.Lock:
        with self._lock:
            lock = self._conversation_locks.get(conversation_id)
            if lock is None:
                lock = asyncio.Lock()
                self._conversation_locks[conversation_id] = lock
            return lock

    def get_or_create(self, conversation_id: str | None) -> ConversationState:
        with self._lock:
            self._evict_expired()
            if conversation_id and conversation_id in self._conversations:
                self._conversations.move_to_end(conversation_id)
                return self._conversations[conversation_id]
            new_id = conversation_id or uuid.uuid4().hex
            state = ConversationState(conversation_id=new_id)
            self._conversations[new_id] = state
            self._conversations.move_to_end(new_id)
            self._evict_over_capacity()
            return state

    def get(self, conversation_id: str) -> ConversationState | None:
        with self._lock:
            self._evict_expired()
            state = self._conversations.get(conversation_id)
            if state is not None:
                self._conversations.move_to_end(conversation_id)
            return state

    def save(self, state: ConversationState) -> None:
        with self._lock:
            state.updated_at = time.time()
            self._conversations[state.conversation_id] = state
            self._conversations.move_to_end(state.conversation_id)
            self._evict_over_capacity()

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._evict_expired()
            return {"active_conversations": len(self._conversations)}

    def _evict_expired(self) -> None:
        cutoff = time.time() - self.idle_expiry_seconds
        expired = [
            conversation_id
            for conversation_id, state in self._conversations.items()
            if state.updated_at < cutoff
        ]
        for conversation_id in expired:
            del self._conversations[conversation_id]
            self._conversation_locks.pop(conversation_id, None)

    def _evict_over_capacity(self) -> None:
        while len(self._conversations) > self.max_conversations:
            evicted_id, _ = self._conversations.popitem(last=False)
            self._conversation_locks.pop(evicted_id, None)
