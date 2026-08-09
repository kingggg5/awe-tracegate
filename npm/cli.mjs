#!/usr/bin/env node

import { parseArgs } from "node:util";
import {
  InstallError,
  availableSkills,
  checkSkills,
  installSkills,
} from "./install.mjs";

function usage() {
  return `AWE TraceGate skill installer

Usage:
  awe-tracegate install --target <repository> [--skill <name>] [--dry-run]
  awe-tracegate check --target <repository> [--skill <name>]
  awe-tracegate list

This command only copies packaged skill files. It does not install Python,
run lifecycle scripts, fetch dependencies, start services, or execute agent code.`;
}

function parseOptions(args) {
  const { values, positionals } = parseArgs({
    args,
    allowPositionals: true,
    strict: true,
    options: {
      target: { type: "string", short: "t" },
      skill: { type: "string", short: "s", multiple: true, default: [] },
      "dry-run": { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false },
    },
  });
  return { command: positionals[0], extra: positionals.slice(1), values };
}

async function main(args) {
  let parsed;
  try {
    parsed = parseOptions(args);
  } catch (error) {
    console.error(error.message);
    console.error(usage());
    return 1;
  }

  const { command, extra, values } = parsed;
  if (values.help || !command) {
    console.log(usage());
    return values.help ? 0 : 1;
  }
  if (extra.length) throw new InstallError(`Unexpected arguments: ${extra.join(" ")}`);
  if (command === "list") {
    console.log((await availableSkills()).join("\n"));
    return 0;
  }
  if (!values.target) throw new InstallError(`--target is required for ${command}`);

  if (command === "check") {
    if (values["dry-run"]) throw new InstallError("--dry-run is only valid with install");
    const result = await checkSkills({ target: values.target, skills: values.skill });
    console.log(`Current: ${result.skills.join(", ")}`);
    return 0;
  }
  if (command !== "install") throw new InstallError(`Unknown command: ${command}`);

  const result = await installSkills({
    target: values.target,
    skills: values.skill,
    dryRun: values["dry-run"],
  });
  const plan = result.skills
    .map((skill, index) => `${skill} (${result.actions[index]})`)
    .join(", ");
  console.log(`${values["dry-run"] ? "Would install" : "Installed"}: ${plan}`);
  console.log(`Destination: ${result.destinationRoot}`);
  return 0;
}

try {
  process.exitCode = await main(process.argv.slice(2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
