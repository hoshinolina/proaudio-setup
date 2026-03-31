import pwd, grp, logging
from proaudio_setup.utils import *

log = logging.getLogger("user")

REALTIME_GROUPS = ["realtime"]

def get_realtime_group():
    for gname in REALTIME_GROUPS:
        try:
            return grp.getgrnam(gname)
        except:
            continue
    else:
        log.info("Cannot find real-time group")
        return None

def get_user():
    for env in ["SUDO_USER", "DOAS_USER", "USER"]:
        user = os.environ.get(env, None)
        if user and user != "root":
            break

    if not user or user == "root":
        logging.info(f"Could not identify current logged-in non-root user")
        return None

    try:
        pw = pwd.getpwnam(user)
    except:
        logging.warn(f"Failed to load passwd entry for {user}")
        return None

    return pw

def check():
    reboot = False
    hdr("Checking user configuration:")

    gr = get_realtime_group()
    if not gr:
        alert("Cannot find group for real-time permissions")
        return

    pw = get_user()
    if not pw:
        alert("Cannot find logged-in user")
        fix(f"If you are logged in as root, try logging in as your user and running `sudo {argvall}` instead.")
        return

    info(f"Logged-in user:", f"`{pw.pw_name}`")

    if pw.pw_gid == gr.gr_gid or pw.pw_name in gr.gr_mem:
        ok(f"User `{pw.pw_name}` is a member of the `{gr.gr_name}` group")
    else:
        bad(f"User `{pw.pw_name}` is not a member of the `{gr.gr_name}` group")
        fix(f"Automatically fixable")


def configure():
    gr = get_realtime_group()
    if not gr:
        return
    pw = get_user()
    if not pw:
        return
    if pw.pw_gid == gr.gr_gid or pw.pw_name in gr.gr_mem:
        return

    ok(f"Adding user `{pw.pw_name}` to the `{gr.gr_name}` group")
    cmd("usermod", "-aG", gr.gr_name, pw.pw_name)

    return "reboot"

def unconfigure():
    gr = get_realtime_group()
    if not gr:
        return
    pw = get_user()
    if not pw:
        return
    if pw.pw_name not in gr.gr_mem:
        return

    ok(f"Removing user `{pw.pw_name}` from the `{gr.gr_name}` group")
    cmd("usermod", "-rG", gr.gr_name, pw.pw_name)

    return "reboot"
