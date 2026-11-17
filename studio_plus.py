"""Pages added in the November 2026 rebuild: Scripts (script-first review), Competitors, References, Costs,
Voices and Prompts. Kept apart from app.py so the older pages are untouched. Call register(app) once.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import abort, flash, g, jsonify, redirect, render_template, request, send_from_directory, url_for

from core import ai, competitors, ledger, playbook, refs
from core import team as teamlib
from core.config import load_settings, save_settings
from core.store import all_posts, get_post, now_iso, save_post

OPEN = ("idea", "draft", "designed")


def decision(p: dict) -> str:
    return (p.get("script_decision") or {}).get("choice") or "pending"


def media_blocked(p: dict) -> bool:
    """Media may be made only after the script is chosen. Posts already past drafting are left alone."""
    return p.get("platform") != "newsletter" and p.get("status") in ("idea", "draft") and decision(p) != "use"


def waiting_scripts(days: int | None = None) -> list[dict]:
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat() if days else "9999"
    out = [p for p in all_posts() if p.get("platform") != "newsletter" and p.get("status") in ("idea", "draft")
           and today <= p.get("date", "") <= end and decision(p) != "use"]
    return sorted(out, key=lambda p: (p.get("date", ""), p.get("time", "")))


def _actor() -> str:
    u = getattr(g, "user", None) or {}
    return u.get("name") or u.get("email") or "Someone"


def _can_edit() -> bool:
    return teamlib.can_edit(getattr(g, "user", None) or {})


def register(app):
    @app.context_processor
    def _plus_counts():
        try:
            posts = all_posts()
            live = competitors.live()
            days = None
            if live.get("scanned_at"):
                days = (date.today() - date.fromisoformat(live["scanned_at"][:10])).days
            plus = {"briefs": sum(1 for p in posts if decision(p) == "use" and p.get("status") in ("idea", "draft")),
                    "rewrites": sum(1 for p in posts if decision(p) == "rewrite"),
                    "comp_days": days, "comp_usd": competitors.scan_estimate()["usd"]}
            return {"scripts_waiting": len(waiting_scripts(14)), "plus": plus,
                    "refs_to_read": sum(1 for r in refs.all_refs() if r["status"] == "to_read")}
        except Exception:
            return {"scripts_waiting": 0, "refs_to_read": 0,
                    "plus": {"briefs": 0, "rewrites": 0, "comp_days": None, "comp_usd": 0}}

    # ------------------------------------------------------------ scripts: read first, then decide
    @app.route("/scripts")
    def scripts_page():
        span = request.args.get("days", "14")
        days = None if span == "all" else int(span) if span.isdigit() else 14
        posts = waiting_scripts(days)
        v = request.args.get("voice") or ""
        plat = request.args.get("p") or ""
        if v:
            posts = [p for p in posts if (p.get("voice") or "company") == v]
        if plat:
            posts = [p for p in posts if p.get("platform") == plat]
        chosen = sorted((p for p in all_posts() if decision(p) == "use" and p.get("status") in ("idea", "draft")),
                        key=lambda p: p.get("date", ""))
        return render_template("scripts.html", posts=posts, span=span, v=v, plat=plat, chosen=chosen,
                               queued=playbook.queued(), total=len(waiting_scripts(None)))

    @app.post("/api/post/<pid>/decision")
    def api_decision(pid):
        if not _can_edit():
            return jsonify(ok=False, error="You don't have permission to decide on scripts."), 403
        p = get_post(pid)
        if not p:
            return jsonify(ok=False, error="Post not found"), 404
        data = request.get_json(silent=True) or {}
        choice = data.get("decision")
        if choice == "use":
            p["script_decision"] = {"choice": "use", "by": _actor(), "at": now_iso()}
            saved = save_post(p, note=f"{_actor()}: chose this script. Media can now be made.")
            path = playbook.queue_media(saved)
            return jsonify(ok=True, id=saved["id"], message="Script chosen. A media brief is waiting for the Claude terminal.", brief=path)
        if choice == "reset":
            p["script_decision"] = {"choice": "pending", "by": _actor(), "at": now_iso()}
            saved = save_post(p, note=f"{_actor()}: script decision cleared")
            playbook.unqueue_media(saved)
            return jsonify(ok=True, id=saved["id"])
        if choice == "new":
            content = (data.get("content") or "").strip()
            if len(content) < 40:
                return jsonify(ok=False, error="Paste the content to write from (a few lines at least)."), 400
            if data.get("how") == "terminal":
                p["script_decision"] = {"choice": "rewrite", "by": _actor(), "at": now_iso(), "content": content}
                saved = save_post(p, note=f"{_actor()}: asked for a new script from their own content (Claude terminal)")
                return jsonify(ok=True, id=saved["id"], message="Saved. Ask the Claude terminal to write the waiting scripts; no API charge.")
            try:
                new = ai.draft_post(p, brief=content)
            except ai.AIError as e:
                return jsonify(ok=False, error=str(e)), 400
            new["script_decision"] = {"choice": "pending", "by": _actor(), "at": now_iso(), "content": content, "rewritten": True}
            new["images"] = p.get("images") or []
            saved = save_post(new, note=f"{_actor()}: new script written from their own content")
            playbook.unqueue_media(saved)
            return jsonify(ok=True, id=saved["id"], message="New script written. Read it, then choose it or change it again.")
        return jsonify(ok=False, error="Unknown choice"), 400

    # ------------------------------------------------------------ competitors
    @app.route("/competitors")
    def competitors_page():
        r = competitors.research()
        live_d = competitors.live()
        short = lambda n: (n or "").split(" (")[0].split(" /")[0]
        feed = []
        for p in live_d.get("posts") or []:
            feed.append({"date": p.get("posted_at") or "", "who": short(p["competitor"]), "kind": p["channel"] + " post",
                         "what": p["text"], "url": p["url"],
                         "meta": f"{p['likes']:,} likes · {p['comments']:,} comments" + (f" · {p['shares']:,} shares" if p.get("shares") else "")})
        for c in r["competitors"]:
            for mv in c.get("recent_moves") or []:
                feed.append({"date": str(mv.get("date") or ""), "who": short(c["name"]), "kind": "Company move",
                             "what": mv.get("what") or "", "url": mv.get("source") or "", "meta": ""})
        for e in competitors.log():
            feed.append({"date": e["date"], "who": short(e["competitor"]), "kind": "Noted by us · " + (e.get("kind") or ""),
                         "what": e["what"] + ((" · Idea: " + e["idea"]) if e.get("idea") else ""), "url": e.get("url") or "",
                         "meta": e.get("works") or "", "log_id": e["id"]})
        dated = sorted((f for f in feed if f["date"][:4].isdigit() and len(f["date"]) >= 7 and f["date"][4] == "-"),
                       key=lambda f: f["date"], reverse=True)
        undated = [f for f in feed if f not in dated]
        whos = sorted({f["who"] for f in feed}, key=lambda n: (n != "Hawky", n.lower()))
        return render_template("competitors.html", r=r, log=competitors.log(), kinds=competitors.KINDS,
                               feed=dated + undated, whos=whos,
                               live=competitors.live(), est=competitors.scan_estimate(),
                               names=competitors.names(), today=date.today().isoformat())

    @app.post("/api/competitors/log")
    def api_comp_log():
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        d = request.get_json(silent=True) or {}
        if not (d.get("competitor") or "").strip() or not (d.get("what") or "").strip():
            return jsonify(ok=False, error="Name the competitor and say what you saw."), 400
        e = competitors.add_log(d["competitor"], d["what"], d.get("url", ""), d.get("kind", ""), d.get("works", ""),
                                d.get("idea", ""), d.get("date", ""), _actor())
        return jsonify(ok=True, id=e["id"])

    @app.post("/api/competitors/log/<eid>/delete")
    def api_comp_log_delete(eid):
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        competitors.delete_log(eid)
        return jsonify(ok=True)

    @app.post("/api/competitors/scan")
    def api_comp_scan():
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        if not competitors.start_scan():
            return jsonify(ok=True, already=True)
        return jsonify(ok=True)

    @app.get("/api/competitors/scan")
    def api_comp_scan_status():
        return jsonify(ok=True, **competitors.scan_status())

    @app.post("/api/competitors/insight")
    def api_comp_insight():
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        try:
            competitors.insight()
        except ai.AIError as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True)

    # ------------------------------------------------------------ references
    @app.route("/references")
    def references_page():
        return render_template("references.html", days=refs.by_day(), today=date.today().isoformat(),
                               open_id=request.args.get("open", ""), n=len(refs.all_refs()))

    @app.post("/references/add")
    def references_add():
        if not _can_edit():
            abort(403)
        f = request.form
        up = request.files.get("file")
        if not (f.get("url") or f.get("text") or (up and up.filename)):
            flash("Paste a link, some text, or choose a file.", "err")
            return redirect(url_for("references_page"))
        item = refs.add(url=f.get("url", ""), text=f.get("text", ""), title=f.get("title", ""),
                        shared_by=f.get("shared_by", "KC"), day=f.get("date", ""), note=f.get("note", ""), upload=up)
        flash(("Saved. " + item["problem"]) if item.get("problem") else
              f"Saved under {item['date']} with {item['chars']:,} characters of text. Run the deep dive when you're ready.",
              "warn" if item.get("problem") else "ok")
        return redirect(url_for("references_page", open=item["id"]))

    @app.post("/api/references/<rid>/summarise")
    def api_ref_summarise(rid):
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        try:
            refs.summarise(rid)
        except ai.AIError as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True)

    @app.post("/api/references/<rid>/text")
    def api_ref_text(rid):
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        refs.add_text(rid, (request.get_json(silent=True) or {}).get("text", ""))
        return jsonify(ok=True)

    @app.post("/api/references/<rid>/delete")
    def api_ref_delete(rid):
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        refs.delete(rid)
        return jsonify(ok=True)

    @app.post("/api/references/<rid>/todo")
    def api_ref_todo(rid):
        """Put one 'change to make' from a reference on the Playbook checklist, so it gets an owner and a status."""
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        import json as _json
        from core.config import DATA
        r = refs.get(rid)
        text = ((request.get_json(silent=True) or {}).get("text") or "").strip()
        if not r or not text:
            return jsonify(ok=False, error="Nothing to add"), 400
        f = DATA / "gaps.json"
        try:
            items = _json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        if any(i.get("title") == text for i in items):
            return jsonify(ok=True, already=True)
        items.append({"id": f"r{len(items) + 1:03d}{rid[-4:]}", "group": "From references", "title": text,
                      "why": f"From: {r['title']} (shared by {r.get('shared_by', '')}, {r.get('date', '')})", "how": "",
                      "priority": "Medium", "status": "todo", "owner": "", "updated": now_iso()})
        f.write_text(_json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        return jsonify(ok=True)

    @app.get("/references/file/<rid>/<path:name>")
    def references_file(rid, name):
        r = refs.get(rid)
        if not r or name not in (r.get("files") or []):
            abort(404)
        return send_from_directory(refs.DIR / r["folder"], name)

    # ------------------------------------------------------------ Instagram numbers by hand
    @app.post("/api/results/instagram/upload")
    def api_ig_upload():
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        from core import analytics as an, ig_manual
        f = request.files.get("file")
        if not f or not (f.filename or "").lower().endswith((".csv", ".txt", ".tsv")):
            return jsonify(ok=False, error="Choose a .csv file (the Meta Business Suite export or the Studio template)."), 400
        try:
            out = ig_manual.import_csv(f.read())
        except an.AnalyticsError as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True, **out)

    @app.post("/api/results/instagram/day")
    def api_ig_day():
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        from core import analytics as an, ig_manual
        d = request.get_json(silent=True) or {}
        try:
            out = ig_manual.save_day(d.get("date"), d.get("followers"), d.get("reach"), d.get("profile_views"), d.get("new_followers"))
        except an.AnalyticsError as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True, saved=out)

    @app.get("/results/instagram-template.csv")
    def ig_template():
        from flask import Response
        from core import ig_manual
        return Response(ig_manual.template_csv(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=instagram-results-template.csv"})

    # ------------------------------------------------------------ costs
    @app.route("/costs")
    def costs_page():
        s = load_settings()
        return render_template("costs.html", r=ledger.report(), prices=ledger.AI_PRICES, model=s.get("anthropic_model"),
                               hiker_limit=ledger.hiker_search_limit(), today=date.today().isoformat(),
                               fallback=ai.LAST_FALLBACK)

    @app.post("/api/costs/caps")
    def api_costs_caps():
        if (getattr(g, "user", None) or {}).get("role") not in ("admin", "approver"):
            return jsonify(ok=False, error="Only an admin or approver can change limits."), 403
        d = request.get_json(silent=True) or {}
        s = load_settings()
        try:
            if "ai" in d:
                s["ai_monthly_cap_usd"] = max(0.0, float(d["ai"]))
            if "research" in d:
                s["discover_daily_cap_usd"] = max(0.0, float(d["research"]))
        except (TypeError, ValueError):
            return jsonify(ok=False, error="Limits must be numbers."), 400
        save_settings(s)
        return jsonify(ok=True)

    @app.post("/api/costs/manual")
    def api_costs_manual():
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        d = request.get_json(silent=True) or {}
        try:
            usd = float(d.get("usd"))
        except (TypeError, ValueError):
            return jsonify(ok=False, error="Enter the amount in US dollars."), 400
        if not (d.get("what") or "").strip():
            return jsonify(ok=False, error="Say what it was for."), 400
        ledger.record((d.get("provider") or "other").strip().lower(), d["what"].strip(), usd, cap=False,
                      note=f"entered by {_actor()}")
        return jsonify(ok=True)

    # ------------------------------------------------------------ voices and prompts
    @app.route("/voices")
    def voices_page():
        posts = all_posts()
        counts = {}
        for p in posts:
            if p.get("platform") == "linkedin":
                counts[p.get("voice") or "company"] = counts.get(p.get("voice") or "company", 0) + 1
        return render_template("voices.html", voices=playbook.voices(), counts=counts)

    @app.post("/api/voices/<key>")
    def api_voice_save(key):
        if not _can_edit():
            return jsonify(ok=False, error="No permission"), 403
        d = request.get_json(silent=True) or {}
        if "samples_text" in d:
            d["samples"] = [s for s in d["samples_text"].split("\n---\n")]
        playbook.save_voice(key, d)
        return jsonify(ok=True, samples=len(playbook.voices()[key]["samples"]))

    @app.route("/prompts", methods=["GET", "POST"])
    def prompts_page():
        if request.method == "POST":
            if not _can_edit():
                return jsonify(ok=False, error="No permission"), 403
            d = request.get_json(silent=True) or {}
            if d.get("reset"):
                cur = {k: v["text"] for k, v in playbook.prompts().items() if k != d["reset"]}
                playbook.save_prompts(cur)
            else:
                cur = {k: v["text"] for k, v in playbook.prompts().items()}
                cur.update({k: v for k, v in d.items() if k in playbook.DEFAULTS})
                playbook.save_prompts(cur)
            return jsonify(ok=True)
        return render_template("prompts.html", prompts=playbook.prompts())
