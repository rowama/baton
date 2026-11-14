---
id: "0146"
title: "Project documents: bind the living file, roles may take several, identity is the path"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13: Accept all."
sections: ["§5.2", "§10.4", "§10.5"]
---

# 0146. Project documents: bind the living file, roles may take several, identity is the path

## Context

Writing `2026-11-project-documents` from Decision 0142 raised six questions about what is bound and when. The suggested answers were put to the owner in one batch.

## Decision

1. **Which copy.** A binding takes the file as it is now, recording whether it differs from what was accepted (`edited_since_accepted`). The confirm-back says so when it does, so the owner's binding decision accepts the edit.
2. **Several documents per role.** A role declares `many: true` to accept one or more documents, bound and rebound as a list. The default is one.
3. **Identity.** A project document is identified by its path in the repo. A newer publication or attestation at the same path is a newer version; a moved file is a new document.
4. **When a deliverable counts.** Once its step is accepted and published, whether or not its run has completed.
5. **No withdrawal.** There is no withdraw command. A newer attestation supersedes an older one, and a deleted file is listed as deleted.
6. **Code.** Workspace-step output is not a project document automatically; the owner may attest a file from the tree.
