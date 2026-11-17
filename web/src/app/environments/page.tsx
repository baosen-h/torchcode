import { LoadingState } from "@/components/loading-state";
import { Suspense } from "react";
import { EnvironmentManager } from "@/components/environment-manager";

export default function EnvironmentsPage() {
  return <Suspense fallback={<LoadingState />}><EnvironmentManager /></Suspense>;
}
