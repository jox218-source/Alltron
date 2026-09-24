# Public publication gate

Alltron is public. A pushed branch exposes **every commit in that branch**, including files later deleted. Run this gate before each branch push, PR update and release. The current household Pi and private source tree are never audit inputs.

## Approved source selection

`docs/PUBLIC_PATHS.txt` is an exact path allowlist. It contains only reviewed public code, docs, tests and GitHub configuration. A new path requires a manifest edit and human review of its origin, license and content before it can be pushed. No broad `src/**` or media allowance is present. Public examples must be invented. Do not add photographs, audio, model weights, account caches, local state, personal files, machine addresses, private source directories, symlinks or submodules.

Alltron-owned source is GPL-3.0-only. The current Python preview has no third-party runtime package or bundled model/voice asset. `setuptools` builds the package; `detect-secrets` is an optional audit dependency. Before any third-party code, speech engine, voice, model or wake asset is distributed, record its source, version, license, modification status and distribution terms, then obtain Sol High review.

## Repeatable check

From a clean Alltron checkout on the proposed commit:

```sh
python -m pip install -e ".[audit]"
python tools/publication_audit.py
git diff --check b400f035ea3d69254d71bec5ced2a2fe1cdd4557..HEAD
git status --short
```

Install the optional local pre-push guard once per clone with `git config core.hooksPath .githooks`. It runs the same audit and refuses a push of a different checked-out commit. The guard supplements the manual Sol High review and GitHub CI; it cannot inspect a push made from another clone where the hook was not installed.

GitHub `main` protection requires a pull request and successful `privacy` plus Python 3.11/3.12/3.13 checks, including for the repository administrator. Force pushes and deletion are disabled. Development branches become public **before** CI runs, so the local gate and exact-SHA review still precede every branch push.

Before confirming a GitHub PR merge, verify the merging account's web commit email privacy setting and select its GitHub no-reply address in the merge dialog. Review the proposed merge or squash message for personal data. Do not merge if the identity or message is uncertain. Immediately after a merge, inspect the new `main` commit's raw author, committer and message and rerun this audit; stop further publication if unexpected personal data appears. This pre-merge check is separate from the branch pre-push hook.

The audit refuses a dirty tree, an unexpected remote or base, unapproved paths in **any post-root commit**, symlinks/submodules/binary or oversized files, non-no-reply commit identities except one immutable already-public merge commit, common personal-data patterns and scanner findings. It scans every historical text blob using private temporary files with `detect-secrets` verification disabled, so candidate values are not sent to verification services. Temporary files are removed after scanning; matched content is never printed. CI runs the same check for development branches and PRs.

The automated gate cannot recognize every household name, calendar detail, image, audio recording or license issue. Sol High must inspect the exact proposed SHA, every changed file and all commits and objects in the range. The reviewer records the SHA, scanner output, test results and any exceptions in the PR. If a questionable file entered a commit, rebuild a clean branch from the public base; deleting it later does not make the old commit safe.

## Known legacy metadata exception

The repository's original commit `b400f03` was public before this gate and has the owner's personal email in Git author metadata. On 2026-09-22 the owner chose to retain that history and document the exposure. PR #1 was subsequently squash-merged as `1255bc2`; its author metadata and commit message also contain the owner's personal email despite the no-reply development commits. Both commits are already public. The script treats the original commit as the fixed base and permits the exact immutable merge SHA as one metadata/message exception while still scanning its content and other message patterns. All other commits must use approved no-reply identities. These exceptions do **not** erase or hide the exposures, authorize future personal-email commits, or resolve copies already fetched or cached elsewhere.

## Release gate

The local pre-push hook blocks tag pushes because the branch auditor does not inspect annotated tagger/message metadata. Before any release tag, extend the gate to review that metadata, obtain exact-tag approval, then inspect the built archive, installer, package metadata and licenses. Verify GitHub secret scanning, push protection, Dependabot security updates and private vulnerability reporting remain enabled. Do not publish a beta until the dedicated Pi and independent owner setup gates in [STAGES.md](STAGES.md) pass.
