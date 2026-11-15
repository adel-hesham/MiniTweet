#!/usr/bin/env python3
"""
End-to-end check of a running MiniTweet stack. Uses only the Python standard library.

    docker compose up -d --build
    python scripts/smoke_test.py                       # checks http://localhost:8080
    python scripts/smoke_test.py http://some-host:8080

It signs up two new users, posts a tweet, likes it, waits for the notification, checks the
dashboard data, then deletes the tweet and checks the likes are cleaned up by the event.
Exit code is 0 only if every check passed, so it can be used in a CI pipeline.
"""
import json
import random
import string
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
failures = []


def call(method, path, body=None, token=None):
    """Returns (http status, parsed JSON or None). Status 0 means the server could not be reached."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, None
    except Exception as err:
        return 0, {"error": str(err)}


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or not detail else f"   ({detail})"))
    if not ok:
        failures.append(name)
    return ok


def wait_for(fn, seconds=15):
    """Keeps calling fn until it returns something truthy, or the time is up."""
    end = time.time() + seconds
    while time.time() < end:
        result = fn()
        if result:
            return result
        time.sleep(0.5)
    return None


def main():
    print(f"Smoke test against {BASE}\n")

    # 1. Is everything ready?
    for service in ("users", "tweets", "likes", "notifications"):
        status, _ = call("GET", f"/api/{service}/ready")
        check(f"{service} service is ready", status == 200, f"HTTP {status}")
    if failures:
        print("\nThe stack is not ready. Is `docker compose up` finished?")
        return 1

    # 2. Two users
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    alice, bob = f"alice_{suffix}", f"bob_{suffix}"
    tokens = {}
    for name in (alice, bob):
        status, _ = call("POST", "/api/users/register", {"username": name, "password": "secret123"})
        check(f"register {name}", status == 201, f"HTTP {status}")
        status, body = call("POST", "/api/users/login", {"username": name, "password": "secret123"})
        check(f"login {name}", status == 200 and body and "access_token" in body, f"HTTP {status}")
        tokens[name] = (body or {}).get("access_token")
    if not all(tokens.values()):
        return 1
    ta, tb = tokens[alice], tokens[bob]

    status, _ = call("POST", "/api/users/login", {"username": alice, "password": "wrong-password"})
    check("a wrong password is refused", status == 401, f"HTTP {status}")

    # 3. Bob tweets
    status, _ = call("POST", "/api/tweets", {"content": "no token"})
    check("posting without a token is refused", status == 401, f"HTTP {status}")
    status, tweet = call("POST", "/api/tweets", {"content": f"hello from {bob}"}, tb)
    if not check("bob posts a tweet", status == 201 and tweet and "id" in tweet, f"HTTP {status}"):
        return 1
    tweet_id = tweet["id"]
    status, listing = call("GET", "/api/tweets?limit=50")
    check("the tweet is in the public list", status == 200 and any(t["id"] == tweet_id for t in listing or []))

    # 4. Alice likes it (REST: like-service asks tweet-service; event: tweet.liked)
    status, body = call("POST", "/api/likes", {"tweet_id": tweet_id}, ta)
    check("alice likes the tweet", status == 201 and body and body["count"] == 1, f"HTTP {status}")
    status, body = call("POST", "/api/likes", {"tweet_id": tweet_id}, ta)
    check("liking twice keeps one like", status == 200 and body and body["count"] == 1, f"HTTP {status}")
    status, body = call("GET", f"/api/likes?tweet_ids={tweet_id}", token=ta)
    check("alice sees her like in the summary",
          status == 200 and body and body[str(tweet_id)] == {"count": 1, "liked_by_me": True})
    status, body = call("POST", "/api/likes", {"tweet_id": 99999999}, ta)
    check("liking a tweet that does not exist gives 404", status == 404, f"HTTP {status}")

    # 5. The event arrives: bob gets notifications
    def bob_notifications():
        code, data = call("GET", "/api/notifications", token=tb)
        types = {n["type"] for n in (data or {}).get("notifications", [])} if code == 200 else set()
        return data if {"welcome", "like"} <= types else None

    data = wait_for(bob_notifications)
    check("bob gets a welcome and a like notification (events work)", data is not None)
    if data:
        like = next(n for n in data["notifications"] if n["type"] == "like")
        check("the like notification names alice", alice in like["message"], like["message"])
        status, after = call("POST", "/api/notifications/read", token=tb)
        check("bob can mark notifications as read", status == 200 and after == {"unread": 0}, f"HTTP {status}")

    # 6. Ownership rule
    status, _ = call("DELETE", f"/api/tweets/{tweet_id}", token=ta)
    check("alice cannot delete bob's tweet", status == 403, f"HTTP {status}")

    # 7. Unlike, like again, then delete the tweet: the event removes the likes
    status, body = call("DELETE", f"/api/likes/{tweet_id}", token=ta)
    check("alice unlikes", status == 200 and body and body["count"] == 0, f"HTTP {status}")
    call("POST", "/api/likes", {"tweet_id": tweet_id}, ta)
    status, _ = call("DELETE", f"/api/tweets/{tweet_id}", token=tb)
    check("bob deletes his tweet", status == 204, f"HTTP {status}")
    status, _ = call("GET", f"/api/tweets/{tweet_id}")
    check("the deleted tweet is gone", status == 404, f"HTTP {status}")

    def likes_removed():
        code, body = call("GET", f"/api/likes?tweet_ids={tweet_id}", token=ta)
        return code == 200 and body and body[str(tweet_id)]["count"] == 0

    check("the likes of the deleted tweet are removed (tweet.deleted event)", bool(wait_for(likes_removed)))

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
