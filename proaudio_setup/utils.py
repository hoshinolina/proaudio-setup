import sys, re, subprocess, os, logging, syslog
import click

def cmd(*c, default=None, check=True):
    try:
        sp = subprocess.run(c, stdout=subprocess.PIPE, check=check)
        return sp.stdout.decode("utf-8").strip()
    except:
        if default is not None:
            return default
        raise Exception(f"Command `{' '.join(c)}` failed")

root = os.getuid() == 0

def get_distro():
    return cmd("lsb_release", "-si", default='unknown').strip().lower()
    logging.info("Distribution:", distro)

argv0 = sys.argv[0]
if argv0 == "-m":
    argv0 = "python3 -m proaudio_setup"

argvall = " ".join([argv0, *sys.argv[1:]])

def autofmt(s):
    if not s:
        return s

    def cb(m):
        return click.style(m.group(1), fg="magenta", bold=True)
    s = re.sub(r"`([^`]+)`", cb, s)

    def cb(m):
        return click.style(m.group(1), bold=True)
    s = re.sub(r"\*([^*]+)\*", cb, s)

    out = []
    stack = []
    for tok in re.split("((?:\x1b\\[[^m]*m)+)", s):
        if not tok:
            continue
        if tok[0] != "\x1b":
            out.append(tok)
            continue

        while tok.startswith('\x1b[0m'):
            out.append('\x1b[0m')
            stack.pop()
            if stack:
                out.append(stack[-1])
            tok = tok[4:]
        if not tok:
            continue

        if tok.endswith('\x1b[0m'):
            continue
        else:
            stack.append(tok)

        out.append(tok)
    return "".join(out)

_indent = 0
_ilist = None

def readfile(f):
    if not os.path.exists(f):
        return None
    with open(f) as fd:
        return fd.read().strip()

def writefile(f, v):
    with open(f, "w") as fd:
        fd.write(v)

_do_syslog = False

def enable_syslog():
    global _do_syslog
    _do_syslog = True
    logging.getLogger().addHandler(logging.handlers.SysLogHandler())

def msg(s=""):
    s = autofmt(s)
    click.echo("  " * _indent + s, err=True)
    if _do_syslog:
        syslog.syslog("  " * _indent + s)

def hdr(s=""):
    global _indent
    msg(click.style("\n" + s, bold=True))
    _indent += 1

def fix(s):
    msg(f"ℹ️ {s}")

def ok(s, t=None):
    global _indent, _ilist
    if _ilist is not None:
        _indent = _ilist
    msg(click.style(f"✅️ {s}", fg="green", bold=True) + (f" {t}" if t else ""))
    _ilist = _indent
    _indent += 1

def alert(s, t=None):
    global _indent, _ilist
    if _ilist is not None:
        _indent = _ilist
    msg(click.style(f"⚠️ {s}", fg="yellow", bold=True) + (f" {t}" if t else ""))
    _ilist = _indent
    _indent += 1

def unk(s, t=None):
    global _indent, _ilist
    if _ilist is not None:
        _indent = _ilist
    msg(f"❔️ {s}" + (f" {t}" if t else ""))
    _ilist = _indent
    _indent += 1

def bad(s, t=None):
    global _indent, _ilist
    if _ilist is not None:
        _indent = _ilist
    msg(click.style(f"❌️ {s}", fg="red", bold=True) + (f" {t}" if t else ""))
    _ilist = _indent
    _indent += 1

def info(s):
    msg(click.style(f"Info: {s}", underline=True))

def warn(s):
    msg(click.style(f"Warning: {s}", fg="yellow", bold=True))

def err(s):
    msg(click.style(f"Error: {s}", fg="red", bold=True))

def pop():
    global _indent, _ilist
    if _ilist is not None:
        _indent = _ilist
    _indent = max(_indent - 1, 0)
    msg("")

def popall():
    global _indent, _ilist
    _indent = 0
    _ilist = None
