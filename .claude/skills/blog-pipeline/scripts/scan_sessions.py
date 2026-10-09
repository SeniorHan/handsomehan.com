#!/usr/bin/env python3
"""Find blog material in past Claude Code / omp agent sessions.

Sessions are stored as JSONL transcripts, bucketed by the working directory
they ran in:

  ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl          (Claude Code)
  ~/.omp/agent/sessions/<encoded-cwd>/<ts>_<uuid>.jsonl  (omp)

Subagent transcripts (.../subagents/*.jsonl and omp phase-slice subdirs) are
NOT main conversations, so they are excluded — blog material lives in the
human<->AI dialogue.

Subcommands
-----------
  list   --top N            rank main sessions by size, print the top N
  theme  --keywords a,b,c   score sessions by keyword hits in the USER's own
                            prompts (more reliable than full-text, which is
                            polluted by deploy logs / quoted output)
  digest --path P [...]     write a compact digest (user prompts + first
                            assistant reply + metadata) — cheap to summarize
  story  --path P [...]     write a rich transcript (user + assistant prose +
                            tool calls + truncated results) — enough to draft
                            a blog from, without choking on a 20MB file

Digests/stories are written to --out (default /tmp/blogscan). Hand the small
digest files to summarizer subagents; hand the story file to the writer.

stdlib only. Safe to run repeatedly.
"""
from __future__ import annotations
import argparse, glob, json, os, sys

CLAUDE_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
OMP_GLOB = os.path.expanduser("~/.omp/agent/sessions/*/*.jsonl")


def collect():
    """Return [(tool, size_bytes, path)] for every MAIN session transcript."""
    rows = []
    for p in glob.glob(CLAUDE_GLOB):
        if "/subagents/" in p:
            continue
        rows.append(("claude", os.path.getsize(p), p))
    for p in glob.glob(OMP_GLOB):  # omp sub-slices live in subdirs, already excluded
        rows.append(("omp", os.path.getsize(p), p))
    return rows


def _text_blocks(content):
    """Pull plain text out of a message `content` (str or list of blocks)."""
    if isinstance(content, str):
        return [content]
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                out.append(b["text"])
    return out


def _is_noise(s: str) -> bool:
    s = s.strip()
    return (not s) or s.startswith((
        "<local-command", "<command-", "Caveat:", "<system-",
        "[Request interrupted", "<bash-", "This session is being continued",
    ))


def parse(path):
    """Walk a transcript once, returning the bits everything else needs."""
    user_prompts, ts0, ts1, cwd, branch = [], None, None, None, None
    assistant_first = None
    n_user = n_asst = 0
    with open(path, errors="ignore") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("isSidechain"):
                continue
            if o.get("timestamp"):
                ts0 = ts0 or o["timestamp"]
                ts1 = o["timestamp"]
            cwd = cwd or o.get("cwd")
            branch = branch or o.get("gitBranch")
            m = o.get("message")
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role == "user" and not o.get("isMeta"):
                for s in _text_blocks(m.get("content")):
                    if not _is_noise(s):
                        n_user += 1
                        user_prompts.append(s.strip())
            elif role == "assistant":
                if assistant_first is None:
                    for s in _text_blocks(m.get("content")):
                        if s.strip():
                            assistant_first = s.strip()[:500]
                            break
                n_asst += 1
    return dict(user_prompts=user_prompts, assistant_first=assistant_first,
                ts0=ts0, ts1=ts1, cwd=cwd, branch=branch,
                n_user=n_user, n_asst=n_asst)


def _proj(path):
    return (path.split("/")[-2]
            .replace("-home-hankangshuai-workspace-", "")
            .replace("-home-hankangshuai", "~"))


def write_digest(path, out_dir, label=None):
    info = parse(path)
    caps = [(s[:800] + ("…" if len(s) > 800 else "")) for s in info["user_prompts"][:40]]
    lines = [
        f"# Session digest{f' ({label})' if label else ''}",
        f"path: {path}", f"cwd: {info['cwd']}", f"gitBranch: {info['branch']}",
        f"time: {info['ts0']} → {info['ts1']}",
        f"size: {os.path.getsize(path)/1e6:.2f}MB",
        f"user_prompt_count: {info['n_user']}  assistant_msg_count: {info['n_asst']}",
        "", "## First assistant reply (head)", info["assistant_first"] or "(none)",
        "", "## User prompts (chronological, truncated)",
    ]
    for i, s in enumerate(caps, 1):
        lines.append(f"\n[{i}] {s}")
    extra = len(info["user_prompts"]) - 40
    if extra > 0:
        lines.append(f"\n… (+{extra} more user prompts omitted)")
    os.makedirs(out_dir, exist_ok=True)
    name = label or os.path.basename(path).split(".")[0]
    dest = os.path.join(out_dir, f"digest_{name}.md")
    with open(dest, "w") as f:
        f.write("\n".join(lines))
    return dest


def _tool_key(inp):
    if not isinstance(inp, dict):
        return ""
    for k in ("command", "file_path", "path", "pattern", "url", "description", "query", "prompt"):
        if inp.get(k):
            return f"{k}={str(inp[k])[:220]}"
    return str(inp)[:160]


def write_story(path, out_dir, label=None, cap=95000):
    buf = []
    with open(path, errors="ignore") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("isSidechain"):
                continue
            m = o.get("message")
            if not isinstance(m, dict):
                continue
            role, c = m.get("role"), m.get("content")
            if role == "user" and not o.get("isMeta"):
                if isinstance(c, str):
                    s = c.strip()
                    if s and not _is_noise(s):
                        buf.append(f"\n\n### 🧑 USER\n{s[:1800]}")
                elif isinstance(c, list):
                    for b in c:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and b.get("text", "").strip():
                            buf.append(f"\n\n### 🧑 USER\n{b['text'].strip()[:1800]}")
                        elif b.get("type") == "tool_result":
                            rc = b.get("content")
                            if isinstance(rc, list):
                                rc = " ".join(x.get("text", "") for x in rc if isinstance(x, dict))
                            rc = str(rc)[:500]
                            if rc.strip():
                                buf.append(f"    ↳ result: {rc}")
            elif role == "assistant" and isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        buf.append(f"\n🤖 {b['text'].strip()[:1400]}")
                    elif b.get("type") == "tool_use":
                        buf.append(f"    → [{b.get('name')}] {_tool_key(b.get('input'))}")
            if len("\n".join(buf)) > cap:
                buf.append("\n\n…[转写已截断，后续略]")
                break
    os.makedirs(out_dir, exist_ok=True)
    name = label or os.path.basename(path).split(".")[0]
    dest = os.path.join(out_dir, f"story_{name}.md")
    with open(dest, "w") as f:
        f.write("\n".join(buf))
    return dest


def cmd_list(args):
    rows = sorted(collect(), key=lambda r: -r[1])[args.skip:args.skip + args.top]
    for i, (tool, sz, p) in enumerate(rows, args.skip + 1):
        info = parse(p) if args.detail else None
        extra = f"  {info['n_user']}U/{info['n_asst']}A" if info else ""
        print(f"{i:3}. [{tool}] {sz/1e6:6.2f}MB  {_proj(p):16}{extra}  {p}")


def cmd_theme(args):
    kws = [k.strip().lower() for k in args.keywords.split(",") if k.strip()]
    scored = []
    for tool, sz, p in collect():
        info = parse(p)
        ut = "\n".join(info["user_prompts"]).lower()
        if not ut:
            continue
        score = sum(ut.count(k) for k in kws)
        if score:
            fp = info["user_prompts"][0][:80] if info["user_prompts"] else "(?)"
            scored.append((score, sz, p, tool, fp))
    scored.sort(key=lambda r: -r[0])
    for score, sz, p, tool, fp in scored[:args.top]:
        print(f"{score:4} hits  {sz/1e6:6.2f}MB [{tool}] {_proj(p):16} | {fp}")
        print(f"            {p}")


def cmd_digest(args):
    for p in args.path:
        print(write_digest(p, args.out, args.label))


def cmd_story(args):
    for p in args.path:
        print(write_story(p, args.out, args.label, cap=args.cap))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="rank main sessions by size")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--skip", type=int, default=0, help="skip the first N (paginate)")
    p.add_argument("--detail", action="store_true", help="also count user/assistant turns")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("theme", help="rank sessions by keyword hits in user prompts")
    p.add_argument("--keywords", required=True, help="comma-separated, e.g. uart,gpio,刷机")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_theme)

    p = sub.add_parser("digest", help="write compact digest(s) for summarizing")
    p.add_argument("--path", nargs="+", required=True)
    p.add_argument("--out", default="/tmp/blogscan")
    p.add_argument("--label", default=None, help="name for the output file")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("story", help="write rich transcript(s) for drafting")
    p.add_argument("--path", nargs="+", required=True)
    p.add_argument("--out", default="/tmp/blogscan")
    p.add_argument("--label", default=None)
    p.add_argument("--cap", type=int, default=95000, help="max chars per source")
    p.set_defaults(func=cmd_story)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
