# Credentials and public artifacts

Keep API keys in an untracked config.local.json or environment variables. A
wheel installation should use an external JSON file via --config or
ACADEMIC_TRANSLATE_CONFIG. Do not put credentials in command arguments, examples,
logs, commits or release archives.

Older revisions of this repository contained a local proxy credential. Removing
it from the current files or rewriting Git history does not revoke it. Operators
who used an exposed value must replace it at their proxy and update its clients.
Do not paste old or new credentials into a public issue.

History cleanup cannot erase third-party clones or every cached GitHub view.
After a history rewrite, start from a fresh clone or carefully transplant only
your clean changes; merging an old branch can restore removed sensitive history.
See GitHub's [sensitive-data removal guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

Before publishing, review the staged diff and inspect wheel/source archive
contents. .gitignore prevents accidental tracking of common private files but
does not remove already tracked files or inspect arbitrary file contents.
Runtime output, translation caches and rollback archives should stay private
unless explicitly reviewed for sharing.
