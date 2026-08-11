import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  ACTIVE_SKILLS,
  InstallError,
  MANIFEST_NAME,
  checkSkills,
  installSkills,
} from "./install.mjs";

test("reports the package version without touching a repository", () => {
  const result = execFileSync(
    process.execPath,
    [fileURLToPath(new URL("./cli.mjs", import.meta.url)), "--version"],
    { encoding: "utf8" },
  );
  assert.equal(result.trim(), "awe-tracegate 0.3.0");
});

async function workspace(t) {
  const root = await mkdtemp(join(tmpdir(), "awe-tracegate-npm-test-"));
  t.after(async () => rm(root, { recursive: true, force: true }));
  return root;
}

test("installs only the selected skill and records managed hashes", async (t) => {
  const root = await workspace(t);
  const result = await installSkills({
    target: root,
    skills: ["tracegate-check"],
  });
  assert.deepEqual(result.actions, ["install"]);
  const manifest = JSON.parse(
    await readFile(join(root, ".agents", "skills", MANIFEST_NAME), "utf8"),
  );
  assert.deepEqual(Object.keys(manifest.skills), ["tracegate-check"]);
  assert.match(manifest.skills["tracegate-check"].files["SKILL.md"], /^[0-9a-f]{64}$/u);
  await checkSkills({ target: root, skills: ["tracegate-check"] });

  manifest.skills["tracegate-check"].package_version = "0.2.9";
  await writeFile(
    join(root, ".agents", "skills", MANIFEST_NAME),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
  const updated = await installSkills({ target: root, skills: ["tracegate-check"] });
  assert.deepEqual(updated.actions, ["update"]);
  await checkSkills({ target: root, skills: ["tracegate-check"] });
});

test("dry-run is non-mutating", async (t) => {
  const root = await workspace(t);
  const result = await installSkills({ target: root, dryRun: true });
  assert.equal(result.skills.length, ACTIVE_SKILLS.length);
  await assert.rejects(readFile(join(root, ".agents", "skills", MANIFEST_NAME)), {
    code: "ENOENT",
  });
});

test("refuses unmanaged and locally modified skills", async (t) => {
  const unmanagedRoot = await workspace(t);
  const unmanaged = join(unmanagedRoot, ".agents", "skills", "tracegate-check");
  await mkdir(unmanaged, { recursive: true });
  await writeFile(join(unmanaged, "SKILL.md"), "user content\n", "utf8");
  await assert.rejects(
    installSkills({ target: unmanagedRoot, skills: ["tracegate-check"] }),
    (error) => error instanceof InstallError && /unmanaged skill/u.test(error.message),
  );

  const managedRoot = await workspace(t);
  await installSkills({ target: managedRoot, skills: ["tracegate-check"] });
  await writeFile(
    join(managedRoot, ".agents", "skills", "tracegate-check", "SKILL.md"),
    "local edit\n",
    "utf8",
  );
  await assert.rejects(
    installSkills({ target: managedRoot, skills: ["tracegate-check"] }),
    (error) => error instanceof InstallError && /modified outside/u.test(error.message),
  );
});
