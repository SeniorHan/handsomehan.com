#!/usr/bin/env python3
"""Turn a finished Markdown draft into a published Astro blog post.

The blog is an Astro content collection (src/content.config.ts):
  - files live in src/content/blog/<YYYY-MM-DD>-<slug>.md
  - required frontmatter: title, date, description, tags (draft optional)
  - the Post layout renders the title as <h1>, so the body must NOT repeat it
    as a leading "# ..." — this script strips that line for you.

What it does, in order:
  1. read the draft, strip a leading "# Title" (+ blank lines)
  2. prepend YAML frontmatter (quotes safely escaped)
  3. write to src/content/blog/<date>-<slug>.md
  4. (--build)  build with the repo's LOCAL astro (never npx — npx pulls a
                stray astro that can't find the local config); npm install first
                if node_modules is missing
  5. (--commit) commit ONLY the new post. package-lock.json churn from a fresh
                npm install is restored so it doesn't pollute the commit, and
                git identity is borrowed from the last commit if unset.
  6. (--push)   push to origin (Cloudflare Pages auto-deploys on push)

stdlib only.
"""
from __future__ import annotations
import argparse, os, subprocess, sys


def sh(cmd, cwd, check=True, capture=False):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str),
                       text=True, capture_output=capture)
    if check and r.returncode != 0:
        out = (r.stdout or "") + (r.stderr or "")
        sys.exit(f"command failed ({r.returncode}): {cmd}\n{out}")
    return r


def yaml_q(s: str) -> str:
    """Single-quoted YAML scalar (double internal single quotes)."""
    return "'" + s.replace("'", "''") + "'"


def strip_h1(text: str) -> str:
    lines = text.split("\n")
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).rstrip() + "\n"


def auto_description(body: str) -> str:
    """Best-effort: first blockquote line, else first paragraph, trimmed."""
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith(">"):
            return s.lstrip("> ").strip()[:160]
    for line in body.split("\n"):
        s = line.strip()
        if s and not s.startswith(("#", "```", "|", "-", "*")):
            return s[:160]
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draft", required=True, help="path to the finished .md draft")
    ap.add_argument("--title", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--slug", required=True, help="kebab-case english slug")
    ap.add_argument("--tags", default="", help="comma-separated")
    ap.add_argument("--description", default=None, help="defaults to first blockquote/para")
    ap.add_argument("--draft-flag", action="store_true", help="set draft: true in frontmatter")
    ap.add_argument("--repo", default=".", help="repo root (default cwd)")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    body = strip_h1(open(args.draft).read())
    desc = args.description or auto_description(body)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    fm = ["---",
          f"title: {yaml_q(args.title)}",
          f"date: {args.date}",
          f"description: {yaml_q(desc)}",
          "tags: [" + ", ".join(yaml_q(t) for t in tags) + "]"]
    if args.draft_flag:
        fm.append("draft: true")
    fm.append("---\n\n")

    rel = os.path.join("src/content/blog", f"{args.date}-{args.slug}.md")
    dest = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as f:
        f.write("\n".join(fm) + body)
    print(f"wrote {rel}")
    if not desc:
        print("  ⚠ description empty — pass --description for a proper meta/SEO blurb")

    if args.build:
        if not os.path.exists(os.path.join(repo, "node_modules/.bin/astro")):
            print("node_modules missing → npm install")
            sh("npm install", repo)
        print("building with local astro …")
        sh("node_modules/.bin/astro build", repo)
        print("  ✓ build passed")

    if args.commit:
        # drop unrelated package-lock.json churn from npm install
        sh("git checkout -- package-lock.json", repo, check=False)
        sh(["git", "add", rel], repo)
        # borrow identity from last commit if not configured
        if sh("git config user.email", repo, check=False, capture=True).returncode != 0:
            last = sh("git log -1 --format=%an%n%ae", repo, capture=True).stdout.splitlines()
            if len(last) >= 2:
                sh(["git", "config", "user.name", last[0]], repo)
                sh(["git", "config", "user.email", last[1]], repo)
        msg = f"blog: {args.title}"
        sh(["git", "commit", "-m", msg], repo)
        print(f"  ✓ committed: {msg}")
        if args.push:
            sh("git push origin HEAD", repo)
            print("  ✓ pushed (Cloudflare Pages will rebuild)")


if __name__ == "__main__":
    main()
