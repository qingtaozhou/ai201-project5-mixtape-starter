# Mixtape Project Submission

## Codebase Map

### Application setup

- `app.py` creates the shared SQLAlchemy object and defines the `create_app()` application factory. The factory loads the database URL and secret key, accepts configuration overrides for tests, initializes SQLAlchemy, registers four blueprints under `/songs`, `/playlists`, `/users`, and `/feed`, and creates the database tables. The project should be started through this factory with `FLASK_APP=app:create_app flask run`.
- `requirements.txt` lists the Flask, Flask-SQLAlchemy, SQLAlchemy, dotenv, and pytest dependencies.
- `seed_data.py` rebuilds the development database and inserts users, bidirectional friendships, tags, songs, listening events, ordered playlist entries, and a sample notification. Its data deliberately covers recent and older listening activity, songs with different numbers of tags, and populated playlists.

### Data model

`models.py` defines seven SQLAlchemy models:

- `User` stores identity, current listening streak, and the last listening time. Its relationships expose shared songs, ratings, listening events, notifications, playlists, and friends.
- `Tag` stores a unique tag name.
- `Song` stores music metadata, the user who shared it, its share time/note, ratings, listening events, and tags.
- `ListeningEvent` records which user listened to which song and when. These records drive listening history and both feed views.
- `Rating` records a user's 1–5 score for a song. A unique constraint on `(user_id, song_id)` allows only one rating per user/song pair.
- `Playlist` stores playlist metadata and exposes its songs through an association table.
- `Notification` stores a recipient, notification type, message body, creation time, and read state.

There are also three association tables rather than full model classes:

- `friendships` represents the self-referential many-to-many user relationship. The seed script writes both directions explicitly.
- `song_tags` connects songs and tags.
- `playlist_entries` connects playlists and songs while also storing `position`, `added_by`, and `added_at`. Playlist order is therefore explicit database data, not an assumption about insertion order.

Most models provide `to_dict()` methods, so the service layer can return JSON-ready dictionaries without duplicating serialization in every route.

### HTTP routes

- `routes/songs.py` provides song search and detail endpoints, rating submission, and listening-event creation. It delegates to the search, notification, and streak services.
- `routes/playlists.py` provides playlist creation, playlist metadata, ordered song retrieval, and adding a song. It delegates playlist queries to `playlist_service` and the add-and-notify workflow to `notification_service`.
- `routes/users.py` returns user profiles and streaks and supports listing or marking notifications as read. Profile lookup is the one route that queries a model directly; the other operations use services.
- `routes/feed.py` exposes the deduplicated “listening now” view and the broader activity feed through `feed_service`.

Routes mainly parse path/query/JSON input, reject missing fields, call one service function, and format a JSON response. Service `ValueError`s are translated into HTTP 400 or 404 responses.

### Service layer

- `services/search_service.py` searches song titles and artists case-insensitively and retrieves a single song. Returned song dictionaries include tag names through the `Song.tags` relationship.
- `services/streak_service.py` creates listening events and updates or retrieves a user's consecutive-day listening streak. Event creation and the streak update are committed together.
- `services/feed_service.py` builds two friend-based views from `ListeningEvent` records. “Listening now” applies a time cutoff and keeps the newest event for each friend; the activity feed returns up to 20 friend events without that recency filter.
- `services/playlist_service.py` creates playlists, retrieves metadata, lists a user's playlists, and joins through `playlist_entries` to return songs ordered by their stored position.
- `services/notification_service.py` creates, retrieves, and marks notifications as read. It also owns the two interaction workflows: adding a song to a playlist and creating/updating a rating.

### Tests

- `tests/test_streaks.py` checks new, same-day, consecutive-day, skipped-day, and weekend streak behavior.
- `tests/test_feed.py` checks both sides of the one-hour “listening now” boundary and confirms that the general activity feed remains unfiltered by age.
- `tests/test_search.py` checks matching, no-match results, and songs with zero, one, or several tags.
- `tests/test_playlists.py` checks complete ordered playlist retrieval and empty playlists.

Each test module creates an isolated in-memory SQLite application using `create_app()` configuration overrides. The tests call service functions directly, which keeps them focused on business logic rather than HTTP transport.

## Feature Data Flows

### Adding a song to a playlist and notifying its sharer

1. A client sends `POST /playlists/<playlist_id>/songs` with `song_id` and `added_by` JSON fields.
2. `routes/playlists.py:add_song()` validates that both fields are present and calls `notification_service.add_to_playlist()`.
3. `add_to_playlist()` loads the `Song`, adding `User`, and `Playlist`, raising `ValueError` if any identifier is invalid.
4. If the playlist does not already contain the song, the service appends it through `Playlist.songs`, which writes the relationship to `playlist_entries`, and commits it.
5. If the adding user is not the song's original sharer, the service calls `create_notification()` with the sharer's user ID and a `song_added_to_playlist` message.
6. `create_notification()` inserts and commits a `Notification`. The route then returns HTTP 201.
7. The recipient later requests `GET /users/<user_id>/notifications`. `routes/users.py` calls `get_notifications()`, which can filter unread records and returns them newest-first.

This flow shows that a notification is not emitted merely by reading a playlist. It is a side effect of the service operation that mutates the playlist relationship.

### Recording a listen and surfacing it in a feed

1. A client sends `POST /songs/<song_id>/listen` with `user_id`.
2. `routes/songs.py:listen()` validates the payload and calls `streak_service.record_listening_event()`.
3. The service loads the user, creates a timestamped `ListeningEvent`, calls `update_listening_streak()`, and commits both changes in one transaction.
4. A friend requests `GET /feed/<user_id>/listening-now` or `/activity`.
5. `routes/feed.py` delegates to `feed_service`, which obtains that user's friend IDs, queries their listening events newest-first, loads the related user and song data, and returns JSON-ready feed entries.

The write path and read path meet at `ListeningEvent`: recording a listen updates streak state immediately, while feed endpoints later query the same event as social activity.

## Organization Patterns Noticed

- The code follows a small layered structure: blueprints handle HTTP concerns, services handle use cases and database operations, and models define persistence and serialization.
- The application-factory pattern supports both the SQLite development database and isolated in-memory test databases.
- UUID strings are used as primary keys throughout, and timestamps are created in UTC.
- Many-to-many concepts use association tables. `playlist_entries` is richer than an ordinary join because it carries ordering and attribution metadata.
- Service functions generally validate referenced records and signal expected failures with `ValueError`; routes consistently convert those exceptions into JSON errors.
- Multi-step workflows and commits live in services. Some workflows cross feature boundaries—for example, adding a playlist song also creates a notification, while recording a listen also updates a streak.

## Five Issues Reviewed Before Selection

The repository README identifies these five issue areas; the full descriptions are in the separate Project 5 brief:

1. Listening streaks unexpectedly reset (`streak_service.py`).
2. “Friends Listening Now” includes people from yesterday (`feed_service.py`).
3. The same song appears more than once in search (`search_service.py`).
4. Playlist additions notify a song's sharer, but ratings do not (`notification_service.py`).
5. The final song in a playlist is missing (`playlist_service.py`).

## Chosen Bugs and Reproduction Notes

No fix code was changed before or during these reproductions. I chose Issues #1, #2, and #5.

### Issue #1 — Listening streak resets on Sunday

**How I reproduced it:** Before changing service code, I ran the existing `test_streak_increments_on_sunday` test with a new user. The test calls `update_listening_streak()` at Saturday, June 15, 2024 at 12:00 UTC and again at Sunday, June 16 at 12:00 UTC. The first call established a streak of 1. Although the second call was exactly one calendar day later and should have incremented the streak to 2, it remained 1. Pytest therefore failed with `assert 1 == 2`.

```bash
.venv/bin/python -m pytest tests/test_streaks.py::test_streak_increments_on_sunday -q
```

I also isolated the relevant date values in Python. `(sunday - saturday).days` returned `1`, Saturday's `weekday()` returned `5`, and Sunday's returned `6`. With those inputs, the service's original increment condition evaluated to `False`.

**How I found the root cause:** I traced the feature top-down. In `routes/songs.py`, `POST /songs/<song_id>/listen` calls `record_listening_event()` in `services/streak_service.py`. That function creates a `ListeningEvent`, then calls `update_listening_streak(user, now)` before committing. In `models.py`, I confirmed that the function is updating the `User.listening_streak` and `User.last_listened_at` columns. I also checked `routes/users.py` and `get_streak()` to confirm that streak reads simply return this stored value and do not recalculate it later. Finally, I compared `update_listening_streak()` with the boundary cases in `tests/test_streaks.py`. The decisive moment was seeing that the docstring says every one-day gap increments, while the implementation required both `days_since_last == 1` and `today.weekday() != 6`.

**The root cause:** Python's `date.weekday()` returns `6` for Sunday. The condition `days_since_last == 1 and today.weekday() != 6` therefore explicitly rejected every otherwise-valid consecutive-day update occurring on Sunday. A Saturday listen followed by a Sunday listen went to the `else` branch, which reset the streak to 1. Weekday numbering was not needed at all: continuity is already fully determined by `days_since_last`.

**My fix and side-effect check:** I removed only the unrelated Sunday restriction, changing the increment condition to `days_since_last == 1`. This makes Sunday behave like every other consecutive calendar day while preserving the existing branches for a new user, repeated listens on the same day, and gaps longer than one day. All five streak tests pass after the change: new-user initialization, Monday-to-Tuesday increment, same-day no-op, skipped-day reset, and Saturday-to-Sunday increment. I then ran the full suite: 11 tests passed, while the two playlist tests for the separate, still-unfixed Issue #5 continued to fail. This shows the streak change did not disturb search or playlist behavior.

### Issue #2 — “Friends Listening Now” includes old activity

**How I reproduced it:** Before changing `feed_service.py`, I first created an isolated in-memory database with a viewer and one friend whose only `ListeningEvent` was 18 hours old. Calling `get_friends_listening_now(viewer.id)` returned that friend and `Yesterday Song` instead of an empty list:

```text
event age: 18 hours
expected listening-now count: 0
actual listening-now count: 1
returned friend/song: [('friend', 'Yesterday Song')]
```

I then made the boundary precise in `tests/test_feed.py`: one friend had an event 59 minutes old and another had an event 61 minutes old. Before the fix, `test_listening_now_uses_one_hour_boundary` failed because the service returned both `recent` and `stale` instead of only `recent`. The seed database alone was less reliable for demonstrating the symptom because a newer event for the same friend can hide that friend's old event during deduplication.

**How I found the root cause:** I started at `routes/feed.py`. `GET /feed/<user_id>/listening-now` calls `get_friends_listening_now()` and only wraps its list in JSON, so the route does not decide which events are recent. In `services/feed_service.py`, I followed the function in order: load the requesting `User`, read IDs from `User.friends`, calculate a cutoff, query `ListeningEvent.listened_at >= cutoff`, sort newest-first, and retain one event per friend. I checked `models.py` to confirm that `ListeningEvent.listened_at` is the timestamp being filtered. I then compared this path with `get_activity_feed()`, which intentionally has no age filter, and with `seed_data.py`, whose comments say events within 30 minutes should appear while events beginning at 2 hours old should not. The decisive line was `RECENT_THRESHOLD = timedelta(hours=24)`: it made the otherwise-correct cutoff query accept nearly a full day of activity.

**The root cause:** The “listening now” cutoff used a 24-hour window instead of the intended one-hour window. Because the query includes every event whose timestamp is newer than `now - RECENT_THRESHOLD`, an event from 18 hours ago still passed the database filter. Ordering and per-friend deduplication could choose the newest qualifying event, but neither could remove an old event when it was that friend's only event.

**My fix and side-effect check:** I changed only `RECENT_THRESHOLD` from `timedelta(hours=24)` to `timedelta(hours=1)`. The query structure, friend filtering, ordering, and deduplication remain unchanged. I added one regression test proving that a 59-minute event is included while a 61-minute event is excluded, covering both sides of the boundary. A second test proves that `get_activity_feed()` still returns both events because that separate feature is intentionally not time-filtered. Both feed tests pass. The full suite reports 13 passing tests, with only the two tests for the separate, still-unfixed playlist issue failing.

### Issue #5 — Last playlist song is missing

**How I reproduced it:** I used the existing playlist fixture, which creates one playlist with five songs named `Track 1` through `Track 5`. Each song is inserted into `playlist_entries` with positions 1 through 5. I called `get_playlist_songs(playlist.id)` and inspected both its length and ordered titles.

**Expected:** The service should return five songs in this order: `Track 1`, `Track 2`, `Track 3`, `Track 4`, `Track 5`.

**Actual:** It returned only four songs: `Track 1`, `Track 2`, `Track 3`, and `Track 4`. `Track 5`, the final positioned entry, was absent.

**Reproduction command:**

```bash
.venv/bin/python -m pytest \
  tests/test_playlists.py::test_playlist_returns_all_songs \
  tests/test_playlists.py::test_playlist_returns_songs_in_order -q
```

**Result:** Both tests fail consistently on the unchanged starter code: the count is 4 instead of 5, and the ordered title list lacks `Track 5`.

Issues #1 and #2 are fixed. Issue #5 remains unchanged for its separate investigation pass.

## AI Usage

For Issue #1, I used AI after tracing the route and service myself. I asked it to explain the meaning of `today.weekday() != 6` and used that explanation to check Python's weekday numbering. I verified the answer directly with controlled `date` values and the existing Sunday test before editing code. AI helped explain the suspicious condition; the call-chain reading and executable test established the diagnosis.

For Issue #2, I used AI after locating `get_friends_listening_now()` to enumerate boundary cases for its time filter and to compare its structure with `get_activity_feed()`. This helped identify useful checks just inside and outside one hour and the need to preserve the unfiltered activity feed. I verified the diagnosis with controlled 59- and 61-minute database records before changing the threshold.
