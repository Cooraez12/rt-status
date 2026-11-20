"""RT.app status checks.

Calls RT's own public endpoints only, records up / slow / down for each
service, and keeps 90 days of daily uptime. Only the result is stored:
response bodies, versions and internal names are never written out.
Also copies staff incident notes (GitHub issues labelled "incident") into
docs/data/incidents.json.
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
UA = "RT-Status-Check/1.0 (+https://status.rt.app)"
TIMEOUT = 20
SLOW_SECONDS = 8
KEEP_DAYS = 90
KEEP_RECENT = 288  # 24 hours of 5-minute checks

APP = "https://app.rt.app"
CHECKS = {
    "website": ("page", "https://rt.app/"),
    "signin": ("page", APP + "/login"),
    "payments_core": ("health", APP + "/payment-api/health"),
    "banking_core": ("health", APP + "/banking-api/health"),
    "payments_jobs": ("queue", APP + "/payment-api/health/queues"),
    "banking_jobs": ("queue", APP + "/banking-api/health/queues"),
}

COMPONENTS = [
    ("website", "Website & sign in", "Our website, the RT.app web app and signing in.",
     ["website", "signin", "payments_core"]),
    ("accounts", "Accounts & balances", "Seeing your accounts, balances and activity.",
     ["signin", "banking_core"]),
    ("cards", "Card payments", "Paying with your RT.app virtual cards.",
     ["banking_core", "banking_jobs"]),
    ("add_money", "Add money", "Adding money to your RT.app account.",
     ["payments_core", "payments_jobs"]),
    ("bank_transfers", "Bank transfers", "Sending and receiving bank transfers.",
     ["banking_core", "banking_jobs"]),
    ("payouts", "International payouts", "Sending money to people and businesses abroad.",
     ["banking_core", "banking_jobs"]),
    ("checkout", "Merchant checkout", "Checkout pages and payment links for businesses.",
     ["signin", "payments_core", "payments_jobs"]),
    ("api", "API", "The RT.app API for developers.",
     ["payments_core", "banking_core"]),
]

RANK = {"up": 0, "slow": 1, "down": 2}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(200_000)
            return r.status, body, time.monotonic() - start
    except urllib.error.HTTPError as e:
        return e.code, e.read(200_000) if e.fp else b"", time.monotonic() - start
    except Exception:
        return 0, b"", time.monotonic() - start


def judge(kind, status, body, seconds):
    if kind == "page":
        result = "up" if status == 200 else "down"
    else:
        try:
            state = json.loads(body).get("status")
        except Exception:
            state = None
        if kind == "health":
            if status == 200 and state == "ok":
                result = "up"
            elif status == 200:
                result = "slow"
            else:
                result = "down"
        else:  # background job queues: a backlog means delays, not an outage
            result = "up" if status == 200 and state in ("ok", "warn") else "slow"
    if result == "up" and seconds > SLOW_SECONDS:
        result = "slow"
    return result


def run_check(kind, url):
    result, seconds = "down", 0.0
    for attempt in range(2):  # one retry so a single blip is not an outage
        status, body, seconds = fetch(url)
        result = judge(kind, status, body, seconds)
        if result == "up":
            break
        time.sleep(5)
    return result, seconds


def load(name, default):
    try:
        with open(os.path.join(DATA, name)) as f:
            return json.load(f)
    except Exception:
        return default


def save(name, obj):
    with open(os.path.join(DATA, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")


def run_checks(now):
    raw = {key: run_check(kind, url) for key, (kind, url) in CHECKS.items()}
    history = load("history.json", {})
    today = now.date().isoformat()
    cutoff = (now.date() - dt.timedelta(days=KEEP_DAYS - 1)).isoformat()
    components = []
    for cid, name, about, keys in COMPONENTS:
        state = max((raw[k][0] for k in keys), key=RANK.get)
        ms = int(max(raw[k][1] for k in keys) * 1000)
        h = history.setdefault(cid, {"days": {}, "recent": []})
        day = h["days"].setdefault(today, {"n": 0, "up": 0, "slow": 0, "down": 0})
        day["n"] += 1
        day[state] += 1
        h["days"] = {d: v for d, v in h["days"].items() if d >= cutoff}
        h["recent"] = (h["recent"] + [[now.strftime("%Y-%m-%dT%H:%MZ"), state]])[-KEEP_RECENT:]
        components.append({"id": cid, "name": name, "about": about, "status": state, "ms": ms})
    save("history.json", history)
    save("status.json", {"checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "components": components})


def gh(path):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


STAFF = {"OWNER", "MEMBER", "COLLABORATOR"}


def clean(text):
    """Plain text only: drop template comments and trim."""
    return re.sub(r"<!--.*?-->", "", text or "", flags=re.S).strip()[:2000]


def update_incidents(now):
    try:
        issues = gh("/issues?labels=incident&state=all&per_page=30&sort=created&direction=desc")
    except Exception:
        return  # keep the last saved incidents if GitHub is unreachable
    if issues is None:
        return
    recent = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for i in issues:
        if "pull_request" in i or i.get("author_association") not in STAFF:
            continue
        if i["state"] == "closed" and (i.get("closed_at") or "") < recent:
            continue
        updates = []
        try:
            for c in gh(f"/issues/{i['number']}/comments?per_page=50") or []:
                if c.get("author_association") in STAFF and clean(c.get("body")):
                    updates.append({"at": c["created_at"], "text": clean(c.get("body"))})
        except Exception:
            pass
        out.append({
            "title": i["title"][:200],
            "text": clean(i.get("body")),
            "opened_at": i["created_at"],
            "resolved_at": i.get("closed_at") if i["state"] == "closed" else None,
            "updates": updates,
        })
    save("incidents.json", out)


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    if os.environ.get("SKIP_CHECKS") != "1":
        run_checks(now)
    update_incidents(now)
