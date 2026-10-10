import Link from "next/link";
import { navigation } from "@/lib/navigation";

export default async function PlannedSectionPage({ params }: { params: Promise<{ segments: string[] }> }) {
  const { segments } = await params;
  const path = `/${segments.join("/")}`;
  const entry = navigation.find((item) => item.href === path);
  const title = entry?.label ?? segments.at(-1)?.replaceAll("-", " ") ?? "Page";

  return (
    <div className="page-wrap planned-page">
      <p className="eyebrow">FAMILYOS</p>
      <h1>{title}</h1>
      <div className="planned-rule" />
      <p>This section is staged behind its service and is not available yet.</p>
      <Link className="text-link" href="/">Return home <span aria-hidden="true">→</span></Link>
    </div>
  );
}