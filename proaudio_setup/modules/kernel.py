import os, re, logging
from proaudio_setup.utils import *

log = logging.getLogger("kernel")

class Grubby:
    @classmethod
    def usable(cls):
        return root

    def __init__(self):
        self.cur_kern=cmd("grubby", "--default-kernel")
        self.get_info()

    def get_info(self):
        self.info = {}
        for line in cmd("grubby", f"--info={self.cur_kern}").split("\n"):
            line = line.strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            self.info[k] = v.lstrip('"').rstrip('"')

    def args(self):
        args = self.info.get("args", "").split()
        log.debug(f"Grubby kernel args: {args}")
        return args

    def add_arg(self, arg):
        cmd("grubby", "--update-kernel=ALL", f"--args={arg}")
        self.get_info()

    def rm_arg(self, arg):
        cmd("grubby", "--update-kernel=ALL", f"--remove-args={arg}")
        self.get_info()

CMDLINE_BACKENDS = {
    "fedora": Grubby
}

def init():
    global cmdline_backend, PREEMPT_DYNAMIC

    distro = get_distro()

    try:
        cmdline_backend = CMDLINE_BACKENDS.get(distro, None)
        if cmdline_backend:
            log.info(f"Using {cmdline_backend.__name__} for kernel command line management")
            if cmdline_backend.usable():
                cmdline_backend = cmdline_backend()
            else:
                cmdline_backend = None
    except:
        warn(f"Failed to initialize {cmdline_backend} to access kernel command line options.")
        cmdline_backend = None

    PREEMPT_DYNAMIC = "PREEMPT_DYNAMIC" in os.uname().version

def preempt():
    for k in os.uname().version.split():
        if k.startswith("PREEMPT"):
            return k
    return "<unknown>"

def get_cmdline():
    with open("/proc/cmdline") as fd:
        return fd.read().split()

def parse_cmdline():
    cmdline = get_cmdline()

    opts = {}
    for i in cmdline:
        if "=" in i:
            k, v = i.split("=", 1)
            opts[k] = v
        else:
            opts[i] = True

    return opts

def check():
    reboot = False
    fixable = False
    hdr("Checking kernel configuration:")

    opts = parse_cmdline()

    def fixarg(arg):
        nonlocal fixable, reboot
        if cmdline_backend:
            if arg in cmdline_backend.args():
                fix(f"Reboot to fix")
                reboot = True
            else:
                fixable = True
                fix(f"Automatically fixable")
        else:
            fix(f"Add `{arg}` to your kernel command line")

    if opts.get("threadirqs", False):
        ok("Threaded IRQs enabled", "[`threadirqs`]")
    else:
        bad("Threaded IRQs disabled", "[`threadirqs`]")
        fixarg("threadirqs")

    nohz_full = opts.get("nohz_full", False)
    if nohz_full == "all":
        ok("Tickless mode enabled", "[`nohz_full=all`]")
    else:
        bad("Tickless mode not enabled", f"[`nohz_full={nohz_full}`]")
        fixarg("nohz_full=all")

    if preempt() == "PREEMPT_DYNAMIC":
        opt = opts.get("preempt", "voluntary")
        if opt == "full":
            ok("Full preemption enabled", "[`preempt=full`]")
        else:
            bad(f"Full preemption disabled", f"[`preempt={opt}`]")
            fixarg("preempt=full")
    else:
        if preempt() == "PREEMPT":
            ok("Full preemption enabled", "[`CONFIG_PREEMPT`]")
        else:
            bad(f"Full preemption disabled", f"[`CONFIG_{preempt()}`]")
            fix("Switch to a realtime-capable kernel (`CONFIG_PREEMPT` or `CONFIG_PREEMPT_DYNAMIC`)")

    if fixable:
        return "configure"
    if reboot:
        return "reboot"

def configure():
    reboot = False
    if cmdline_backend is None:
        return

    opts = get_cmdline()

    need_args = ["nohz_full=all", "threadirqs"]
    if preempt() == "PREEMPT_DYNAMIC":
        need_args.append("preempt=full")
    for arg in need_args:
        if arg not in cmdline_backend.args():
            try:
                cmdline_backend.add_arg(arg)
                ok(f"Added `{arg}` to kernel command line")
                reboot = True
            except:
                bad(f"Failed to add `{arg}` to kernel command line")
        elif arg not in opts:
            reboot = True

    return "reboot" if reboot else None

def unconfigure():
    reboot = False
    if cmdline_backend is None:
        return

    opts = get_cmdline()

    remove_args = ["nohz_full=all", "threadirqs", "preempt=full"]
    for arg in remove_args:
        if arg in cmdline_backend.args():
            try:
                cmdline_backend.rm_arg(arg)
                ok(f"Removing `{arg}` from kernel command line")
                reboot = True
            except:
                bad(f"Failed to remove `{arg}` from kernel command line")
        elif arg in opts:
            reboot = True

    return "reboot" if reboot else None
