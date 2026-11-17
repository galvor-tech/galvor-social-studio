"""AI copywriting engine. Drafts / rewrites posts in Galvor's voice and returns post-schema JSON.

Provider order (Settings → AI): Claude (ANTHROPIC_API_KEY or `ant auth login` profile) → Gemini (GEMINI_API_KEY).
Every AI output is validated by core.lint; if blocking issues remain, the model gets one repair pass.
"""
from __future__ import annotations

import json
import os
import re

from .config import DATA, FORMATS, PILLARS, RHYTHM, VOICES, load_env, load_settings
from . import ledger, playbook
from .lint import has_errors, lint_post

load_env()

SPEC = (DATA / "CONTENT_SPEC.md").read_text(encoding="utf-8") if (DATA / "CONTENT_SPEC.md").exists() else ""

SYSTEM = f"""You are Galvor's senior social content strategist and copywriter.
You write LinkedIn and Instagram posts that are specific, useful and in the right person's voice.
Follow this spec exactly — it is the brand guide, the rulebook and the JSON schema:

{SPEC}

Output: ONE JSON object for the post (the schema in section 7), no prose, no markdown fences.
Use only numbers from the facts bank; if none fits, use no number. Never invent clients, quotes or results.
Allowed pillars: {json.dumps(PILLARS)}. Allowed formats: {json.dumps(FORMATS)}. Voices: {list(VOICES)}."""


class AIError(RuntimeError):
    pass


class NoCredit(AIError):
    """The Claude API account has no credit left."""


LAST_FALLBACK = {"at": "", "why": ""}      # shown on Costs so a silent switch of writer is never hidden


def provider() -> str:
    s = load_settings()
    choice = s.get("ai_provider", "auto")
    if choice in ("anthropic", "gemini"):
        return choice
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "none"


def status() -> dict:
    p = provider()
    s = load_settings()
    model = s.get("anthropic_model") if p == "anthropic" else (s.get("gemini_model") or os.getenv("GEMINI_MODEL", "")) if p == "gemini" else ""
    return {"provider": p, "model": model, "ready": p != "none"}


# ---------------------------------------------------------------- providers
def claude_client(timeout: float = 180.0):
    """Anthropic client. This key isn't scoped to one workspace, so every request must name it
    (ANTHROPIC_WORKSPACE_ID in .env -> anthropic-workspace-id header)."""
    import anthropic
    ws = os.getenv("ANTHROPIC_WORKSPACE_ID")
    return anthropic.Anthropic(timeout=timeout, max_retries=2,
                               default_headers={"anthropic-workspace-id": ws} if ws else None)


def _call_anthropic(prompt: str, max_tokens: int = 16000, what: str = "AI writing") -> str:
    import anthropic

    s = load_settings()
    try:
        ledger.check_ai()
    except ledger.OverBudget as e:
        raise AIError(str(e)) from e
    client = claude_client()
    try:
        resp = client.beta.messages.create(
            model=s.get("anthropic_model") or "claude-opus-5-5",
            max_tokens=max_tokens,
            # brand guide is ~6k tokens and identical every call: cache it (repeat calls read it at ~10% price)
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as e:
        raise AIError("Claude authentication failed — check CLAUDE_API_KEY (or ANTHROPIC_API_KEY) in studio/.env.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Claude rate limit hit — wait a minute and retry.") from e
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e).lower():
            raise NoCredit("The Claude API account has run out of credit. Add credit in the Anthropic console "
                           "(Plans & Billing), or write this one in the Claude terminal.") from e
        raise AIError(f"Claude API error {e.status_code}: {str(e)[:300]}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Couldn't reach the Claude API — check your internet connection.") from e
    if what:
        _log_claude(resp, what)
    if resp.stop_reason == "refusal":
        raise AIError("The model declined this request. Rephrase the brief and try again.")
    if resp.stop_reason == "max_tokens":
        raise AIError("The response was cut off (max tokens). Try a shorter format or fewer slides.")
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _log_claude(resp, what: str) -> None:
    """Record what this call cost, from the token counts the API returned. Never blocks the reply."""
    try:
        u = resp.usage
        inp, out = u.input_tokens or 0, u.output_tokens or 0
        cw, cr = getattr(u, "cache_creation_input_tokens", 0) or 0, getattr(u, "cache_read_input_tokens", 0) or 0
        model = resp.model or ""
        usd = ledger.ai_cost(model, inp, out, cw, cr)
        ledger.record("claude", what, usd or 0.0, kind="ai", cap=False, model=model,
                      tokens={"in": inp, "out": out, "cache_write": cw, "cache_read": cr},
                      **({} if usd is not None else {"note": "price for this model not in the table"}))
    except Exception:
        pass


def _gemini(key: str):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=240_000))


def _call_gemini(prompt: str, max_tokens: int = 8192, what: str = "AI writing") -> str:
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    model = load_settings().get("gemini_model") or os.getenv("GEMINI_MODEL")
    if not key or not model:
        raise AIError("Set GEMINI_API_KEY and GEMINI_MODEL in studio/.env (or add a Claude key).")
    resp, last = None, None
    for attempt in range(2):          # one retry for dropped connections (long drafts)
        try:
            resp = _gemini(key).models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json",
                                                   temperature=0.6, max_output_tokens=max_tokens),
            )
            break
        except Exception as e:
            last = e
            if attempt == 0 and any(x in str(e) for x in ("Connection aborted", "10054", "RemoteDisconnected", "Connection reset")):
                continue
            break
    try:
        if resp is None:
            raise last
    except Exception as e:  # google-genai raises a variety of error types
        t = str(e)
        if "404" in t or "NOT_FOUND" in t:
            raise AIError(f"Gemini model '{model}' isn't available to this key.") from e
        if "401" in t or "403" in t:
            raise AIError("Gemini authentication failed — check GEMINI_API_KEY.") from e
        if "503" in t or "UNAVAILABLE" in t or "overloaded" in t.lower():
            raise AIError("Gemini is overloaded right now (Google 503). Try again in a few minutes, or add a Claude key in Settings.") from e
        if "timed out" in t.lower() or "timeout" in t.lower():
            raise AIError("Gemini didn't answer within 90 seconds. Try again shortly.") from e
        raise AIError(f"Gemini request failed: {t[:300]}") from e
    try:
        um = resp.usage_metadata
        if what:
            ledger.record("gemini", what, 0.0, kind="ai", cap=False, model=model,
                          tokens={"in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0},
                          note="Gemini text price not in the table; see your Google bill")
    except Exception:
        pass
    return resp.text or ""


def complete(prompt: str, max_tokens: int | None = None, what: str = "AI writing", log: bool = True) -> str:
    """`what` names the move on the Costs page. log=False when the caller records its own estimate."""
    p = provider()
    if p == "anthropic":
        try:
            return _call_anthropic(prompt, max_tokens or 16000, what if log else "")
        except NoCredit as e:
            # Claude has no credit: use Gemini for this call if it is set up, and say so on Costs
            if not (os.getenv("GEMINI_API_KEY") and (load_settings().get("gemini_model") or os.getenv("GEMINI_MODEL"))):
                raise
            from datetime import datetime
            LAST_FALLBACK.update(at=datetime.now().isoformat(timespec="seconds"), why=str(e))
            return _call_gemini(prompt, min(max_tokens or 8192, 16000), (what + " (Gemini: Claude out of credit)") if log else "")
    if p == "gemini":
        return _call_gemini(prompt, max_tokens or 8192, what if log else "")
    raise AIError("No AI provider configured. Add ANTHROPIC_API_KEY or GEMINI_API_KEY in Settings.")


def _parse_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise AIError("The model didn't return valid JSON. Try again.")


KEEP = ("id", "slug", "platform", "date", "time", "voice", "status", "approvals", "metrics", "images",
        "published_url", "published_at", "publish_log", "created_at", "_folder", "script_decision")


def _merge(base: dict, gen: dict) -> dict:
    out = dict(base)
    for k, v in gen.items():
        if k in KEEP:
            continue
        out[k] = v
    return out


def _repair(post: dict, issues: list[dict]) -> dict:
    msg = "\n".join(f"- [{i['severity']}] {i['field']}: {i['message']}" for i in issues)
    prompt = (f"This post failed our quality check. Fix every issue and return the full corrected JSON object.\n"
              f"Issues:\n{msg}\n\nPost:\n{json.dumps({k: v for k, v in post.items() if k not in KEEP}, ensure_ascii=False)}")
    return _merge(post, _parse_json(complete(prompt, what="Fix a draft after the quality check")))


def draft_post(base: dict, brief: str = "") -> dict:
    """Fill a slot (platform/date/voice/format/pillar/hook…) with a complete post."""
    v = VOICES.get(base.get("voice") or "company", VOICES["company"])
    ctx = {k: base.get(k) for k in ("platform", "date", "time", "voice", "pillar", "job", "format", "series",
                                    "title", "hook", "festival", "theme", "topic_ref")}
    how = playbook.prompt("linkedin") if base.get("platform") == "linkedin" else ""
    if base.get("format") in ("reel", "video"):
        how += "\n\n" + playbook.prompt("reel")
    prompt = (f"Write this post.\nSlot: {json.dumps(ctx, ensure_ascii=False)}\n"
              f"{playbook.voice_block(base.get('voice') or 'company')}\n\n{how}\n\n"
              f"Content from the marketing lead. When this is given, build the post from it and add no outside facts: "
              f"{brief or '(none: use the hook and pillar)'}\n"
              "Return the complete post JSON (caption, first_comment, hashtags, alt_text, cta, creative.slides, "
              "script if video/reel, poll if poll, notes).")
    post = _merge(base, _parse_json(complete(prompt, what="Write a post script")))
    issues = [i for i in lint_post(post) if i["field"] != "images"]
    if has_errors(issues):
        post = _repair(post, issues)
    post["status"] = "draft"
    return post


def rewrite(post: dict, instruction: str) -> dict:
    prompt = (f"Edit this post. Instruction: {instruction}\nKeep everything else that already works. "
              f"Return the full JSON object.\n{json.dumps({k: v for k, v in post.items() if k not in KEEP}, ensure_ascii=False)}")
    new = _merge(post, _parse_json(complete(prompt, what="Rewrite a post")))
    issues = [i for i in lint_post(new) if i["field"] != "images"]
    if has_errors(issues):
        new = _repair(new, issues)
    return new


def write_script(post: dict, instruction: str = "") -> dict:
    """Write (or rewrite) only the reel/video script from the post. Returns the new `script` dict;
    the caption and everything else stay as they are."""
    v = VOICES.get(post.get("voice") or "company", VOICES["company"])
    ctx = {k: post.get(k) for k in ("platform", "format", "voice", "pillar", "job", "title", "hook", "caption", "cta")}
    have = (post.get("script") or {}).get("scenes")
    prompt = (f"{'Rewrite' if have else 'Write'} the scene-by-scene script for this {post.get('format') or 'reel'}, "
              f"spoken by {v['name']} ({v['role']}).\n{playbook.voice_block(post.get('voice') or 'company')}\n\n"
              f"{playbook.prompt('reel')}\n\n"
              f"Instruction from the marketing lead: {instruction or '(none)'}\n"
              f"Post: {json.dumps(ctx, ensure_ascii=False)}\n"
              + (f"Current script: {json.dumps(post.get('script'), ensure_ascii=False)}\n" if have else "")
              + 'Return ONLY this JSON: {"script": {"duration": "...", "setup": "...", "scenes": '
                '[{"time": "0-3s", "visual": "...", "voiceover": "...", "on_screen": "..."}], "music": "...", "notes": "..."}}')
    data = _parse_json(complete(prompt, what="Write a reel script"))
    sc = data.get("script") if isinstance(data.get("script"), dict) else data
    scenes = [s for s in (sc.get("scenes") or []) if isinstance(s, dict) and (s.get("voiceover") or "").strip()]
    if not scenes:
        raise AIError("The model didn't return any scenes with voiceover. Try again.")
    sc["scenes"] = scenes
    return {k: sc.get(k, "") for k in ("duration", "setup", "scenes", "music", "notes")}


def ask(question: str, context: str) -> str:
    """Free-form Q&A ('Ask the Studio'). Returns plain text."""
    prompt = (f"Answer the marketing lead's question about Galvor's content plan. Be concise and specific. "
              f"Plain text, no JSON.\n\nCurrent plan snapshot:\n{context}\n\nQuestion: {question}")
    p = provider()
    if p == "anthropic":
        return _call_anthropic(prompt, 4000, "Ask the Studio")
    if p == "gemini":
        from google import genai
        from google.genai import types
        r = _gemini(os.getenv("GEMINI_API_KEY")).models.generate_content(
            model=load_settings().get("gemini_model") or os.getenv("GEMINI_MODEL"), contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=2048))
        return r.text or ""
    raise AIError("No AI provider configured.")
