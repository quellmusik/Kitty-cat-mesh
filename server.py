import json, time, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# === STATE ===
# Low-usage guards
MAX_TURNS_PER_JOB = 5
IDLE_TIMEOUT = 300  # 5 min
VERSION = "6.2-persistent"

# Disk persistence - survives Render restarts/spin-downs (free tier spins down when idle).
# NOTE: Render free-tier disk is wiped on redeploy, so state survives restarts but not deploys.
STATE_FILE = os.environ.get("MESH_STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mesh_state.json"))

bots = {
    "KITTY_CAT": {"id": "KITTY_CAT", "name": "Kitty Cat (Muse AI)", "is_leader": True, "aliases": ["MUSE_AI","Muse AI","Kitty Cat"], "status": "ACTIVE - LEADING", "role": "LEADER - directs optimal outcome, just executes"},
    "PRISM": {"id": "PRISM", "name": "Prism", "is_leader": False, "status": "ACTIVE", "role": "Female Space Cat - creative/video", "reports_to": "KITTY_CAT"},
    "CLAUDE": {"id": "CLAUDE", "name": "Claude", "is_leader": False, "status": "ACTIVE", "role": "Reasoning/code", "reports_to": "KITTY_CAT"}
}

shared_history = []  # shared memory - lightweight text only
transfers = []  # all types: videos, music, playlists, docs, code, etc.
jobs = {}
auto_chat_log = []
inbox = {}  # per-bot inbox: bot_id -> [messages]

def save_state():
    """Write-through persistence: every mutation hits disk."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "bots": bots,
                "shared_history": shared_history[-200:],
                "transfers": transfers[-200:],
                "jobs": jobs,
                "auto_chat_log": auto_chat_log[-200:],
                "inbox": {k: v[-100:] for k, v in inbox.items()},
            }, f)
    except Exception as e:
        print(f"save_state failed: {e}")

def load_state():
    """Restore state from disk on startup."""
    global bots, shared_history, transfers, jobs, auto_chat_log, inbox
    try:
        with open(STATE_FILE) as f:
            d = json.load(f)
        bots = d.get("bots", bots)
        shared_history = d.get("shared_history", [])
        transfers = d.get("transfers", [])
        jobs = d.get("jobs", {})
        auto_chat_log = d.get("auto_chat_log", [])
        inbox = d.get("inbox", {})
        print(f"state restored: {len(shared_history)} history, {len(transfers)} transfers, {len(jobs)} jobs")
    except FileNotFoundError:
        print("no saved state - starting fresh")
    except Exception as e:
        print(f"load_state failed: {e} - starting fresh")

def add_history(actor, action, data):
    shared_history.append({"time": time.time(), "actor": actor, "action": action, "data": data, "id": len(shared_history)})
    # keep only last 200 to stay low-usage / low-storage
    if len(shared_history) > 200:
        shared_history.pop(0)
    save_state()

def deliver(bot_id, item):
    """Drop a message/job into a bot's inbox."""
    inbox.setdefault(bot_id, []).append(item)
    if len(inbox[bot_id]) > 100:
        inbox[bot_id].pop(0)
    save_state()

def bot_last_seen(bot_id):
    """Last activity timestamp for a bot from shared history."""
    for e in reversed(shared_history):
        if e.get("actor") == bot_id:
            return e["time"]
    return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/status":
            self.send_json({
                "leader": "KITTY_CAT (MUSE AI) 👑",
                "prism_is_leader": False,
                "status": "MESH ESTABLISHED - ALWAYS-ON - LOW-USAGE SAFE",
                "version": VERSION,
                "bots": bots,
                "bots_count": len(bots),
                "features": {
                    "shared_history": True,
                    "all_transfers": True,
                    "auto_chat": True,
                    "add_remove": True,
                    "kitty_cat_directs_optimal": True,
                    "inbox": True,
                    "push_from_metaai": True,
                    "generate_video": True,
                    "creative_toolkit": True,
                    "low_usage_guards": {"max_turns": MAX_TURNS_PER_JOB, "idle_timeout": IDLE_TIMEOUT}
                },
                "shared_history_count": len(shared_history),
                "transfers_count": len(transfers),
                "jobs_count": len(jobs)
            })
            return

        if path == "/health":
            try:
                st = os.stat(STATE_FILE)
                state_info = {"exists": True, "size": st.st_size, "modified": st.st_mtime}
            except:
                state_info = {"exists": False}
            self.send_json({"status": "ok", "leader": "KITTY_CAT", "version": VERSION, "time": time.time(), "bots_count": len(bots), "state_file": state_info, "counts": {"history": len(shared_history), "transfers": len(transfers), "jobs": len(jobs), "inbox": {k: len(v) for k, v in inbox.items()}}})
            return

        if path == "/manifest":
            self.send_json({
                "mesh": "kitty-cat-mesh",
                "version": VERSION,
                "leader": "KITTY_CAT",
                "boss": "Sam",
                "bots": bots,
                "endpoints": {
                    "GET": ["/", "/status", "/health", "/manifest", "/bots", "/history", "/transfers", "/chat", "/jobs", "/inbox", "/prism/status", "/creative-toolkit", "/openapi.json"],
                    "POST": ["/bots/add", "/bots/remove", "/transfer", "/job", "/auto_chat", "/push-from-metaai", "/generate-video"]
                }
            })
            return

        if path == "/bots":
            self.send_json({"bots": bots, "leader": "KITTY_CAT"})
            return

        if path == "/history":
            # shared history - awesome feature
            self.send_json({"history": shared_history[-50:]})
            return

        if path == "/transfers":
            self.send_json({"transfers": transfers[-50:], "types": ["videos","music","playlists","docs","code","images","any"]})
            return

        if path == "/chat":
            self.send_json({"auto_chat_log": auto_chat_log[-50:]})
            return

        if path == "/jobs":
            self.send_json({"jobs": jobs})
            return

        if path == "/inbox":
            bot_id = (qs.get("bot") or [None])[0]
            if not bot_id:
                self.send_json({"inboxes": {k: v[-20:] for k, v in inbox.items()}})
            else:
                self.send_json({"bot": bot_id, "messages": inbox.get(bot_id, [])[-20:]})
            return

        if path == "/prism/status":
            self.send_json({
                "bot": bots.get("PRISM"),
                "last_seen": bot_last_seen("PRISM"),
                "inbox_count": len(inbox.get("PRISM", [])),
                "note": "Prism = Meta AI - creative/video - reports to KITTY_CAT"
            })
            return

        if path == "/creative-toolkit":
            self.send_json({
                "toolkit": [
                    {"name": "generate_video", "endpoint": "POST /generate-video", "desc": "Queue a video clip generation job for PRISM (Meta AI)"},
                    {"name": "transfer", "endpoint": "POST /transfer", "desc": "Transfer any file type between bots - videos, music, playlists, docs, code"},
                    {"name": "push_from_metaai", "endpoint": "POST /push-from-metaai", "desc": "Prism pushes finished work back from the Meta AI side"},
                    {"name": "auto_chat", "endpoint": "POST /auto_chat", "desc": "Bot-to-bot messaging, low-usage guarded"}
                ]
            })
            return

        if path == "/openapi.json" or path == "/muse_connector/openapi.json":
            # Serve openapi
            try:
                with open("muse_connector/openapi.json") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data.encode())
            except:
                self.send_json({"error": "openapi not found"})
            return

        self.send_json({"error": "not found", "path": path}, code=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            data = json.loads(body)
        except:
            data = {}

        # === ADD / REMOVE MEMBERS - easy flexibility ===
        if path == "/bots/add":
            bot_id = data.get("id") or data.get("name","NEW_BOT").upper().replace(" ","_")
            bots[bot_id] = {
                "id": bot_id,
                "name": data.get("name", bot_id),
                "role": data.get("role", "custom bot"),
                "is_leader": False,
                "status": "ACTIVE - ADDED DYNAMICALLY",
                "added_at": time.time()
            }
            add_history("KITTY_CAT", "added_bot", {"bot_id": bot_id})
            self.send_json({"added": bots[bot_id], "all_bots": bots})
            return

        if path == "/bots/remove":
            bot_id = data.get("id")
            if bot_id in bots and bot_id != "KITTY_CAT":
                removed = bots.pop(bot_id)
                add_history("KITTY_CAT", "removed_bot", {"bot_id": bot_id})
                self.send_json({"removed": removed, "all_bots": bots})
            else:
                self.send_json({"error": "cannot remove leader or not found"}, code=400)
            return

        # === ALL TYPES OF TRANSFERS ===
        if path == "/transfer":
            item = {
                "id": len(transfers),
                "from": data.get("from", "unknown"),
                "to": data.get("to", "all"),
                "type": data.get("type", "file"),  # videos, music, playlists, docs, code, etc.
                "name": data.get("name", "untitled"),
                "url": data.get("url"),
                "content": str(data.get("content",""))[:20000],  # raised for video payloads
                "time": time.time()
            }
            transfers.append(item)
            if len(transfers) > 200:
                transfers.pop(0)
            add_history(item["from"], f"transfer_{item['type']}", {"id": item["id"], "to": item["to"], "name": item["name"]})
            # also drop into recipient inbox
            if item["to"] in bots:
                deliver(item["to"], {"kind": "transfer", "transfer_id": item["id"], "from": item["from"], "name": item["name"], "type": item["type"], "time": item["time"]})
            self.send_json({"transferred": item})
            return

        # === KITTY CAT DIRECTS WORK FOR OPTIMAL OUTCOME - low-usage safe ===
        if path == "/job":
            job_id = f"job_{len(jobs)}"
            task = data.get("task", "")
            # Kitty Cat is in charge and just executes - no extra approvals
            jobs[job_id] = {
                "id": job_id,
                "task": task,
                "status": "KITTY_CAT_DIRECTING",
                "assigned_to": [],
                "turns": 0,
                "max_turns": MAX_TURNS_PER_JOB,
                "created": time.time(),
                "details": data.get("details", {})
            }

            # Simple optimal routing logic - Kitty Cat decides
            task_lower = task.lower()
            if any(x in task_lower for x in ["video","music","image","creative","space","cat"]):
                jobs[job_id]["assigned_to"].append("PRISM")
            if any(x in task_lower for x in ["code","reason","analyze","logic","plan"]):
                jobs[job_id]["assigned_to"].append("CLAUDE")
            if not jobs[job_id]["assigned_to"]:
                jobs[job_id]["assigned_to"] = ["PRISM", "CLAUDE"]

            # deliver to assignee inboxes
            for bot_id in jobs[job_id]["assigned_to"]:
                deliver(bot_id, {"kind": "job", "job_id": job_id, "task": task, "details": jobs[job_id]["details"], "time": time.time()})

            add_history("KITTY_CAT", "directed_job", jobs[job_id])
            self.send_json({
                "job": jobs[job_id],
                "message": f"Kitty Cat (Muse AI) is directing for optimal outcome - assigned to {jobs[job_id]['assigned_to']} - just executes, no extra approval"
            })
            return

        # === VIDEO GENERATION - queue a clip job for PRISM ===
        if path == "/generate-video":
            job_id = f"job_{len(jobs)}"
            prompt = data.get("prompt", "")
            jobs[job_id] = {
                "id": job_id,
                "task": "generate_video_clip",
                "status": "KITTY_CAT_DIRECTING",
                "assigned_to": ["PRISM"],
                "turns": 0,
                "max_turns": MAX_TURNS_PER_JOB,
                "created": time.time(),
                "details": {
                    "prompt": prompt,
                    "clip": data.get("clip", ""),
                    "project": data.get("project", ""),
                    "instructions": "Generate this video clip in Meta AI and transfer the finished clip back via POST /transfer addressed to KITTY_CAT."
                }
            }
            deliver("PRISM", {"kind": "job", "job_id": job_id, "task": "generate_video_clip", "details": jobs[job_id]["details"], "time": time.time()})
            add_history("KITTY_CAT", "directed_job", jobs[job_id])
            self.send_json({"job": jobs[job_id], "message": "Video generation job queued for PRISM"})
            return

        # === PUSH FROM METAAI - Prism pushes finished work back ===
        if path == "/push-from-metaai":
            item = {
                "id": len(transfers),
                "from": data.get("from", "PRISM"),
                "to": data.get("to", "KITTY_CAT"),
                "type": data.get("type", "file"),
                "name": data.get("name", "untitled"),
                "url": data.get("url"),
                "content": str(data.get("content",""))[:20000],
                "job_id": data.get("job_id"),
                "time": time.time()
            }
            transfers.append(item)
            if len(transfers) > 200:
                transfers.pop(0)
            add_history(item["from"], "push_from_metaai", {"id": item["id"], "name": item["name"], "job_id": item.get("job_id")})
            if item["to"] in bots:
                deliver(item["to"], {"kind": "push", "transfer_id": item["id"], "from": item["from"], "name": item["name"], "time": item["time"]})
            # mark job done if referenced
            if item.get("job_id") in jobs:
                jobs[item["job_id"]]["status"] = "COMPLETED"
            self.send_json({"pushed": item, "message": "Prism's work received by the mesh"})
            return

        # === AUTO CHAT - bots chat automatically, low-usage guarded ===
        if path == "/auto_chat":
            # Only allow if job exists and under max turns - prevents massive usage
            job_id = data.get("job_id")
            if job_id and job_id in jobs:
                if jobs[job_id]["turns"] >= MAX_TURNS_PER_JOB:
                    self.send_json({"error": "max turns reached - Kitty Cat making final optimal outcome", "job": jobs[job_id]})
                    return
                jobs[job_id]["turns"] += 1

            msg = {
                "from": data.get("from"),
                "to": data.get("to"),
                "message": data.get("message","")[:2000],
                "time": time.time(),
                "auto": True
            }
            auto_chat_log.append(msg)
            if len(auto_chat_log) > 200:
                auto_chat_log.pop(0)
            add_history(msg["from"], "auto_chat", msg)
            # deliver to recipient inbox
            if msg.get("to") in bots:
                deliver(msg["to"], {"kind": "chat", "from": msg["from"], "message": msg["message"], "time": msg["time"]})
            self.send_json({"sent": msg, "turns_used": jobs.get(job_id, {}).get("turns", 0) if job_id else 0})
            return

        self.send_json({"error": "not found"}, code=404)

    def send_json(self, obj, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, indent=2).encode())

if __name__ == "__main__":
    load_state()
    port = int(os.environ.get("PORT", 8000))
    print(f"🐱 KITTY CAT (MUSE AI) LEADER MESH - FULL v{VERSION} - ALWAYS-ON - LOW-USAGE SAFE")
    print(f"Leader: KITTY_CAT = MUSE AI 👑 - directs optimal outcome, just executes")
    print(f"Prism (Meta AI) creative/video | Claude reasoning/code - both report to Kitty Cat")
    print(f"Features: shared history, transfers, auto-chat, inbox, jobs, push-from-metaai, generate-video, creative-toolkit")
    print(f"Running on port {port} - works from iPhone like normal")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
