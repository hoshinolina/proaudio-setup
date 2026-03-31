# SPDX-FileCopyrightText: 2026-present Hoshino Lina <lina@lina.yt>
#
# SPDX-License-Identifier: MIT
import logging, logging.handlers
logging.basicConfig(level=logging.DEBUG)

import click, fcntl

from proaudio_setup.__about__ import __version__
from proaudio_setup import ALL_MODULES
from proaudio_setup.utils import *

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger("cli")

def lock():
    if not root:
        err("This command must be run as root")
        fix(f"Try running `sudo {argvall}` instead.")
        sys.exit(1)

    LOCKFILE = "/run/lock/proaudio-setup.lock"

    global lockfd
    try:
        lockfd = open(LOCKFILE, "w")
    except:
        log.warn(f"Failed to open lockfile {LOCKFILE}")
        return

    fcntl.flock(lockfd.fileno(), fcntl.LOCK_EX)

def run_modules(command, *args, **kwargs):
    rets = []
    for mod in ALL_MODULES:
        fn = getattr(mod, "init", None)
        if fn:
            fn()
        popall()
        fn = getattr(mod, command, None)
        if fn:
            rets.append(fn(*args, **kwargs))
        popall()
    return rets

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="proaudio-setup")
@click.option("--verbose", "-v", count=True, help="Verbose logs (twice for debug)")
def proaudio_setup(verbose):
    logging.getLogger().setLevel(logging.WARN - 10 * verbose)

@proaudio_setup.command()
def check():
    """Check system configuration and suggest changes"""
    if not root:
        info("Not running as root, some information may be incomplete")
        fix(f"Try running `sudo {argvall}` instead.")
    rets = run_modules("check")
    if "configure" in rets:
        hdr(f"Some issues are automatically fixable.")
        fix(f"Run `sudo {argv0} configure` {"and reboot " if "reboot" in rets else ""} to apply fixes.")
    elif "reboot" in rets:
        hdr(f"Some issues will be fixed after a reboot.")
        fix(f"Reboot your system and run `sudo {argv0} check` again.")
    elif "apply" in rets:
        hdr(f"Some issues are runtime tweaks.")
        fix(f"Run `sudo {argv0} apply` to apply changes until reboot.")
        alert(f"If proaudio-setup is correctly installed, this should happen automatically on every reboot!")

@proaudio_setup.command()
def configure():
    """Configure persistent system settings"""
    lock()
    click.echo("Configuring system for proaudio...")
    rets = run_modules("configure")
    rets += run_modules("apply")
    if "reboot" in rets:
        msg()
        fix(f"Reboot your system to apply the changes.")
    elif any(rets):
        msg()
        msg("Changes applied (no reboot needed).")
    else:
        msg()
        msg("No changes needed.")

@proaudio_setup.command()
def unconfigure():
    """Unconfigure persistent system settings"""
    lock()
    click.echo("Unconfiguring system for proaudio...")
    rets = run_modules("unconfigure")
    if "reboot" in rets:
        msg()
        fix(f"Reboot your system to apply the changes.")
    elif not any(rets):
        msg("No changes needed.")

@proaudio_setup.command()
def apply():
    """Apply runtime settings on startup, resume, or hotplug"""
    lock()
    click.echo("Applying runtime settings...")
    rets = run_modules("apply")
    if any(rets):
        msg()
        msg("Changes applied.")
    else:
        msg("No changes needed.")

@proaudio_setup.group()
def trigger():
    pass

trigger.hidden = True

@trigger.command()
def postin():
    """Trigger post-install actions"""
    lock()
    rets = run_modules("configure")
    if "reboot" in rets:
        msg()
        fix(f"Reboot your system to apply the changes.")

@trigger.command()
def postun():
    """Trigger post-uninstall actions"""
    lock()
    rets = run_modules("unconfigure")
    if "reboot" in rets:
        msg()
        fix(f"Reboot your system to apply the changes.")

@trigger.command()
def udev():
    """Trigger device add/remove actions"""
    lock()
    enable_syslog()
    run_modules("apply")

@trigger.command()
def boot():
    """Trigger boot actions"""
    lock()
    run_modules("apply")

@trigger.command()
def wake():
    """Trigger wake from sleep actions"""
    lock()
    run_modules("apply", nosvc=True)
