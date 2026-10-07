---
name: Stuck report
about: Claude Code waited on something far longer than it should have (or forever)
title: "[stuck] "
labels: stuck-report
---

**What was Claude waiting on?**
<!-- a Bash command, an MCP tool, a subagent, a device, a CI run, a background task... -->

**How long, and how did you find out?**

**Why did nobody notice?**
<!-- no timeout / the loop never broke / the call never returned / it finished but was never reported / ... -->

**How to reproduce**
```
<command or setup>
```

**Your environment**
- OS:
- Claude Code version:
- Framework / tools involved:

**Idea for a fix (optional)**
<!-- a timeout flag, a rule, a pack, ... -->
