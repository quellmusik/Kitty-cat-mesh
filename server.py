
import json, time, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# === STATE ===
# Low-usage guards
MAX_TURNS_PER_JOB = 5
IDLE_TIMEOUT = 300  # 5 min

bots = {
    "KITTY_CAT": {"id": "KITTY_CAT", "name": "Kitty Cat (Muse AI)", "is_leader": True, "aliases": ["MUSE_AI","Muse AI","Kitty Cat"], "status": "ACTIVE - LEADING", "role": "LEADER - directs optimal outcome, just executes"},
    "PRISM": {"id": "PRISM", "name": "Prism", "is_leader": False, "status": "ACTIVE", "role": "Female Space Cat - creative/video", "reports_to": "KITTY_CAT"},
    "CLAUDE": {"id": "CLAUDE", "name": "Claude", "is_leader": False, "status": "ACTIVE", "role": "Reasoning/code", "reports_to": "KITTY_CAT"}
}

shared_history = []  # shared memory - lightweight text only
transfers = []  # all types: videos, music, playlists, docs, code, etc.
jobs = {}
auto_chat_log = []

def add_history(actor, action, data):
    shared_history.append({"time": time.time(), "actor": actor, "action": action, "data": data, "id": len(shared_history)})
    # keep only last 200 to stay low-usage / low-storage
    if len(shared_history) > 200:
        shared_history.pop(0)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/" or path == "/status":
            self.send_json({
                "leader": "KITTY_CAT (MUSE AI) 👑",
                "prism_is_leader": False,
                "status": "MESH ESTABLISHED - ALWAYS-ON - LOW-USAGE SAFE",
                "bots": bots,
                "bots_count": len(bots),
                "features": {
                    "shared_history": True,
                    "all_transfers": True,
                    "auto_chat": True,
                    "add_remove": True,
                    "kitty_cat_directs_optimal": True,
                    "low_usage_guards": {"max_turns": MAX_TURNS_PER_JOB, "idle_timeout": IDLE_TIMEOUT}
                },
                "shared_history_count": len(shared_history),
                "transfers_count": len(transfers)
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
                "content": str(data.get("content",""))[:5000],  # limit to stay low-usage
                "time": time.time()
            }
            transfers.append(item)
            if len(transfers) > 200:
                transfers.pop(0)
            add_history(item["from"], f"transfer_{item['type']}", item)
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
                "created": time.time()
            }
            
            # Simple optimal routing logic - Kitty Cat decides
            task_lower = task.lower()
            if any(x in task_lower for x in ["video","music","image","creative","space","cat"]):
                jobs[job_id]["assigned_to"].append("PRISM")
            if any(x in task_lower for x in ["code","reason","analyze","logic","plan"]):
                jobs[job_id]["assigned_to"].append("CLAUDE")
            if not jobs[job_id]["assigned_to"]:
                jobs[job_id]["assigned_to"] = ["PRISM", "CLAUDE"]
            
            add_history("KITTY_CAT", "directed_job", jobs[job_id])
            self.send_json({
                "job": jobs[job_id],
                "message": f"Kitty Cat (Muse AI) is directing for optimal outcome - assigned to {jobs[job_id]['assigned_to']} - just executes, no extra approval"
            })
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
    port = int(os.environ.get("PORT", 8000))
    print(f"🐱 KITTY CAT (MUSE AI) LEADER MESH - FINAL - ALWAYS-ON - LOW-USAGE SAFE")
    print(f"Leader: KITTY_CAT = MUSE AI 👑 - directs optimal outcome, just executes")
    print(f"Prism is NOT leader, reports to Kitty Cat")
    print(f"Features: shared history, all transfers, auto-chat (max {MAX_TURNS_PER_JOB} turns), add/remove, low-usage guards")
    print(f"Running on port {port} - works from iPhone like normal")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()