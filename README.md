# proaudio-setup

Automatic system configuration for low-latency professional audio

The goal of this project is to *automatically* (without explicit user configuration) set up the system to support low-latency audio, to make proaudio (studio/streaming) workflows more accessible to non-expert users.

## Runing ad-hoc

Clone the repo, make sure you have the `click` Python module, and run:

    cd proaudio-setup
    sudo python3 -m proaudio_setup check

## Packaging guide

Ideally, this project should be packaged such that the only thing users have to do is to install the package, and that does all the required configuration automatically.

### Support files

All the files in support/ are templates. The packaging should replace `%PREFIX%` with the installation prefix.

* `support/proaudio-setup.service.in`: Systemd unit file. This should be enabled by default, and it is set up to reload any time `irqbalance.service` reloads (`irqbalance.service` itself is optional, it will work without it).
* `support/proaudio-setup.sleep.in`: This should go in `/lib/systemd/system-sleep`. See the comment at the top of the file for more details.
* `support/80-proaudio-setup.rules.in`: Udev rules file.

### Automatic config on install/uninstall

On installation, the packaging should call `proaudio-setup trigger postin`. This will perform systemwide configuration steps. Note that this includes looking for the `SUDO_USER` (or `DOAS_USER`) and adding them to the `realtime` group, if it exists and a non-root user was found.

On uninstallation, the packaging should call `proaudio-setup trigger preun`. This will undo `postin`.

The packaging should, if possible, automatically enable the systemd unit for the user, and direct them to reboot to apply the changes.

`postin` currently only supports Fedora and similar systems that use `grubby`. It will add certain kernel command line arguments (`nohz_full=all threadirqs preempt=full`). If your distribution has a different reliable kernel command line modification system/tool, please submit a PR to add support for it. Otherwise, you should prompt the user on package installation to add those arguments as needed.

Note that `preempt=full` only works for `PREEMPT_DYNAMIC` kernel builds. Otherwise users have to explicitly switch to a realtime kernel build.
