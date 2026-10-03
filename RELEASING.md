# Releasing

Users install simplicity through the `eonraider` marketplace (`EONRaider/claude-plugins`). That marketplace pins each plugin to a tag and a commit SHA. Merging to `main` alone ships nothing to them.

1. **Bump the version.** Set `version` in `.claude-plugin/plugin.json`. The install cache is keyed by version, so a release without a bump may not reach users who already installed it.
2. **Date the changelog.** Change the release's CHANGELOG heading from `Unreleased` to the release date, and update the compare links at the bottom of the file.
3. **Merge to `main`.**
4. **Tag the merge commit** as `vX.Y.Z`, then push the tag:

   ```bash
   git tag -a vX.Y.Z -m "simplicity vX.Y.Z" <merge-sha>
   git push origin vX.Y.Z
   ```

   Don't use `claude plugin tag` for this. It creates `simplicity--vX.Y.Z`, but the CHANGELOG and the marketplace use `vX.Y.Z`.
5. **Update the marketplace.** In `EONRaider/claude-plugins`, edit the `simplicity` entry in `.claude-plugin/marketplace.json`:
   - set `ref` to the new tag and `sha` to the tagged commit;
   - set `version` to the new version, matching `plugin.json`;
   - refresh `description` and `keywords` so they cover every skill;
   - update the simplicity line in that repo's README.

   Check it with `claude plugin validate .claude-plugin/marketplace.json`, then merge.
6. **Update your own install:**

   ```bash
   claude plugin marketplace update eonraider
   claude plugin update simplicity@eonraider
   ```

   Then restart Claude Code.
