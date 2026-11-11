# The coding task
A real bug from [boltons](https://github.com/mahmoud/boltons): `fileutils.rotate_file` dropped one generation
(issue #483). `repo/` is the library at commit `fe1ce8bc` (the parent of the fix) with `tests/test_fileutils.py` taken
from the fix commit `1c2db466`, so the test fails on this checkout. `fixed/boltons/fileutils.py` is the maintainer's
version, used only by the validator as a positive control; it is not in the agent's image.
