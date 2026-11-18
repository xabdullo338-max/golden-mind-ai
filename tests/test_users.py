import pytest
from app.users import UserStore

def test_user_password_is_hashed_and_authenticates(tmp_path):
    store = UserStore(str(tmp_path / "users.db"))
    store.create_user("alice", "correct-horse-123", "trader")
    assert store.authenticate("alice", "correct-horse-123")["role"] == "trader"
    assert store.authenticate("alice", "wrong-password") is None

def test_short_password_rejected(tmp_path):
    with pytest.raises(ValueError):
        UserStore(str(tmp_path / "users.db")).create_user("alice", "short", "viewer")
