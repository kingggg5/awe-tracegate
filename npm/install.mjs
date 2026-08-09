import { createHash, randomUUID } from "node:crypto";
import {
  cp,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const PACKAGE_VERSION = "0.3.0";
export const SCHEMA_VERSION = "awe.tracegate-skill-install.v1";
export const MANIFEST_NAME = ".awe-tracegate-managed.json";
export const ACTIVE_SKILLS = Object.freeze([
  "tracegate-check",
  "tracegate-compare-change",
  "tracegate-integrate-evidence",
  "tracegate-share-evidence",
  "tracegate-verify-evidence",
]);

const PACKAGE_ROOT = fileURLToPath(new URL("../", import.meta.url));
const SKILLS_ROOT = join(PACKAGE_ROOT, "skills");
const SAFE_SKILL = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;
const SAFE_DIGEST = /^[0-9a-f]{64}$/u;

export class InstallError extends Error {
  constructor(message) {
    super(message);
    this.name = "InstallError";
  }
}

async function pathState(path) {
  try {
    return await lstat(path);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

function portableRelative(root, path) {
  const value = relative(root, path).split(sep).join("/");
  if (!value || value.startsWith("../") || value.includes("/../")) {
    throw new InstallError(`Unsafe package path: ${value}`);
  }
  return value;
}

async function walkFiles(root, current = root, files = []) {
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const path = join(current, entry.name);
    if (entry.isSymbolicLink()) {
      throw new InstallError(`Skill packages cannot contain symlinks: ${path}`);
    }
    if (entry.isDirectory()) {
      await walkFiles(root, path, files);
    } else if (entry.isFile()) {
      files.push(path);
    } else {
      throw new InstallError(`Skill packages must contain regular files: ${path}`);
    }
  }
  return files;
}

async function fileHashes(root) {
  const state = await pathState(root);
  if (!state?.isDirectory() || state.isSymbolicLink()) {
    throw new InstallError(`Skill source must be a real directory: ${root}`);
  }
  const files = await walkFiles(root);
  files.sort((left, right) => left.localeCompare(right, "en"));
  const hashes = {};
  for (const path of files) hashes[portableRelative(root, path)] = await sha256(path);
  if (!("SKILL.md" in hashes)) {
    throw new InstallError(`Skill package has no SKILL.md: ${root}`);
  }
  return hashes;
}

function emptyManifest() {
  return {
    schema_version: SCHEMA_VERSION,
    installer_version: PACKAGE_VERSION,
    skills: {},
  };
}

function safeManifestPath(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !value.startsWith("/") &&
    !value.includes("\\") &&
    !value.split("/").some((part) => part === "" || part === "." || part === "..")
  );
}

function validateManifest(document, path) {
  if (
    !document ||
    typeof document !== "object" ||
    Array.isArray(document) ||
    document.schema_version !== SCHEMA_VERSION ||
    !document.skills ||
    typeof document.skills !== "object" ||
    Array.isArray(document.skills)
  ) {
    throw new InstallError(`Unsupported managed manifest: ${path}`);
  }
  for (const [name, record] of Object.entries(document.skills)) {
    if (!SAFE_SKILL.test(name) || !record || typeof record !== "object" || Array.isArray(record)) {
      throw new InstallError(`Managed manifest has an invalid record for ${name}`);
    }
    if (!record.files || typeof record.files !== "object" || Array.isArray(record.files)) {
      throw new InstallError(`Managed manifest has an invalid files map for ${name}`);
    }
    for (const [pathName, digest] of Object.entries(record.files)) {
      if (!safeManifestPath(pathName) || typeof digest !== "string" || !SAFE_DIGEST.test(digest)) {
        throw new InstallError(`Managed manifest has an invalid file for ${name}`);
      }
    }
  }
  return document;
}

async function loadManifest(path) {
  const state = await pathState(path);
  if (!state) return emptyManifest();
  if (!state.isFile() || state.isSymbolicLink()) {
    throw new InstallError(`Managed manifest must be a regular file: ${path}`);
  }
  try {
    return validateManifest(JSON.parse(await readFile(path, "utf8")), path);
  } catch (error) {
    if (error instanceof InstallError) throw error;
    throw new InstallError(`Managed manifest is unreadable: ${path}`);
  }
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function equalJson(left, right) {
  return canonicalJson(left) === canonicalJson(right);
}

async function assertManagedTree(destination, expected) {
  const state = await pathState(destination);
  if (!state?.isDirectory() || state.isSymbolicLink()) {
    throw new InstallError(`Managed skill is missing or unsafe: ${destination}`);
  }
  const actual = await fileHashes(destination);
  if (!equalJson(actual, expected)) {
    throw new InstallError(
      `Managed skill was modified outside the installer: ${destination}. ` +
        "Back up or remove the local changes before updating it.",
    );
  }
}

export async function availableSkills() {
  for (const skill of ACTIVE_SKILLS) {
    const state = await pathState(join(SKILLS_ROOT, skill, "SKILL.md"));
    if (!state?.isFile() || state.isSymbolicLink()) {
      throw new InstallError(`Package is missing active skill: ${skill}`);
    }
  }
  return [...ACTIVE_SKILLS];
}

function selectSkills(selected) {
  const skills = selected.length ? [...new Set(selected)] : [...ACTIVE_SKILLS];
  const unknown = skills.filter((skill) => !ACTIVE_SKILLS.includes(skill));
  if (unknown.length) {
    throw new InstallError(
      `Unknown skill: ${unknown.join(", ")}. Available: ${ACTIVE_SKILLS.join(", ")}`,
    );
  }
  return skills;
}

async function validateTarget(target) {
  const resolved = resolve(target);
  const state = await pathState(resolved);
  if (!state?.isDirectory()) {
    throw new InstallError(`Target repository is not a directory: ${resolved}`);
  }
  return resolved;
}

async function planInstall(target, selected) {
  const root = await validateTarget(target);
  const skills = selectSkills(selected);
  await availableSkills();
  const agentsRoot = join(root, ".agents");
  const agentsState = await pathState(agentsRoot);
  if (agentsState && (!agentsState.isDirectory() || agentsState.isSymbolicLink())) {
    throw new InstallError(`Agent destination must be a real directory: ${agentsRoot}`);
  }
  const destinationRoot = join(root, ".agents", "skills");
  const destinationState = await pathState(destinationRoot);
  if (destinationState && (!destinationState.isDirectory() || destinationState.isSymbolicLink())) {
    throw new InstallError(`Skill destination must be a real directory: ${destinationRoot}`);
  }
  const manifest = await loadManifest(join(destinationRoot, MANIFEST_NAME));
  const records = {};
  const actions = [];
  for (const skill of skills) {
    records[skill] = {
      package_version: PACKAGE_VERSION,
      files: await fileHashes(join(SKILLS_ROOT, skill)),
    };
    const destination = join(destinationRoot, skill);
    const destinationExists = Boolean(await pathState(destination));
    const managed = manifest.skills[skill];
    if (destinationExists && !managed) {
      throw new InstallError(
        `Refusing to overwrite unmanaged skill: ${destination}. Move it aside or choose another target.`,
      );
    }
    if (managed) await assertManagedTree(destination, managed.files);
    actions.push(!managed ? "install" : equalJson(managed, records[skill]) ? "current" : "update");
  }
  return { destinationRoot, manifest, records, skills, actions };
}

export async function checkSkills({ target, skills = [] }) {
  const plan = await planInstall(target, skills);
  if (plan.actions.some((action) => action !== "current")) {
    throw new InstallError("Installed skills are missing or do not match this package");
  }
  return plan;
}

export async function installSkills({ target, skills = [], dryRun = false }) {
  const plan = await planInstall(target, skills);
  if (dryRun || plan.actions.every((action) => action === "current")) return plan;

  await mkdir(plan.destinationRoot, { recursive: true });
  const stageRoot = await mkdtemp(join(plan.destinationRoot, ".awe-tracegate-stage-"));
  const backupRoot = join(stageRoot, ".backup");
  const installed = [];
  const manifestPath = join(plan.destinationRoot, MANIFEST_NAME);
  const manifestBackup = join(backupRoot, MANIFEST_NAME);
  let manifestBackedUp = false;

  try {
    for (let index = 0; index < plan.skills.length; index += 1) {
      if (plan.actions[index] === "current") continue;
      const skill = plan.skills[index];
      const staged = join(stageRoot, skill);
      await cp(join(SKILLS_ROOT, skill), staged, {
        recursive: true,
        errorOnExist: true,
        force: false,
        verbatimSymlinks: true,
      });
      if (!equalJson(await fileHashes(staged), plan.records[skill].files)) {
        throw new InstallError(`Staged skill failed digest verification: ${skill}`);
      }
    }

    await mkdir(backupRoot);
    for (let index = 0; index < plan.skills.length; index += 1) {
      if (plan.actions[index] === "current") continue;
      const skill = plan.skills[index];
      const destination = join(plan.destinationRoot, skill);
      let backup = null;
      if (await pathState(destination)) {
        backup = join(backupRoot, skill);
        await rename(destination, backup);
      }
      installed.push({ destination, backup });
      await rename(join(stageRoot, skill), destination);
    }

    const updated = {
      ...plan.manifest,
      installer_version: PACKAGE_VERSION,
      skills: { ...plan.manifest.skills, ...plan.records },
    };
    const temporaryManifest = join(stageRoot, `${MANIFEST_NAME}.${randomUUID()}.tmp`);
    await writeFile(temporaryManifest, `${JSON.stringify(updated, null, 2)}\n`, "utf8");
    if (await pathState(manifestPath)) {
      await rename(manifestPath, manifestBackup);
      manifestBackedUp = true;
    }
    await rename(temporaryManifest, manifestPath);
  } catch (error) {
    for (const { destination, backup } of installed.reverse()) {
      await rm(destination, { recursive: true, force: true });
      if (backup && (await pathState(backup))) await rename(backup, destination);
    }
    if (manifestBackedUp) {
      await rm(manifestPath, { force: true });
      if (await pathState(manifestBackup)) await rename(manifestBackup, manifestPath);
    }
    throw error;
  } finally {
    await rm(stageRoot, { recursive: true, force: true });
  }
  return plan;
}
