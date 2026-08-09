import createClient from "openapi-fetch";

import type { components, paths } from "./schema.js";

export type CompilationReceipt = components["schemas"]["CompilationReceipt"];
export type EvaluationReceipt = components["schemas"]["EvaluationReceipt"];
export type ExperimentManifest = components["schemas"]["ExperimentManifest"];
export type ExecutionTrace = components["schemas"]["ExecutionTrace"];
export type PromotionReceipt = components["schemas"]["PromotionReceipt"];
export type ReceiptVerification = components["schemas"]["ReceiptVerification"];

export function createTraceGateClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}

export type TraceGateClient = ReturnType<typeof createTraceGateClient>;
