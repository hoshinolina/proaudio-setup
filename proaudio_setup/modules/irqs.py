import os, re, logging, stat, socket
import collections.abc
from proaudio_setup.utils import *

log = logging.getLogger("irqs")

PRIO_RTPRI = 80
PRIO_RTSEC = 70

class IRQBalance:
    def __new__(cls):
        if not root:
            return None

        path = "/run/irqbalance"
        socks = os.listdir(path)
        if len(socks) == 1:
            obj = super(IRQBalance, cls).__new__(cls)
            obj.path = f"{path}/{socks[0]}"
            return obj
        else:
            return None

    def cmd(self, cmd):
        cmd += "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(self.path)
            client.send(cmd.encode("ascii"))
            ret = b""
            while True:
                msg = client.recv(8192)
                if not msg:
                    break
                ret += msg
            return ret.decode("ascii")

    def get_setup(self):
        vals = re.split(r"(SLEEP|IRQ|BANNED) ", self.cmd("setup"))
        assert not vals[0]
        i = iter(vals[1:])
        for k, v in zip(i, i):
            yield k.strip(), v.strip()

    def get_banned_cpus(self):
        for k, v in self.get_setup():
            if k == "BANNED":
                return CPUSet(v.replace(",", ""))
        return None

    def set_banned_cpus(self, mask):
        self.cmd(f"settings cpus {str(mask) if mask else ""}")

    def set_banned_irqs(self, irqs):
        self.cmd(f"settings ban irqs {" ".join(map(str, irqs))}")

    def get_banned_irqs(self):
        banned = set()
        for k, v in self.get_setup():
            if k == "IRQ":
                banned.add(int(v.split()[0]))
        return banned

class CPU(int):
    def __new__(cls, v):
        return super(CPU, cls).__new__(cls, int(v))

    def attr(self, v):
        return readfile(f"/sys/devices/system/cpu/cpu{self}/{v}")

    @property
    def online(self):
        return self.attr("online") != "0"

    @property
    def thread_siblings(self):
        siblings = self.attr("topology/thread_siblings")
        if siblings is None:
            return CPUSet([self])
        return CPUSet(siblings)

    @property
    def thread(self):
        return sorted(self.thread_siblings).index(self)

    @property
    def capacity(self):
        return int(self.attr("cpu_capacity") or "1024")

class CPUSet(collections.abc.MutableSet):
    @classmethod
    def all(cls):
        all = cls()
        for cpu in os.listdir("/sys/devices/system/cpu"):
            if re.match("^cpu[0-9]+$", cpu):
                all.add(CPU(int(cpu[3:])))
        return all

    @classmethod
    def online(cls):
        return cls(i for i in cls.all() if i.online)

    def __init__(self, v=[]):
        self.s = set()
        if isinstance(v, str):
            v = int(v, 16)
        if isinstance(v, int):
            i = 0
            while v:
                if v & (1 << i):
                    v &= ~(1 << i)
                    self.s.add(CPU(i))
                i += 1
        else:
            for i in v:
                self.s.add(CPU(i))

    def __invert__(self):
        return self.online() - self

    def __contains__(self, other):
        return other in self.s

    def __iter__(self):
        return iter(self.s)

    def __len__(self):
        return len(self.s)

    def add(self, other):
        assert isinstance(other, CPU)
        self.s.add(other)

    def discard(self, other):
        assert isinstance(other, CPU)
        self.s.discard(other)

    def __str__(self):
        if len(self) == 0:
            return "<none>"
        l = []
        prev = None
        for i in sorted(self):
            if l and i == (l[-1][1] + 1):
                l[-1][1] = i
            else:
                l.append([i, i])
        s = []
        for a, b in l:
            if a == b:
                s.append(str(a))
            else:
                s.append(f"{a}-{b}")
        return ",".join(s)

    def hex(self):
        return f"{int(self):x}"

    def __int__(self):
        v = 0
        for i in self:
            v |= (1 << i)
        return v

class IRQ:
    def __init__(self, n):
        self.n = n

    def attr(self, v):
        return readfile(f"/proc/irq/{self.n}/{v}")

    def attr_writable(self, v):
        st = os.stat(f"/proc/irq/{self.n}/{v}")
        return bool(st.st_mode & stat.S_IWUSR)

    def write_attr(self, v, s):
        writefile(f"/proc/irq/{self.n}/{v}", s)

    @property
    def effective_affinity(self):
        v = self.attr("effective_affinity")
        return CPUSet(v) if v is not None else None

    @property
    def smp_affinity(self):
        v = self.attr("smp_affinity")
        return CPUSet(v) if v is not None else None

    @property
    def can_set_affinity(self):
        return self.attr_writable("smp_affinity")

    def set_affinity(self, v):
        self.write_attr("smp_affinity", v.hex())

    @property
    def devices(self):
        devs = []
        for i in os.listdir(f"/proc/irq/{self.n}"):
            st = os.stat(f"/proc/irq/{self.n}/{i}")
            if stat.S_ISDIR(st.st_mode):
                devs.append(i)
        return devs

    def __str__(self):
        return f"IRQ #{self.n}: Cur {self.smp_affinity} ({self.effective_affinity}) {"writable" if self.can_set_affinity else ""} | {", ".join(self.devices)}"

    def __hash__(self):
        return hash(self.n)

    def __eq__(self, other):
        return self.n == other.n

class Device:
    def __init__(self, path):
        self.path = os.path.realpath(path)

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return self.path == other.path

    def attr(self, v):
        return readfile(f"{self.path}/{v}")

    def walk(self, k):
        path = self.path
        while path != "/sys/devices":
            apath = os.path.join(path, k)
            if os.path.exists(os.path.join(path, k)):
                return apath
            path, _ = os.path.split(path)

    def rwalk(self, k):
        p = self.walk(k)
        return readfile(p) if p else None

    def lwalk(self, k):
        p = self.walk(k)
        return os.readlink(p) if p else None

    @property
    def product(self):
        return self.rwalk("product")

    @property
    def manufacturer(self):
        return self.rwalk("manufacturer")

    @property
    def usb_device(self):
        dpath = self.walk("bNumConfigurations")
        if dpath:
            return os.path.split(dpath)[0]
        else:
            return None

    @property
    def driver(self):
        drv = self.lwalk("driver")
        if not drv:
            log.warn(self.path)
        else:
            return drv.split("/")[-1]

    @property
    def name(self):
        if self.product or self.manufacturer:
            return f"{self.manufacturer} {self.product}"
        else:
            return self.attr("name") or self.attr("id") or self.path

    @property
    def irqs(self):
        path = self.path
        irqs = set()
        while path != "/sys/devices":
            if os.path.exists(f"{path}/irq"):
                irq = int(readfile(f"{path}/irq") or "0")
                if irq and os.path.exists(f"/proc/irq/{irq}"):
                    irqs.add(irq)
            if os.path.exists(f"{path}/msi_irqs"):
                for irq in os.listdir(f"{path}/msi_irqs"):
                    irq = int(irq)
                    if irq and os.path.exists(f"/proc/irq/{irq}"):
                        irqs.add(irq)
            if irqs:
                return irqs
            path, _ = os.path.split(path)
        return None


    @property
    def dev(self):
        return self.attr("dev")

    def __str__(self):
        return f"{self.dev} ({self.driver}, irqs={self.irqs}): {self.name}"

class AudioCard(Device):
    def __init__(self, path):
        self.path = os.path.realpath(path)

    @property
    def card(self):
        return os.path.split(self.path)[-1]

    @property
    def number(self):
        return int(self.attr("number"))

    @property
    def name(self):
        for line in readfile("/proc/asound/cards").split("\n"):
            line = line.strip()
            if "]: " in line and line.startswith(f"{self.number} "):
                return line.split("]: ", 1)[1]
        return super(self).name

    def __str__(self):
        return f"{self.card} ({self.driver}, irqs={self.irqs}): {self.name} {"[VIDEO]" if self.is_usbvideo else ""}"

    @property
    def is_usbvideo(self):
        usb = self.usb_device
        if not usb:
            return False
        for sub in os.listdir(usb):
            if os.path.exists(f"{usb}/{sub}/video4linux"):
                return True
        return False

class IRQManager:
    def __init__(self):
        self.load_cpus()
        self.load_irqthreads()
        self.load_irqs()

        def is_audio(p):
            return os.path.split(p)[1].startswith("card") and (
                any(i.startswith("pcm") for i in os.listdir(p)))
        self.audio_devs = self.load_devs(AudioCard, "sound", is_audio)
        self.video_devs = self.load_devs(Device, "video4linux")
        self.assign_irqs()
        self.assign_cpus()

    def load_cpus(self):
        self.all_cpus = CPUSet.all()
        log.info(f"All CPUs: {self.all_cpus}")
        self.online_cpus = CPUSet.online()
        log.info(f"Online CPUs: {self.online_cpus}")
        self.thread0_cpus = CPUSet(i for i in self.online_cpus if i.thread == 0)
        log.info(f"Primary threads: {self.thread0_cpus}")
        self.threadn_cpus = CPUSet(i for i in self.online_cpus if i.thread != 0)
        log.info(f"Secondary threads: {self.threadn_cpus}")

        self.rt_candidates = sorted(self.thread0_cpus, key=lambda c: c.capacity)

    def assign_cpus(self):
        self.manage_cpus = True
        if len(self.rt_candidates) >= 4 and self.pri_irqs and self.sec_irqs:
            self.rt_pri = CPUSet([self.rt_candidates[-1]])
            self.rt_sec = CPUSet([self.rt_candidates[-2]])
            self.rt_cpus = self.rt_pri | self.rt_sec
            log.info(f"Realtime CPUs: {self.rt_pri} / {self.rt_sec}")
        elif len(self.rt_candidates) >= 2 and (self.pri_irqs or self.sec_irqs):
            self.rt_cpus = self.rt_pri = self.rt_sec = CPUSet([self.rt_candidates[-1]])
            log.info(f"Realtime CPU: {self.rt_pri}")
        else:
            self.rt_pri = self.rt_sec = self.rt_cpus = CPUSet()
            if self.pri_irqs or self.sec_irqs:
                log.info(f"Not enough CPUs for realtime")
                self.manage_cpus = False

        # Add in the threads
        self.rt_cpus = CPUSet(i for i in self.online_cpus if i.thread_siblings & self.rt_cpus)

        self.nonrt_cpus = self.online_cpus - self.rt_cpus
        self.nonrt_cores = self.thread0_cpus - self.rt_cpus
        log.info(f"Non-realtime CPUs: {self.nonrt_cpus}")

    def load_irqs(self):
        self.irqs = {}
        for irq in os.listdir("/proc/irq"):
            try:
                n = int(irq)
            except ValueError:
                continue
            irq = IRQ(n)
            log.info(irq)
            self.irqs[n] = irq

    def load_irqthreads(self):
        self.irqthreads = {}

        for pid in os.listdir("/proc"):
            try:
                pid = int(pid)
            except ValueError:
                continue

            PF_KTHREAD = 0x00200000

            try:
                stat = readfile(f"/proc/{pid}/stat")
            except:
                pass
            if not stat:
                continue
            stat = stat.split()
            flags = int(stat[8])
            if not (flags & PF_KTHREAD):
                continue

            try:
                comm = readfile(f"/proc/{pid}/comm")
            except:
                continue
            if not comm:
                continue

            m = re.match(f"^irq/([0-9]+)-", comm)
            if m:
                n = int(m.group(1))
                self.irqthreads.setdefault(n, {})[pid] = comm

    def load_devs(self, cls, kcls, filter=None):
        devs = set()
        if not os.path.exists(f"/sys/class/{kcls}"):
            return
        for dev in os.listdir(f"/sys/class/{kcls}"):
            path = f"/sys/class/{kcls}/{dev}"
            if os.path.realpath(path).startswith("/sys/devices/virtual/"):
                continue
            if filter and not filter(path):
                continue
            d = cls(path)
            if d not in devs:
                log.info(f"{cls.__name__}: {d}")
                devs.add(d)
        return devs

    def load_video(self):
        self.audiodevs = set()
        if not os.path.exists("/sys/class/sound"):
            return
        for pcm in os.listdir("/sys/class/sound"):
            if not pcm.startswith("pcm"):
                continue
            d = AudioCard(f"/sys/class/sound/{pcm}/device")
            if d not in self.audiodevs:
                log.info(f"Audio device: {d}")
                self.audiodevs.add(d)

    def assign_irqs(self):
        self.pri_irqs = set()
        self.sec_irqs = set()
        for dev in self.audio_devs:
            if not dev.irqs:
                log.info(f"Audio device {dev} has no IRQs?")
                continue

            shared_video = set(d for d in self.video_devs if dev.irqs and dev.irqs & d.irqs)
            if shared_video:
                self.sec_irqs |= dev.irqs
            else:
                self.pri_irqs |= dev.irqs

        assert len(self.pri_irqs & self.sec_irqs) == 0

    def check_irqs(self):
        for dev in sorted(self.audio_devs, key=lambda c: c.number):
            if not dev.irqs:
                unk(f"Cannot find IRQ for audio device {dev.number} `{dev.name}`")
                continue
            sirq = ",".join(map(str,dev.irqs))
            if dev.irqs & self.sec_irqs:
                if not dev.is_usbvideo:
                    shared_video = set(d for d in self.video_devs if dev.irqs & d.irqs)
                    others = set(o.name for o in shared_video)
                    alert(f"Audio device {dev.number} `{dev.name}` shares a USB controller with video device(s): `{", ".join(others)}`", f"[{sirq}]")
                    fix("Try moving the devices to different USB ports for better performance.")
            else:
                ok(f"Audio device {dev.number} `{dev.name}` does not share IRQs with slow devices", f"[{sirq}]")

    def check_affinity(self):
        can_apply = False
        for i in self.irqs.values():
            if not i.can_set_affinity or not i.devices:
                continue
            s = f"{i.n} ({", ".join(i.devices)})"
            if i.n in self.pri_irqs:
                if i.smp_affinity == self.rt_pri:
                    ok(f"Real-time IRQ {s} is on the real-time CPU", f"[{i.smp_affinity}]")
                else:
                    bad(f"Real-time IRQ {s} is not on the real-time CPU", f"[{i.smp_affinity}]")
                    fix(f"Automatically fixable")
                    can_apply = True
            elif i.n in self.sec_irqs:
                if i.smp_affinity == CPUSet(self.rt_sec):
                    ok(f"Semi-real-time IRQ {s} is on the semi-real-time CPU", f"[{i.smp_affinity}]")
                else:
                    bad(f"Semi-real-time IRQ {s} is not on the semi-real-time CPU", f"[{i.smp_affinity}]")
                    fix(f"Automatically fixable")
                    can_apply = True
            else:
                if i.smp_affinity & self.rt_cpus:
                    bad(f"Non realtime IRQ {s} is on a realtime CPU", f"[{i.smp_affinity}]")
                    fix(f"Automatically fixable")
                    can_apply = True
        return can_apply

    def apply_affinity(self):
        changed = False
        for i in self.irqs.values():
            if not i.can_set_affinity or not i.devices:
                continue
            if i.n in self.pri_irqs:
                want_cpus = self.rt_pri
                t = "real-time"
            elif i.n in self.sec_irqs:
                want_cpus = self.rt_sec
                t = "semi-real-time"
            else:
                want_cpus = i.smp_affinity & ~self.rt_cpus
                if not want_cpus:
                    want_cpus = self.nonrt_cpus
                t = "non-real-time"

            if want_cpus != i.smp_affinity:
                s = f"{i.n} ({", ".join(i.devices)})"
                ok(f"Moving {t} IRQ {s} to {t} CPU(s)", f"[{want_cpus}]")
                i.set_affinity(want_cpus)
                changed = True

        return changed

    def check_irqbalance(self):
        fixable = False

        irqbalance = IRQBalance()
        if irqbalance is None:
            alert(f"Cannot communicate with irqbalance")
            return

        banned_cpus = irqbalance.get_banned_cpus()
        if banned_cpus == self.rt_cpus:
            ok(f"IRQ balancing avoids real-time CPUs", f"[*{~banned_cpus}*]")
        elif banned_cpus > self.rt_cpus:
            alert(f"IRQ balancing does not use all non-real-time CPUs", f"[*{~banned_cpus}*]")
            fix(f"Automatically fixable")
            fixable = True
        else:
            bad("IRQ balancing uses real-time CPUs", f"[*{~banned_cpus}*]")
            fix(f"Automatically fixable")
            fixable = True

        banned_irqs = irqbalance.get_banned_irqs()
        if banned_irqs >= (self.pri_irqs | self.sec_irqs):
            ok(f"IRQ balancing bans real-time IRQs", f"[*{",".join(map(str, banned_irqs)) or "-"}*]")
        else:
            bad("IRQ balancing does not ban real-time IRQs", f"[*{",".join(map(str, banned_irqs)) or "-"}*]")
            fix(f"Automatically fixable")
            fixable = True

    def apply_irqbalance(self):
        fixed = False

        irqbalance = IRQBalance()
        if irqbalance is None:
            alert(f"Cannot communicate with irqbalance")
            return

        if irqbalance.get_banned_cpus() != self.rt_cpus:
            ok("Using non-realtime CPUs for IRQ balancing", f"[*{~self.rt_cpus}*]")
            irqbalance.set_banned_cpus(self.rt_cpus)
            fixed = True

        ban_irqs = self.pri_irqs | self.sec_irqs
        if irqbalance.get_banned_irqs() < ban_irqs:
            ok(f"Banning realtime IRQs from IRQ balancing", f"[*{",".join(map(str, ban_irqs))}*]")
            irqbalance.set_banned_irqs(ban_irqs)
            fixed = True

        return fixed

    def check_priority(self):
        fixable = False
        for i in (self.pri_irqs | self.sec_irqs):
            want_prio = PRIO_RTPRI if i in self.pri_irqs else PRIO_RTSEC
            semi = "" if i in self.pri_irqs else "semi-"
            if i not in self.irqthreads:
                unk(f"Thread for {semi}real-time IRQ *{i}* not found")
                continue
            for pid, comm in self.irqthreads[i].items():
                param = os.sched_getparam(pid)
                if param.sched_priority != want_prio:
                    bad(f"Thread *{comm}* (*{pid}*) for {semi}real-time IRQ does not have the correct priority", f"[*{param.sched_priority}*]")
                    fix(f"Automatically fixable")
                    fixable = True
                else:
                    ok(f"Thread *{comm}* (*{pid}*) for {semi}real-time IRQ has the correct priority", f"[*{param.sched_priority}*]")

        return fixable

    def apply_priority(self):
        fixed = False
        for i in (self.pri_irqs | self.sec_irqs):
            want_prio = PRIO_RTPRI if i in self.pri_irqs else PRIO_RTSEC
            semi = "" if i in self.pri_irqs else "semi-"
            if i not in self.irqthreads:
                continue
            for pid, comm in self.irqthreads[i].items():
                param = os.sched_getparam(pid)
                if param.sched_priority != want_prio:
                    ok(f"Setting priority for {semi}real-time IRQ thread *{comm}* (*{pid}*)", f"[*{want_prio}*]")
                    param = os.sched_param(want_prio)
                    os.sched_setparam(pid, param)
                    fixed = True

        return fixed

def init():
    global irqm
    irqm = IRQManager()

def check():
    can_configure = False
    can_apply = False

    hdr("Checking IRQ configuration:")

    irqm.check_irqs()

    if not irqm.manage_cpus:
        alert("Not enough CPUs to isolate realtime IRQs")
    else:
        default_smp_affinity = readfile("/proc/irq/default_smp_affinity")
        if default_smp_affinity is not None:
            default_smp_affinity = CPUSet(default_smp_affinity)
            if default_smp_affinity.isdisjoint(irqm.rt_cpus):
                ok("Default IRQ affinity avoids RT CPUs", f"[*{default_smp_affinity}*]")
            else:
                bad("Default IRQ affinity includes RT CPUs", f"[*{default_smp_affinity}*]")
                fix(f"Automatically fixable")
                can_apply = True

        if irqm.check_affinity():
            can_apply = True

        irqbalance = cmd("systemctl", "is-active", "irqbalance", check=False, default=None)

        if irqbalance == "inactive":
            ok("IRQ balancing is disabled")
        elif irqbalance == "active":
            if irqm.check_irqbalance():
                can_apply = True
        else:
            unk("IRQ balancing status is unknown")

    if irqm.check_priority():
        can_apply = True

    if can_configure:
        return "configure"
    elif can_apply:
        return "apply"

# def configure():
#     if irqm.rt_pri is None:
#         return
#
#     changed = False
#
#     irqbalance = cmd("systemctl", "is-active", "irqbalance", check=False, default=None)
#
#     if irqbalance == "active":
#         ok(f"Disabling `irqbalance`")
#         cmd("systemctl", "disable", "--now", "irqbalance")
#
#     return changed

# def unconfigure():
#     if irqm.rt_pri is None:
#         return
#
#     changed = False
#
#     irqbalance = cmd("systemctl", "is-active", "irqbalance", check=False, default=None)
#
#     if irqbalance == "inactive":
#         ok(f"Enabling `irqbalance`")
#         cmd("systemctl", "enable", "--now", "irqbalance")
#
#     ok(f"Enabling `irqbalance`")
#
#     return changed

def apply(nosvc=False):
    changed = False

    if irqm.manage_cpus:
        default_smp_affinity = readfile("/proc/irq/default_smp_affinity")
        if default_smp_affinity is not None:
            if CPUSet(default_smp_affinity) != irqm.nonrt_cores:
                ok(f"Setting default IRQ affinity", f"[*{irqm.nonrt_cores}*]")
                writefile("/proc/irq/default_smp_affinity", irqm.nonrt_cores.hex())
                changed = True

        if not nosvc:
            irqbalance = cmd("systemctl", "is-active", "irqbalance", check=False, default=None)

            if irqbalance == "active" and irqm.apply_irqbalance():
                changed = True

        if irqm.apply_affinity():
            changed = True

    if irqm.apply_priority():
        changed = True

    return changed
