import { LoadingState } from "@/components/loading-state";
import { Suspense } from "react";
import { ProblemLibrary } from "@/components/problem-library";

export default function ProblemsPage() {
  return <Suspense fallback={<LoadingState />}><ProblemLibrary /></Suspense>;
}
