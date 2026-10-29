# SVD tools

`svd_to_qemu.py` generates a conservative, storage-backed QEMU `SysBusDevice`
from a CMSIS-SVD peripheral definition. It uses the `cmsis-svd` package in the
project virtual environment:

```sh
.venv/bin/python tools/svd_to_qemu.py \
  --svd=MIMXRT685S_cm33.xml \
  --peripheral=CTIMER \
  --output=rt6xx_ctimer.c
```

`--peripheral` accepts either an exact SVD peripheral name (`CTIMER0`) or an
SVD `groupName` (`CTIMER`). A group produces one reusable model and lists all
of its base addresses and interrupt numbers in the generated header comment.
Use `--qom-type` when the default lower-case, hyphenated QOM name is unsuitable.
Without `--output`, source is written to standard output.

The generated model implements register storage, reset values, access masks,
arrays and clusters, sub-word accesses, migration state, and CMSIS
`modifiedWriteValues`. Compatible alternate read/write views at the same
address are coalesced into one storage entry. SVD files do not describe
peripheral behaviour, so the result is a skeleton: device-specific side
effects, IRQ logic, clocks, resets, and connectivity still need to be
implemented manually.

Run the generator tests with:

```sh
.venv/bin/python -m unittest -v tools/test_svd_to_qemu.py
```

Generated source is intended only for local experimentation. The QEMU
submodule's `AGENTS.md` prohibits submitting AI-generated QEMU code upstream.
