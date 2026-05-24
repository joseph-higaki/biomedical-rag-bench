---
name: release
description: Guide the user through cutting a SemVer release of biomedical-rag-bench. Use this skill whenever the user mentions shipping, releasing, tagging, publishing, finalizing, or cutting a version (e.g. "release v1.0.0", "Project 1 is done, let's ship it", "tag and publish", "create a release"), even if they don't explicitly say "release." Claude does not execute the release — Claude presents each step and the user runs the commands themselves in their terminal.
---

# Release procedure

This skill walks the user through cutting a SemVer-tagged release of biomedical-rag-bench. The tag push triggers @.github/workflows/release.yml, which creates the GitHub Release from a release-notes file.

## Execution model

**Claude does not run git, gh, or any commands that modify the repository or remote state.** Claude presents each command in a code block with an explanation of what it does and what the expected outcome is. The user runs the command themselves in their own terminal and reports back. Claude waits for confirmation before proposing the next step.

This applies to every step below. There are no exceptions for "safe" or "obvious" commands. The whole point of this skill is to make a deliberate, observable release process.

## Confirmation gate (always run this first)

Before walking through any steps, ask the user:

> I'm ready to walk you through a release. Confirm:
> - Version to release: `<version>` (e.g. `v1.0.0`)
> - Currently on `main` with a clean working tree?
> - All eval results for this release committed?
>
> Reply with "yes" and the version number to proceed, or describe what's not ready.

Do not begin presenting steps until the user explicitly confirms.

## Choosing the version

If the user is unsure which SemVer component to bump, apply these rules:

- **MAJOR** — anything that breaks comparability with prior results. Eval metric definition changed, ground truth corrected, generator changed in a way that's more than a config swap, question removed.
- **MINOR** — adds capability without breaking prior results. New retriever, new questions added, new telemetry fields, new analysis.
- **PATCH** — bug fix that corrects a prior result. Token counting bug, off-by-one in hop counting, broken SPARQL template.

Project 1's first release is `v1.0.0` regardless of these rules — it's the initial public release.

## Steps

For each step:

1. Explain what the step does and why.
2. Show the command(s) in a code block.
3. Tell the user what to expect when they run it.
4. Wait for them to report the outcome before proceeding.

### Step 1 — Write the release notes file

Explain: the release notes file is the most important artifact of the release. The GitHub Action that creates the Release reads this file as the Release body. It also fails the workflow if the file doesn't exist, which is the safety mechanism preventing accidental releases.

Ask the user to create `.github/release-notes/<version>.md` with this structure (they fill in the findings based on real eval results):

```markdown
# <version> — <descriptive title>

One-paragraph summary of what shipped in this release.

## Findings summary

- H1: confirmed / refuted / partial. Specific numbers.
- H2: ...
- (continue for each sub-hypothesis tested in this release)

Full numbers and analysis: `eval/analyze.ipynb` at this tag.

## Reproducing this experiment

\`\`\`bash
git clone https://github.com/joseph-higaki/biomedical-rag-bench
cd biomedical-rag-bench
git checkout <version>
docker compose up -d
make ingest
python eval/run_eval.py --generator <model-id>
\`\`\`

Expected runtime: <X> hours on a laptop.

## Configuration used for the published results

- Generator: <model-id>
- Embeddings: sentence-transformers/all-MiniLM-L6-v2
- GraphDB: v11.3.2, `empty` ruleset
- Hetionet snapshot: <commit-sha> from github.com/hetio/hetionet
```

When the user confirms the notes file exists and has real content, present these commands for them to run:

```bash
git add .github/release-notes/<version>.md
git commit -m "Release notes for <version>"
git push origin main
```

Expected outcome: commit lands on `main` and pushes to origin without errors.

Wait for confirmation before continuing.

### Step 2 — Create and push the tag

Explain: the tag is the bookmark that pins the release. Pushing it triggers the GitHub Action.

Important: the tag must be created after the release notes file is committed. The Action verifies the notes file exists at the tagged commit.

Present these commands for the user to run:

```bash
git tag -a <version> -m "<descriptive title for the release>"
git push origin <version>
```

Expected outcome: `git tag` creates the tag locally; `git push origin <version>` sends it to GitHub and triggers the workflow.

Wait for confirmation before continuing.

### Step 3 — Verify the workflow ran successfully

Explain: the GitHub Action should complete within ~30 seconds, creating a Release page attached to the tag.

Present this command:

```bash
gh run watch
```

Or, if the user prefers the browser:

```bash
gh run list --limit 1
```

Then explain how to interpret the result.

If the workflow succeeded: proceed to Step 4.

If the workflow failed with "Missing release notes file": the notes file wasn't committed before tagging. Walk the user through rollback:

```bash
git tag -d <version>
git push --delete origin <version>
```

Then return to Step 1.

If the workflow failed with "Resource not accessible by integration": repo settings need adjustment. The fix is in @CLAUDE.local.md under "GitHub Actions setup → One-time setup" — the user needs to set Settings → Actions → General → Workflow permissions to "Read and write." Walk them through this, then retry from Step 2 (no rollback needed; the tag is still valid).

### Step 4 — Verify the Release exists

Present this command:

```bash
gh release view <version> --web
```

Expected outcome: a browser tab opens showing the Release page with the notes attached and a "Latest release" banner if this is the newest tag.

If the page looks correct, the release is done.

## After this release

If this is the first successful release of the repository, note to the user:

> The release workflow has now been proven end-to-end. If you find yourself wanting to streamline the process, this skill could be converted into a slash command at `.claude/commands/release.md` — automating the steps that proved safe and boring while keeping confirmation gates on the destructive ones (tag push, release creation).
>
> That work is optional and best done after a few more releases, once the workflow's failure modes are well understood.

## Scope

- Does not write findings content. The user authors that based on real eval results.
- Does not run the eval. That is a separate workflow.
- Does not execute git, gh, or any state-modifying commands. Presents them for the user.
- Does not handle post-release promotion or distribution. The release notes file and the Release page are the deliverables; what happens with them outside the repo is out of scope.
