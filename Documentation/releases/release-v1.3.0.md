## Aphelion Kernel v1.3.0

### What's New & Fixed

- **Linux 6.1.183 LTS Upstream Sync:** Aligned with Google ACK android14-6.1-lts with Section 6 MediaTek hardware freezes preserved (100% of 475 stock vendor modules active).
- **DroidSpaces & Docker Support:**
  - CONFIG_USER_NS=y (User namespaces for rootless containers)
  - CONFIG_CGROUP_DEVICE=y (Container device access control)
  - CONFIG_CGROUP_PIDS=y (Container process limits & fork-bomb protection)
  - CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y (Docker port forwarding -p & NAT routing)
  - CONFIG_NETFILTER_XT_TARGET_LOG=y & CONFIG_NETFILTER_XT_MATCH_RECENT=y (Container firewalling & rate limiting)
- **KernelSU & SUSFS Parity:** ReSukiSU/BakaSU submodule pinned with full hook compatibility for SUSFS v2.3.0.
- **Build Infrastructure:** Standalone GKI build fixes (Makefile.ext, default signing keys), and build timestamp standardized to IST.

### Verification & Flashing

- **Asset:** boot.img (67,108,864 bytes, AVB signed)
- **SHA-256:** efdf9c39bf2f33ac80c520f2358696d5f7f1545aef03d9a93a9d9f7b9067dcf

`sh
adb reboot fastboot
fastboot flash boot_a boot.img
fastboot reboot
`