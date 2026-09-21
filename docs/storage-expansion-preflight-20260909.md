# Existing disk capacity preflight

Date: 2026-09-09. Read-only investigation; no partition/filesystem modification performed.

## Observed state

- Root `/dev/vda3`: ext4, mounted read/write, 2,046 MiB available, 95% used.
- Disk `/dev/vda`: 50 GiB; root partition approximately 39.8 GiB.
- Project directory: 7,127 MiB; original evidence 6,949 MiB; backups 117 MiB; exports 55 MiB.
- Container storage: 2,138 MiB across projects. Do not prune shared images or volumes based on this inventory.
- Root inode use: 20%; inode exhaustion is not the observed bottleneck.

## Partition dry run

Commands executed: `sfdisk -d /dev/vda`, `growpart -N /dev/vda 3`, `findmnt -n -o SOURCE,FSTYPE,OPTIONS /`.

`growpart -N` reported CHANGE, without writing:

- Partition start unchanged: 415744 sectors.
- Old size: 83470303 sectors; old end: 83886046.
- Proposed size: 104441823 sectors; proposed end: 104857566.
- Increase: 20971520 sectors, equivalent to 10 GiB with 512-byte sectors.
- GPT tooling reports the protective MBR and backup GPT still describe the earlier disk end; a real write would update these. No corrective write performed.

This establishes an existing unallocated-capacity path. No new cloud disk purchase is necessary for this particular 10 GiB increase; it does not establish long-term capacity sufficiency or any cloud billing history.

## Approval and safeguards required

The root filesystem also hosts the protected PTA workload. Obtain user approval and verify an available cloud disk snapshot/recovery path before any actual partition change. A partition-table dump is not a substitute for a full disk snapshot.

After approval, revalidate live disk geometry, filesystem health, collector state and backups. Expand only partition 3 with its start unchanged, then the ext4 filesystem. Confirm kernel partition size before filesystem growth. If kernel recognition fails or a reboot is requested, stop and coordinate rather than rebooting PTA without authorization.

After successful growth: verify filesystem free space, PTA health, PostgreSQL health and backup access; then retry bounded financial collection while retaining the 2 GiB reserve. No deletion of financial evidence, no blind image pruning, no filesystem shrinking, no increase to memory limits.

Current status: awaiting approval/recovery-path verification. Local research remains possible; the overall goal is not globally blocked.
