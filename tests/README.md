
## Description

Add tests for the repository itself (non-DUT parts) in this folder:

For example:
1. Tests for common functions, such as adding common functions in `comm.functions`
1. Tests for tools, such as testing `tool.disasm`
1. Other non-DUT functionality tests, such as Python version, multi-node execution, etc.


Run these tests directly, without the DUT/report plugin:
```bash
python3 -m pytest -q -p no:toffee-test tests
```
