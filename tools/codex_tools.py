"""
Codex Agent — Production Tool Implementations
Matching Rust codex-rs/core/src/tools/handlers/ semantics.
Each tool: validation, multi-step workflows, structured output, error handling.

This is the ORIGINAL codex_tools suite, moved into the shared tools/ folder
so the codex_growth / codex_RAG / codex_normal agents all share one tool set.
"""

import os, re, subprocess, json, time, threading, uuid, base64, difflib, tempfile, shutil, struct, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

from tools.config import Config

logger = logging.getLogger("tools.codex")

# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

_WORKSPACE: Optional[Path] = None

def workspace() -> Path:
    global _WORKSPACE
    if _WORKSPACE is None:
        _WORKSPACE = Config.WORKSPACE_ROOT
    return _WORKSPACE

def resolve_path(path: str) -> Path:
    p = Path(path)
    return p.resolve() if p.is_absolute() else (workspace() / p).resolve()

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024: return f"{size_bytes:,}B"
    elif size_bytes < 1024**2: return f"{size_bytes/1024:.1f}KB"
    elif size_bytes < 1024**3: return f"{size_bytes/1024**2:.1f}MB"
    return f"{size_bytes/1024**3:.1f}GB"

def format_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

# ══════════════════════════════════════════════════════════════════════════════
# Tool Definitions (19 tools)
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    # shell_command
    {"type":"function","function":{"name":"shell_command","description":"Execute a shell command. Returns exit code, duration, stdout, stderr. 30s timeout. Blocks destructive commands. Max 8000 char output.","parameters":{"type":"object","properties":{"command":{"type":"string","description":"Shell command"},"cwd":{"type":"string","description":"Working directory, default: workspace root"},"env":{"type":"object","description":"Extra env vars"}},"required":["command"]}}},
    # read_file
    {"type":"function","function":{"name":"read_file","description":"Read a file with encoding detection, line numbers for partial reads, metadata header. 8000 char limit.","parameters":{"type":"object","properties":{"path":{"type":"string"},"start_line":{"type":"integer","description":"1-based start line"},"end_line":{"type":"integer","description":"1-based end line, inclusive"}},"required":["path"]}}},
    # write_file
    {"type":"function","function":{"name":"write_file","description":"Write a file. Creates .bak backup. Returns unified diff. Auto-creates parent directories.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    # list_directory
    {"type":"function","function":{"name":"list_directory","description":"List directory with sizes, timestamps, type icons. Dirs first, then files.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"Default: workspace root"},"show_hidden":{"type":"boolean","description":"Show dotfiles, default: false"}},"required":[]}}},
    # search_files
    {"type":"function","function":{"name":"search_files","description":"Find files by glob. Up to 100 results, newest first, with sizes.","parameters":{"type":"object","properties":{"pattern":{"type":"string","description":"Glob: **/*.py"}},"required":["pattern"]}}},
    # grep_search
    {"type":"function","function":{"name":"grep_search","description":"Regex search with file:line:col refs, per-file match counts, optional context lines. Case-insensitive.","parameters":{"type":"object","properties":{"query":{"type":"string","description":"Regex, case-insensitive"},"include_pattern":{"type":"string","description":"File filter glob"},"context_lines":{"type":"integer","description":"Lines of context around matches"},"max_matches":{"type":"integer","description":"Max matches, default: 30"}},"required":["query"]}}},
    # apply_patch
    {"type":"function","function":{"name":"apply_patch","description":"Apply a unified diff: (1) read target, (2) backup, (3) parse hunks, (4) apply via difflib or shell fallback, (5) validate.","parameters":{"type":"object","properties":{"target_file":{"type":"string"},"patch_content":{"type":"string","description":"Unified diff"},"description":{"type":"string"}},"required":["target_file","patch_content"]}}},
    # view_image
    {"type":"function","function":{"name":"view_image","description":"Read image, detect dimensions (PNG/JPEG), encode as base64 data URL. Returns metadata.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    # current_time
    {"type":"function","function":{"name":"current_time","description":"Current time in local, UTC, ISO 8601, Unix, weekday formats.","parameters":{"type":"object","properties":{},"required":[]}}},
    # plan
    {"type":"function","function":{"name":"plan","description":"Task plan with step IDs, statuses, optional dependencies, progress tracking.","parameters":{"type":"object","properties":{"title":{"type":"string"},"steps":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"description":{"type":"string"},"status":{"type":"string","enum":["pending","in_progress","completed","blocked"]},"depends_on":{"type":"array","items":{"type":"string"}}},"required":["description"]}}},"required":["title","steps"]}}},
    # request_user_input
    {"type":"function","function":{"name":"request_user_input","description":"Ask user a question. Returns request ID. User responds with /answer <id> <response>.","parameters":{"type":"object","properties":{"question":{"type":"string"},"choices":{"type":"array","items":{"type":"string"}},"default":{"type":"string"}},"required":["question"]}}},
    # spawn_agent
    {"type":"function","function":{"name":"spawn_agent","description":"Create a sub-agent running in parallel. Returns agent_id.","parameters":{"type":"object","properties":{"name":{"type":"string"},"task":{"type":"string"},"context":{"type":"string","description":"Additional context"}},"required":["name","task"]}}},
    # wait_agent
    {"type":"function","function":{"name":"wait_agent","description":"Wait for sub-agent and return its result. Timeout 1-600 seconds.","parameters":{"type":"object","properties":{"agent_id":{"type":"string"},"timeout_seconds":{"type":"integer","description":"Default: 120"}},"required":["agent_id"]}}},
    # list_agents
    {"type":"function","function":{"name":"list_agents","description":"List all sub-agents with status, runtime, task preview.","parameters":{"type":"object","properties":{},"required":[]}}},
    # cancel_agent
    {"type":"function","function":{"name":"cancel_agent","description":"Cancel a running sub-agent.","parameters":{"type":"object","properties":{"agent_id":{"type":"string"}},"required":["agent_id"]}}},
    # send_notification
    {"type":"function","function":{"name":"send_notification","description":"Push notification via PushOver. Supports priority, sound, URL. Requires .env config.","parameters":{"type":"object","properties":{"title":{"type":"string"},"message":{"type":"string"},"priority":{"type":"integer","description":"-2 quiet to 2 emergency"},"url":{"type":"string"},"sound":{"type":"string"}},"required":["title","message"]}}},
    # memory_read
    {"type":"function","function":{"name":"memory_read","description":"Read from persistent key-value memory. '*' lists all keys with metadata. Auto-cleans expired entries.","parameters":{"type":"object","properties":{"key":{"type":"string","description":"Key or '*' for summary"},"default_value":{"type":"string","description":"Returned if key not found"}},"required":["key"]}}},
    # memory_write
    {"type":"function","function":{"name":"memory_write","description":"Write to persistent JSON memory. Optional TTL, tags, auto-timestamps.","parameters":{"type":"object","properties":{"key":{"type":"string"},"value":{"type":"string"},"ttl_seconds":{"type":"integer","description":"0=permanent"},"tags":{"type":"array","items":{"type":"string"}}},"required":["key","value"]}}},
    # web_search — local HTTP fetch (replaces OpenAI's hosted search API)
    {"type":"function","function":{"name":"web_search","description":"Search the web via DuckDuckGo or fetch a URL. Returns page title, content, and URLs. Use for looking up documentation, APIs, or current information that isn't in your training data.","parameters":{"type":"object","properties":{"query":{"type":"string","description":"Search query OR full URL to fetch"},"max_results":{"type":"integer","description":"Max results, default: 3"},"search_mode":{"type":"string","description":"'auto' (default): detect URL vs search. 'url': force URL fetch. 'search': force web search."}},"required":["query"]}}},
]


# ══════════════════════════════════════════════════════════════════════════════
# Tool Implementations
# ══════════════════════════════════════════════════════════════════════════════

DESTRUCTIVE = [
    r'\brm\s+-rf\s+/', r'\bgit\s+reset\s+--hard', r'\bgit\s+checkout\s+--',
    r'\bdd\s+if=', r'>\s*/dev/', r'\bmkfs\.', r'\bchmod\s+777\s+/',
]

def tool_shell_command(command: str, cwd: str = "", env: dict = None) -> str:
    """Execute a shell command. On Windows, auto-tries PowerShell for curl/invoke commands.
    If a conda environment is active, commands are prefixed with 'conda run -n <env>'."""
    try:
        wd = str(resolve_path(cwd)) if cwd else str(workspace())
        if not Path(wd).is_dir(): return f"[ERROR] Directory not found: {wd}"
        for p in DESTRUCTIVE:
            if re.search(p, command): return f"[ERROR] Destructive command blocked: {p}"
        proc_env = {**os.environ, **{str(k):str(v) for k,v in (env or {}).items()}}

        # ── Conda environment prefix ─────────────────────────────────
        conda_prefix = Config.get_conda_activate_prefix()
        if conda_prefix and not command.strip().lower().startswith(('conda ', 'pip ')):
            command = conda_prefix + command

        t0 = time.perf_counter()
        r = subprocess.run(command, shell=True, capture_output=True, timeout=30, cwd=wd, env=proc_env)
        elapsed = time.perf_counter() - t0

        # On Windows, if the command failed and looks like it needs PowerShell, retry
        if os.name == 'nt' and r.returncode != 0:
            cmd_lower = command.strip().lower()
            ps_commands = ('curl ', 'wget ', 'invoke-', 'get-content ', 'select-string ',
                          'where-object ', 'foreach-object ', 'get-childitem ', 'get-item ')
            if any(cmd_lower.startswith(c) for c in ps_commands):
                ps_cmd = f'powershell -NoProfile -Command "{command}"'
                r = subprocess.run(ps_cmd, shell=True, capture_output=True, timeout=30, cwd=wd, env=proc_env)

        out = r.stdout.decode('utf-8', errors='replace').strip() if r.stdout else ''
        err = r.stderr.decode('utf-8', errors='replace').strip() if r.stderr else ''
        parts = [f"Exit: {r.returncode}  |  {elapsed:.2f}s"]
        if out: parts.append(f"stdout ({len(out)}):\n{out[:8000]}" + (f"\n...[+{len(out)-8000} chars]" if len(out)>8000 else ""))
        if err: parts.append(f"stderr ({len(err)}):\n{err[:2000]}")
        if not out and not err: parts.append("(no output)")
        return "\n".join(parts)
    except subprocess.TimeoutExpired: return "[ERROR] Timed out after 30s"
    except Exception as e: return f"[ERROR] {e}"

def tool_read_file(path: str, start_line: int = None, end_line: int = None) -> str:
    try:
        p = resolve_path(path)
        if not p.is_file(): return f"[ERROR] Not found: {p}"
        if p.stat().st_size > 10*1024**2: return f"[ERROR] File too large ({format_size(p.stat().st_size)})"
        try: content = p.read_text(encoding="utf-8"); enc = "utf-8"
        except: content = p.read_text(encoding="utf-8", errors="replace"); enc = "utf-8(replaced)"
        lines = content.splitlines()
        sl, el = max(1,(start_line or 1)), min(len(lines),(end_line or len(lines)))
        sel = lines[sl-1:el]
        if start_line is not None or end_line is not None:
            w = len(str(el)); output = "\n".join(f"{i:>{w}} | {l}" for i,l in enumerate(sel,sl))
        else: output = "\n".join(sel)
        rel = p.relative_to(workspace()) if workspace() in p.parents or p == workspace() else p
        meta = f"File: {rel}\n{len(content):,} chars, {len(lines)} lines"
        if sl>1 or el<len(lines): meta += f" (lines {sl}-{el})"
        meta += f"\nEnc: {enc}\n{'-'*50}\n"
        result = meta + output
        return result[:8000] + (f"\n...[truncated {len(result)-8000}]" if len(result)>8000 else "")
    except Exception as e: return f"[ERROR] {e}"

def tool_write_file(path: str, content: str) -> str:
    try:
        p = resolve_path(path); p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        orig = p.read_text(encoding="utf-8", errors="replace") if existed else ""
        if existed: shutil.copy2(p, p.with_suffix(p.suffix+".bak"))
        p.write_text(content, encoding="utf-8")
        parts = [f"[OK] Wrote {len(content)} chars to {p.relative_to(workspace())}"]
        if existed and orig:
            diff = list(difflib.unified_diff(orig.splitlines(True), content.splitlines(True),
                fromfile=str(p.relative_to(workspace())), tofile=str(p.relative_to(workspace())), lineterm=''))
            if diff:
                d = '\n'.join(diff)
                parts.append(f"Lines: {len(orig.splitlines())}→{len(content.splitlines())} | Backup: {p.with_suffix(p.suffix+'.bak').name}")
                parts.append(f"Diff:\n{d[:2000]}" + (f"\n...[truncated {len(d)-2000}]" if len(d)>2000 else ""))
            else: parts.append("(no changes)")
        return "\n".join(parts)
    except Exception as e: return f"[ERROR] {e}"

def tool_list_directory(path: str = "", show_hidden: bool = False) -> str:
    try:
        p = resolve_path(path) if path else workspace()
        if not p.is_dir(): return f"[ERROR] Not a directory: {p}"
        entries, dc, fc, ts = [], 0, 0, 0
        for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if not show_hidden and e.name.startswith('.') and e.name != '.env': continue
            try:
                s = e.stat(); mt = format_timestamp(s.st_mtime)
                if e.is_dir(): dc+=1; entries.append(f"  📁 {e.name:<40} {mt}")
                else: fc+=1; ts+=s.st_size; entries.append(f"  📄 {e.name:<40} {format_size(s.st_size):>8}  {mt}")
            except: entries.append(f"  ❓ {e.name:<40} [denied]")
        hdr = f"{p.relative_to(workspace()) if p!=workspace() else '(root)'}\n{dc} dirs, {fc} files, {format_size(ts)}\n{'-'*60}"
        return hdr + "\n" + "\n".join(entries) if entries else hdr + "\n(empty)"
    except Exception as e: return f"[ERROR] {e}"

def tool_search_files(pattern: str) -> str:
    try:
        m = [(fp, fp.stat().st_mtime, fp.stat().st_size) for fp in workspace().glob(pattern) if fp.is_file()]
        m.sort(key=lambda x:-x[1])
        lines = [f"Pattern: '{pattern}'  |  {len(m)} files\n{'-'*60}"]
        for fp, mt, sz in m[:100]:
            lines.append(f"  {fp.relative_to(workspace())}  ({format_size(sz)}, {format_timestamp(mt) if mt else '?'})")
        if len(m)>100: lines.append(f"  ... +{len(m)-100} more")
        return "\n".join(lines) if m else f"No files matching '{pattern}'"
    except Exception as e: return f"[ERROR] {e}"

def tool_grep_search(query: str, include_pattern: str = "", context_lines: int = 0, max_matches: int = 30) -> str:
    try:
        pat = re.compile(query, re.IGNORECASE|re.MULTILINE); skip={".pyc",".exe",".dll",".pdb",".obj",".bin",".so",".dylib",".zip",".tar",".gz"}
        results, fm, scanned = [], {}, 0
        for fp in workspace().glob(include_pattern or "**/*"):
            if not fp.is_file() or fp.suffix.lower() in skip: continue; scanned+=1
            try:
                ls = fp.read_text(encoding="utf-8",errors="replace").splitlines()
                for i,line in enumerate(ls):
                    m = pat.search(line)
                    if m:
                        rel = fp.relative_to(workspace()); col = m.start()+1; fm[rel]=fm.get(rel,0)+1
                        if context_lines>0:
                            a,b = max(0,i-context_lines), min(len(ls),i+context_lines+1)
                            ctx = "\n".join(f"     {'>' if j==i else ' '} {j+1:>4}| {ls[j][:120]}" for j in range(a,b))
                            results.append(f"  {rel}:{i+1}:{col}\n{ctx}")
                        else: results.append(f"  {rel}:{i+1}:{col}: {line.strip()[:120]}")
                        if len(results)>=max_matches: break
                if len(results)>=max_matches: break
            except: continue
        summ = f"Query: '{query}'  |  Scanned: {scanned} files"
        if fm: summ += "  |  " + ", ".join(f"{k}:{v}" for k,v in sorted(fm.items(),key=lambda x:-x[1])[:8])
        result = summ + f"\n{'-'*60}\n" + ("\n".join(results) if results else "(no matches)")
        if len(results)>=max_matches: result += f"\n...[stopped at {max_matches}]"
        return result
    except re.error as e: return f"[ERROR] Invalid regex: {e}"
    except Exception as e: return f"[ERROR] {e}"

def tool_apply_patch(target_file: str, patch_content: str, description: str = "") -> str:
    try:
        p = resolve_path(target_file); steps = []
        orig = p.read_text(encoding="utf-8",errors="replace") if p.exists() else ""
        steps.append(f"[1/5] Read target: {p.relative_to(workspace()) if p.exists() else '(new)'} ({len(orig)} chars)")
        if p.exists(): bak = p.with_suffix(p.suffix+".bak"); shutil.copy2(p, bak); steps.append(f"[2/5] Backup: {bak.name}")
        else: steps.append("[2/5] No backup (new file)")
        hunks = len([l for l in patch_content.splitlines() if l.startswith('@@')])
        adds = len([l for l in patch_content.splitlines() if l.startswith('+') and not l.startswith('+++')])
        dels = len([l for l in patch_content.splitlines() if l.startswith('-') and not l.startswith('---')])
        steps.append(f"[3/5] Parsed: {hunks} hunks, +{adds}/-{dels}")
        try:
            new = "".join(difflib.restore(patch_content.splitlines(True), 2)); steps.append("[4/5] Applied via difflib")
        except:
            with tempfile.NamedTemporaryFile(mode='w',suffix='.patch',delete=False) as f: f.write(patch_content); tp=f.name
            subprocess.run(f'patch --ignore-whitespace "{p}" "{tp}"',shell=True,capture_output=True,text=True,timeout=10,cwd=str(p.parent))
            os.unlink(tp); new = p.read_text(encoding="utf-8",errors="replace") if p.exists() else ""; steps.append("[4/5] Applied via shell patch")
        p.parent.mkdir(parents=True,exist_ok=True); p.write_text(new,encoding="utf-8")
        steps.append(f"[5/5] {'✓ Changed' if orig!=new else '⚠ Unchanged'}: {len(orig)}→{len(new)} chars")
        return "\n".join(steps)
    except Exception as e: return f"[ERROR] {e}"

def tool_view_image(path: str) -> str:
    try:
        p=resolve_path(path)
        if not p.is_file(): return f"[ERROR] Not found: {p}"
        mime={".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".gif":"image/gif",".webp":"image/webp",".bmp":"image/bmp"}.get(p.suffix.lower(),"application/octet-stream")
        data=base64.b64encode(p.read_bytes()).decode(); size=p.stat().st_size
        dim=""
        try:
            if p.suffix.lower()=='.png':
                with open(p,'rb') as f: f.read(16); w,h=struct.unpack('>II',f.read(8)); dim=f", {w}x{h}px"
            elif p.suffix.lower() in ('.jpg','.jpeg'):
                with open(p,'rb') as f:
                    f.read(2)
                    while True:
                        mk,=struct.unpack('>H',f.read(2))
                        if mk<0xFFC0: continue
                        ln,=struct.unpack('>H',f.read(2))
                        if mk in(0xFFC0,0xFFC2): f.read(1); h,w=struct.unpack('>HH',f.read(4)); dim=f", {w}x{h}px"; break
                        f.read(ln-2)
        except: pass
        return f"{p.relative_to(workspace())}\nType: {mime}{dim}\nSize: {format_size(size)}\ndata:{mime};base64,{data[:40]}... [{len(data)} chars]"
    except Exception as e: return f"[ERROR] {e}"

def tool_current_time() -> str:
    n=datetime.now(timezone.utc); l=datetime.now(); o=l.utcoffset() or timedelta(0)
    h=int(o.total_seconds()//3600); m=abs(int(o.total_seconds()%3600//60))
    os_=f"UTC{'+' if o.total_seconds()>=0 else ''}{h:+d}:{m:02d}"
    return f"Local:    {l.strftime('%Y-%m-%d %H:%M:%S')} {os_}\nUTC:      {n.strftime('%Y-%m-%d %H:%M:%S')}\nISO:      {l.isoformat()}\nUnix:     {int(l.timestamp())}\nWeekday:  {l.strftime('%A')} (W{l.strftime('%W')})"

# ── Plan, User Input, Multi-Agent, Memory ─────────────────────────────────

_PLANS, _PENDING, _AGENTS = {}, {}, {}
_ALOCK = threading.Lock()
_MF: Optional[Path] = None
_MLOCK = threading.Lock()

def tool_plan(title: str, steps: list) -> str:
    for i,s in enumerate(steps):
        if "id" not in s: s["id"]=f"step_{i+1}"
        if "status" not in s: s["status"]="pending"
    _PLANS[title]=steps
    ic={"pending":"⬜","in_progress":"🔄","completed":"✅","blocked":"🚫"}
    lines=[f"Plan: {title} ({len(steps)} steps)"]
    done=sum(1 for s in steps if s["status"]=="completed")
    for s in steps:
        l=f"  {ic.get(s['status'],'⬜')} {s['description']} [{s['status']}]"
        if s.get("depends_on"): l+=f"\n       depends: {', '.join(s['depends_on'])}"
        lines.append(l)
    if steps: lines.append(f"\nProgress: {done}/{len(steps)} ({done*100//len(steps)}%)")
    return "\n".join(lines)

def tool_request_user_input(question: str, choices: list = None, default: str = "") -> str:
    qid=str(uuid.uuid4())[:8]
    _PENDING[qid]={"question":question,"choices":choices,"default":default,"answer":None,"at":datetime.now(timezone.utc).isoformat()}
    ls=[f"❓ [{qid}] {question}"]
    if choices:
        for i,c in enumerate(choices,1): ls.append(f"  {i}. {c}")
    if default: ls.append(f"  Default: {default}")
    ls.append(f"\nReply: /answer {qid} <your response>")
    return "\n".join(ls)

def tool_spawn_agent(name: str, task: str, context: str = "") -> str:
    try:
        from tools.engine import AgentEngine
        from LLMs.deepseek import MockProvider
        e = AgentEngine(graph=None, encoder=None, llm=MockProvider())
    except Exception as exc:  # noqa: BLE001
        return f"[ERROR] sub-agent engine unavailable: {exc}"
    aid=str(uuid.uuid4())[:8]; t0=time.time()
    with _ALOCK: _AGENTS[aid]={"name":name,"task":task,"status":"running","engine":e,"result":None,"spawned":t0}
    def _r():
        try:
            p=f"Task: {task}"+(f"\n\nContext: {context}" if context else "")
            r=e.run_with_trace(p)
            with _ALOCK: _AGENTS[aid].update({"result":r[0],"status":"completed","done":time.time()})
        except Exception as ex:
            with _ALOCK: _AGENTS[aid].update({"result":str(ex),"status":"failed","done":time.time()})
    t=threading.Thread(target=_r,daemon=True,name=f"codex-sub-{aid}"); t.start()
    with _ALOCK: _AGENTS[aid]["thread"]=t
    return f"Agent spawned [{aid}] '{name}'\nTask: {task[:120]}"

def tool_wait_agent(agent_id: str, timeout_seconds: int = 120) -> str:
    to=min(max(timeout_seconds,1),600)
    if agent_id not in _AGENTS: return f"[ERROR] Not found: {agent_id}"
    a=_AGENTS[agent_id]
    if a["status"]=="running":
        dl=time.time()+to
        while time.time()<dl and a["status"]=="running": time.sleep(2)
        if a["status"]=="running": return f"[WARN] Timed out after {to}s"
    el=a.get("done",time.time())-a.get("spawned",time.time())
    return f"[{agent_id}] '{a['name']}'\nStatus: {a['status']}  |  {el:.1f}s\n{'-'*40}\n{(a.get('result') or '')[:1000]}"

def tool_list_agents() -> str:
    if not _AGENTS: return "No sub-agents."
    ic={"running":"🔄","completed":"✅","failed":"❌","cancelled":"🚫"}
    ls=["Sub-agents:"]
    for aid,a in sorted(_AGENTS.items(),key=lambda x:-x[1].get("spawned",0)):
        el=f" [{time.time()-a['spawned']:.0f}s]" if a["status"]=="running" else f" [{a.get('done',0)-a['spawned']:.1f}s]"
        ls.append(f"  {ic.get(a['status'],'?')} [{aid}] {a['name']} — {a['status']}{el}")
    return "\n".join(ls)

def tool_cancel_agent(agent_id: str) -> str:
    if agent_id not in _AGENTS: return f"[ERROR] Not found: {agent_id}"
    if _AGENTS[agent_id]["status"] in ("completed","failed","cancelled"): return f"[WARN] Already {_AGENTS[agent_id]['status']}"
    _AGENTS[agent_id]["status"]="cancelled"; _AGENTS[agent_id]["done"]=time.time()
    return f"[OK] Cancelled {agent_id}"

def tool_send_notification(title: str, message: str, priority: int = 0, url: str = "", sound: str = "") -> str:
    try:
        if not (Config.PUSHOVER_USER and Config.PUSHOVER_TOKEN): return "[WARN] PushOver not configured"
        import httpx
        d={"token":Config.PUSHOVER_TOKEN,"user":Config.PUSHOVER_USER,"title":title[:250],"message":message[:1024],"priority":max(-2,min(2,priority))}
        if url: d["url"]=url[:512]
        if sound: d["sound"]=sound
        r=httpx.post("https://api.pushover.net/1/messages.json",data=d,timeout=10)
        return f"[OK] Sent (request: {r.json().get('request','?')})" if r.status_code==200 else f"[ERROR] HTTP {r.status_code}"
    except Exception as e: return f"[ERROR] {e}"

def _load_mem():
    global _MF; _MF=_MF or Config.WORKSPACE_ROOT/"chat_history"/".codex_memory.json"
    return json.loads(_MF.read_text()) if _MF.exists() else {}

def _save_mem(d): _MF.write_text(json.dumps(d,indent=2,ensure_ascii=False))

def _expire(d):
    n=time.time(); old=[k for k,v in d.items() if isinstance(v,dict) and v.get("_expires_at",0)>0 and v["_expires_at"]<n]
    for k in old: del d[k]
    return len(old)

def tool_memory_read(key: str, default_value: str = "") -> str:
    with _MLOCK: d=_load_mem(); c=_expire(d)
    if c>0: _save_mem(d)
    if key=="*":
        if not d: return "(empty)"
        ls=[f"Memory ({len(d)} keys):"]
        for k in sorted(d.keys()):
            v=d[k]
            if isinstance(v,dict) and "_value" in v:
                ex=""
                if v.get("_expires_at",0)>0: ex=f" [expires {format_timestamp(v['_expires_at'])}]"
                ls.append(f"  {k}: {str(v['_value'])[:60]}... ({v.get('_created','?')}{ex})")
            else: ls.append(f"  {k}: {str(v)[:80]}")
        return "\n".join(ls)
    v=d.get(key); return str(v["_value"]) if isinstance(v,dict) and "_value" in v else (str(v) if v is not None else (default_value or f"(key '{key}' not found)"))

def tool_memory_write(key: str, value: str, ttl_seconds: int = 0, tags: list = None) -> str:
    with _MLOCK: d=_load_mem(); _expire(d)
    e={"_value":value,"_created":datetime.now(timezone.utc).isoformat(),"_updated":datetime.now(timezone.utc).isoformat()}
    if ttl_seconds>0: e["_expires_at"]=time.time()+ttl_seconds
    if tags: e["_tags"]=[str(t) for t in tags]
    if key in d and isinstance(d[key],dict): e["_created"]=d[key].get("_created",e["_created"])
    d[key]=e
    with _MLOCK: _save_mem(d)
    xtra=[]
    if ttl_seconds>0: xtra.append(f"TTL={ttl_seconds}s")
    if tags: xtra.append(f"tags={','.join(tags)}")
    return f"[OK] Stored '{key}' ({len(value)} chars)"+(f" ({', '.join(xtra)})" if xtra else "")

# ══════════════════════════════════════════════════════════════════════════════
# Web Search (local HTTP fetch — replaces OpenAI's hosted search API)
# ══════════════════════════════════════════════════════════════════════════════

def tool_web_search(query: str, max_results: int = 3, search_mode: str = "auto") -> str:
    """
    Search the web or fetch a URL. Uses curl subprocess for real browser-like
    fetching (handles JS-heavy sites and anti-bot protection better than httpx).

    Modes:
      - auto: If query looks like a URL, fetch it directly. Otherwise search.
      - url: Always treat query as a URL to fetch.
      - search: Always perform a web search.
    """
    try:
        import httpx
        import html
        from urllib.parse import quote_plus
        from html.parser import HTMLParser

        # ── HTML to text helper ────────────────────────────────────────
        class _HTMLStripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.reset()
                self._parts = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ('script','style','noscript','meta','link','head'):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ('script','style','noscript','meta','link','head'):
                    self._skip = False
                if tag in ('p','br','li','div','h1','h2','h3','h4','h5','h6','tr','article','section'):
                    self._parts.append('\n')
            def handle_data(self, d):
                if not self._skip:
                    t = d.strip()
                    if t: self._parts.append(t + ' ')

        def html_to_text(html: str, max_len: int = 6000) -> str:
            s = _HTMLStripper()
            try:
                s.feed(html)
            except:
                pass
            text = re.sub(r'\s+', ' ', ''.join(s._parts)).strip()
            return text[:max_len] + ('...[truncated]' if len(text) > max_len else '')

        # ── Fetch via curl (primary) or httpx (fallback) ──────────────
        def fetch_url(url: str, timeout: int = 20) -> str:
            """Fetch a URL using curl subprocess for real browser behavior."""
            try:
                r = subprocess.run([
                    'curl', '-s', '-L', '--max-time', str(timeout),
                    '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    '-H', 'Accept-Language: en-US,en;q=0.9',
                    '-H', 'Cache-Control: no-cache',
                    url
                ], capture_output=True, timeout=timeout + 5)
                return r.stdout.decode('utf-8', errors='replace') if r.returncode == 0 else f"[curl error {r.returncode}] {r.stderr.decode('utf-8', errors='replace')[:200]}"
            except FileNotFoundError:
                # curl not available — fall back to httpx
                try:
                    client = httpx.Client(timeout=timeout, follow_redirects=True, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                    })
                    resp = client.get(url)
                    return resp.text
                except Exception as e:
                    return f"[ERROR] fetch failed: {e}"
            except Exception as e:
                return f"[ERROR] curl failed: {e}"

        # ── Determine mode ──────────────────────────────────────────────
        is_url = search_mode == "url" or (
            search_mode == "auto" and re.match(r'^https?://', query)
        )

        if is_url:
            raw = fetch_url(query)
            if raw.startswith('[ERROR]'):
                return raw

            title = ''
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', raw, re.IGNORECASE)
            if title_match:
                title = html.unescape(title_match.group(1).strip())

            text = html_to_text(raw, 5000)
            return (
                f"URL: {query}\n"
                f"Title: {title or '(no title)'}\n"
                f"{'-'*50}\n"
                f"{text}"
            )

        else:
            # ── SEARCH MODE ─────────────────────────────────────────────
            results = []

            # Try Google News RSS first (fast, reliable, no JS needed)
            try:
                rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
                rss_raw = fetch_url(rss_url)

                # Parse RSS items
                items = re.findall(r'<item>(.*?)</item>', rss_raw, re.DOTALL)
                for item in items[:max_results]:
                    t = re.search(r'<title>(.*?)</title>', item)
                    l = re.search(r'<link>(.*?)</link>', item)
                    d = re.search(r'<description>(.*?)</description>', item)
                    title_text = html.unescape(re.sub(r'<[^>]+>', '', t.group(1).strip())) if t else ''
                    link_text = l.group(1).strip() if l else ''
                    desc_text = html.unescape(re.sub(r'<[^>]+>', '', d.group(1).strip())) if d else ''
                    if title_text:
                        results.append(f"  {len(results)+1}. {title_text[:120]}\n     {link_text}\n     {desc_text[:200]}")
            except Exception:
                pass  # RSS failed, try next method

            # If RSS gave enough results, return them
            if len(results) >= max_results:
                return (
                    f"Search: '{query}' (Google News)\n"
                    f"Results: {len(results)}\n"
                    f"{'-'*50}\n"
                    + "\n".join(results)
                )

            # Fallback: DuckDuckGo HTML search
            try:
                client = httpx.Client(timeout=15, follow_redirects=True, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                ddg_resp = client.get(ddg_url)
                ddg_text = ddg_resp.text

                # Parse DDG results
                link_re = r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
                snip_re = r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>'

                ddg_links = re.findall(link_re, ddg_text, re.DOTALL | re.IGNORECASE)
                ddg_snips = re.findall(snip_re, ddg_text, re.DOTALL | re.IGNORECASE)

                for i, (href, title_raw) in enumerate(ddg_links[:max_results - len(results)]):
                    title_clean = re.sub(r'<[^>]+>', '', title_raw).strip()
                    title_clean = title_clean.replace('&amp;', '&').replace('&#x27;', "'")

                    # Decode DDG redirect
                    from urllib.parse import unquote
                    clean_url = href
                    if 'uddg=' in href:
                        clean_url = unquote(href.split('uddg=')[-1].split('&')[0].split('&amp;')[0])
                    clean_url = clean_url.replace('&amp;', '&')

                    snip = ''
                    if i < len(ddg_snips):
                        snip = re.sub(r'<[^>]+>', '', ddg_snips[i]).strip()
                        snip = snip.replace('&amp;', '&').replace('&#x27;', "'")

                    if title_clean:
                        results.append(f"  {len(results)+1}. {title_clean[:120]}\n     {clean_url}\n     {snip[:200]}")

            except Exception:
                pass  # DDG failed

            if not results:
                return f"Search: '{query}'\nNo results found. Try a different query or use search_mode='url' to fetch a specific page."

            return (
                f"Search: '{query}'\n"
                f"Results: {len(results)}\n"
                f"{'-'*50}\n"
                + "\n".join(results)
            )

    except Exception as e:
        return f"[ERROR] Web search failed: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# Tool Dispatch — the central dispatcher
# ══════════════════════════════════════════════════════════════════════════════

TOOL_MAP = {
    "shell_command":        tool_shell_command,
    "read_file":            tool_read_file,
    "write_file":           tool_write_file,
    "list_directory":       tool_list_directory,
    "search_files":         tool_search_files,
    "grep_search":          tool_grep_search,
    "apply_patch":          tool_apply_patch,
    "view_image":           tool_view_image,
    "current_time":         tool_current_time,
    "plan":                 tool_plan,
    "request_user_input":   tool_request_user_input,
    "spawn_agent":          tool_spawn_agent,
    "wait_agent":           tool_wait_agent,
    "list_agents":          tool_list_agents,
    "cancel_agent":         tool_cancel_agent,
    "send_notification":    tool_send_notification,
    "memory_read":          tool_memory_read,
    "memory_write":         tool_memory_write,
    "web_search":           tool_web_search,
}


def execute_tool(name: str, args: dict) -> str:
    """
    Dispatch a tool call by name.

    Args:
        name: Tool name (must match a key in TOOL_MAP).
        args: Arguments dict from the parsed tool call.

    Returns:
        String result from the tool implementation.
    """
    fn = TOOL_MAP.get(name)
    if fn is None:
        return f"[ERROR] Unknown tool: '{name}'. Available: {', '.join(TOOL_MAP.keys())}"

    try:
        result = fn(**args)
        return str(result) if result is not None else "[OK] Done."
    except TypeError as e:
        return f"[ERROR] Invalid arguments for '{name}': {e}"
    except Exception as e:
        logger.exception(f"Tool '{name}' crashed")
        return f"[ERROR] Tool '{name}' crashed: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# Query helpers — for the web UI tasks panel
# ══════════════════════════════════════════════════════════════════════════════

def get_plans() -> list:
    """Return current plans for the web UI."""
    return [{"title": k, "steps": v} for k, v in _PLANS.items()]

def get_sub_agents() -> list:
    """Return sub-agent statuses for the web UI."""
    return [
        {"id": aid, "name": a["name"], "status": a["status"],
         "task": a.get("task", ""), "result": a.get("result", ""),
         "spawned": a.get("spawned", 0), "done": a.get("done", 0)}
        for aid, a in _AGENTS.items()
    ]

def get_pending_questions() -> list:
    """Return pending user questions for the web UI."""
    return [{"id": qid, **q} for qid, q in _PENDING.items() if q["answer"] is None]
