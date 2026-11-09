"""Site uptime check: post to Google Chat when a site goes down or comes back.

Runs on GitHub Actions. State lives in state.json (committed only on change).
"""
import datetime, json, os, pathlib, time, urllib.request, urllib.error

SITES = [
    {"name": "yogapalooza.com", "url": "https://yogapalooza.com/", "must_contain": "Yogapalooza"},
]
BAD_MARKERS = ["DEPLOYMENT_DISABLED", "DEPLOYMENT_PAUSED", "temporarily paused", "Payment required"]
REMIND_EVERY = datetime.timedelta(hours=3)
STATE = pathlib.Path(__file__).with_name("state.json")
UA = "Mozilla/5.0 (site-uptime check)"


def probe(site):
    """Return None if healthy, else a short reason. Retries 3x so one blip is not an outage."""
    reason = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(site["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read(200_000).decode("utf-8", "replace")
            bad = next((m for m in BAD_MARKERS if m.lower() in body.lower()), None)
            if bad:
                reason = f"trang báo \"{bad}\""
            elif site["must_contain"] not in body:
                reason = "trang trả về nội dung lạ"
            else:
                return None
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
        except Exception as e:
            reason = f"không kết nối được ({type(e).__name__})"
        time.sleep(30)
    return reason


def post(text):
    hook = os.environ.get("CHAT_WEBHOOK")
    if not hook:
        print("[no webhook] " + text)
        return
    req = urllib.request.Request(hook, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json; charset=UTF-8"})
    urllib.request.urlopen(req, timeout=20).read()


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = datetime.datetime.now(datetime.timezone.utc)
    for site in SITES:
        s = state.get(site["name"], {"down": False})
        reason = probe(site)
        if reason and not s["down"]:
            post(f"🔴 {site['name']} đang SẬP: {reason}\n{site['url']}")
            s = {"down": True, "since": now.isoformat(), "reminded": now.isoformat(), "reason": reason}
        elif reason and now - datetime.datetime.fromisoformat(s["reminded"]) >= REMIND_EVERY:
            mins = int((now - datetime.datetime.fromisoformat(s["since"])).total_seconds() // 60)
            post(f"🔴 {site['name']} vẫn sập ({mins // 60}h{mins % 60:02d}): {reason}\n{site['url']}")
            s["reminded"] = now.isoformat()
        elif not reason and s["down"]:
            mins = int((now - datetime.datetime.fromisoformat(s["since"])).total_seconds() // 60)
            post(f"🟢 {site['name']} đã lên lại (sập {mins // 60}h{mins % 60:02d}).")
            s = {"down": False}
        print(site["name"], "DOWN " + reason if reason else "ok")
        state[site["name"]] = s
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
