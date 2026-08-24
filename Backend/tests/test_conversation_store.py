import time
import unittest

from app.services.conversation_store import ConversationStore


class ConversationStoreTests(unittest.TestCase):
    def test_get_or_create_returns_same_state_for_same_id(self):
        store = ConversationStore()
        first = store.get_or_create(None)
        second = store.get_or_create(first.conversation_id)
        self.assertIs(first, second)

    def test_unknown_id_creates_a_fresh_conversation(self):
        store = ConversationStore()
        state = store.get_or_create("does-not-exist-yet")
        self.assertEqual(state.conversation_id, "does-not-exist-yet")

    def test_lru_eviction_drops_oldest_conversation(self):
        store = ConversationStore(max_conversations=2)
        first = store.get_or_create("a")
        store.get_or_create("b")
        store.get_or_create("c")
        self.assertIsNone(store.get("a"))
        self.assertIsNotNone(store.get("b"))
        self.assertIsNotNone(store.get("c"))
        self.assertNotEqual(first.conversation_id, "b")

    def test_idle_conversations_expire(self):
        store = ConversationStore(idle_expiry_seconds=0.01)
        state = store.get_or_create("idle")
        state.updated_at = time.time() - 10
        self.assertIsNone(store.get("idle"))

    def test_save_updates_timestamp_and_keeps_conversation(self):
        store = ConversationStore()
        state = store.get_or_create("s1")
        state.last_effective_message = "gaming laptop under $1200"
        store.save(state)
        fetched = store.get("s1")
        self.assertEqual(fetched.last_effective_message, "gaming laptop under $1200")


if __name__ == "__main__":
    unittest.main()
