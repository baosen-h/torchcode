import { LoadingState } from "@/components/loading-state";
import { Suspense } from "react";
import { TaskWorkspace } from "@/components/task-workspace";

export default async function ProblemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Suspense fallback={<LoadingState />}><TaskWorkspace key={id} taskId={id} /></Suspense>;
}
