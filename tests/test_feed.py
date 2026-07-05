"""Tests for friends' listening feed logic."""

from datetime import datetime, timedelta, timezone

import pytest

from app import create_app, db
from models import ListeningEvent, Song, User, friendships
from services.feed_service import get_activity_feed, get_friends_listening_now


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def listening_events(app):
    """Create friend events immediately inside and outside the one-hour boundary."""
    with app.app_context():
        viewer = User(username="viewer", email="viewer@example.com")
        recent_friend = User(username="recent", email="recent@example.com")
        stale_friend = User(username="stale", email="stale@example.com")
        db.session.add_all([viewer, recent_friend, stale_friend])
        db.session.flush()

        for friend in (recent_friend, stale_friend):
            db.session.execute(
                friendships.insert().values(user_id=viewer.id, friend_id=friend.id)
            )

        recent_song = Song(title="Recent Song", artist="Artist", shared_by=recent_friend.id)
        stale_song = Song(title="Stale Song", artist="Artist", shared_by=stale_friend.id)
        db.session.add_all([recent_song, stale_song])
        db.session.flush()

        now = datetime.now(timezone.utc)
        db.session.add_all(
            [
                ListeningEvent(
                    user_id=recent_friend.id,
                    song_id=recent_song.id,
                    listened_at=now - timedelta(minutes=59),
                ),
                ListeningEvent(
                    user_id=stale_friend.id,
                    song_id=stale_song.id,
                    listened_at=now - timedelta(minutes=61),
                ),
            ]
        )
        db.session.commit()
        yield viewer.id


def test_listening_now_uses_one_hour_boundary(app, listening_events):
    """Include a 59-minute event but exclude a 61-minute event."""
    with app.app_context():
        feed = get_friends_listening_now(listening_events)
        assert [item["friend"]["username"] for item in feed] == ["recent"]


def test_activity_feed_keeps_older_events(app, listening_events):
    """The general activity feed remains intentionally unfiltered by age."""
    with app.app_context():
        feed = get_activity_feed(listening_events)
        assert [item["friend"]["username"] for item in feed] == ["recent", "stale"]
