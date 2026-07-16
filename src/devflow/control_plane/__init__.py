"""Control plane package — owns ticket/project/milestone lifecycle.

This is the V2 control plane (blueprint §4.1). It is completely separate from
the workflow runtime (``devflow.loop``). The control plane owns *why* work
exists and *when* it's ready to integrate; the loop owns *how* work executes.

No autonomous promotion — the control plane reuses the existing
``result_branch.py`` boundary for all promotion authority.
"""
