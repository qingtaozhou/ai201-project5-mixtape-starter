"""Tests for notifications created by song interactions."""

import pytest

from app import create_app, db
from models import Notification, Song, User
from services.notification_service import rate_song


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def rating_setup(app):
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        friend = User(username="friend", email="friend@example.com")
        db.session.add_all([sharer, friend])
        db.session.flush()

        song = Song(title="Shared Song", artist="Artist", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()
        yield {"sharer_id": sharer.id, "friend_id": friend.id, "song_id": song.id}


def test_rating_notifies_song_sharer(app, rating_setup):
    """A rating from another user should notify the song's original sharer."""
    with app.app_context():
        rate_song(rating_setup["friend_id"], rating_setup["song_id"], 5)

        notifications = db.session.query(Notification).all()
        assert len(notifications) == 1
        assert notifications[0].user_id == rating_setup["sharer_id"]
        assert notifications[0].notification_type == "song_rated"
        assert "friend" in notifications[0].body
        assert "Shared Song" in notifications[0].body
        assert "5" in notifications[0].body


def test_rating_own_song_does_not_notify(app, rating_setup):
    """A user should not receive a notification for rating their own song."""
    with app.app_context():
        rate_song(rating_setup["sharer_id"], rating_setup["song_id"], 4)

        assert db.session.query(Notification).count() == 0
